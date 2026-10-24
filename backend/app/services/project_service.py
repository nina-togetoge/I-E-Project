# =============================================================================
# 项目申报与审核 业务逻辑层（Service）
#
# 职责范围：
#   1) 项目申报：创建草稿、编辑、提交、撤回、删除，以及比赛名额/报名窗口校验；
#   2) 审核推进：指导教师确认 → 学院初审 → 校级复审 → 分配专家 → 专家评审 → 立项；
#   3) 过程管理：中期检查、结题验收（提交报告、专家验收、撤回/驳回重提）；
#   4) 过程变更：变更/延期申请的截止日锁定与超期自动作废；
#   5) 成果管理：项目成果登记、修改、认定/撤销认定、删除与证明材料绑定；
#   6) 统计分析：概览、月度趋势、学院维度对比。
#
# 核心表（均带 is_deleted 软删标记）：
#   proj_project            项目主表（状态机、负责人/指导教师、学院、比赛、金额汇总）
#   proj_team_member        项目团队成员（名额占用校验依据）
#   proj_review             审核记录（review_stage 区分教师/学院/校级/专家/结题，
#                           review_result=99 表示“占位待评审/报告占位”）
#   proj_budget             预算明细（budget_item 科目 + budget_amount/used_amount）
#   proj_expense            经费报销单（status 处于中间态时阻塞结项）
#   proj_achievement        项目成果（achievement_type=4 为竞赛获奖，用于获奖统计）
#   proj_achievement_review 成果认定记录（0 待认定 / 1 已认定 / 2 不通过）
#   proj_midterm_check      中期检查报告（status=2 为已通过，5 为已作废）
#   proj_change_request     变更/延期申请（0 待审核，6 为超期自动作废）
#   附属表：sys_attachment（biz_type=project/achievement 的附件）、sys_user、sys_college
#
# 上游调用方：
#   app/api/routers/project_router.py（项目/成果/统计接口）
#   app/api/routers/common_router.py（公共统计入口）
#   app/services/archive_service.py、review_service.py（归档与审核流转复用本服务）
# 下游依赖：
#   ProjectCRUD / ReviewCRUD / MidtermCRUD / AchievementCRUD / UserCRUD / CollegeCRUD（数据访问）
#   NotificationService（站内通知）、DataScope（角色数据权限）
#
# 关键约束（改代码前务必先读）：
#   - 状态码 PROJECT_STATUS_*：0 草稿、12 待指导教师确认、1 待学院初审、2 学院通过、
#     3 待校级复审、4 校级通过、5 待专家评审、13 待分配专家、6 已立项、7 中期检查、
#     8 待结题、9 已结题、10 已驳回、11 已撤销。状态只能沿流程单向前进（撤回/驳回除外）。
#   - 软删：所有业务查询必须显式带 is_deleted == 0，删除一律置 1 并级联子表，
#     以保证列表、统计与唯一性校验不会读到“已删但残留”的数据。
#   - 金额：budget_amount/used_amount 由数据库 Numeric(12,2) 承载，Python 侧使用 Decimal；
#     统计输出转 Decimal(str(x))，禁止用 float 做金额相等/累加判断。
#   - 行级锁：本文件的状态前置校验在单事务内完成，未显式 with_for_update；
#     真正的并发加锁（审核/报销流转）在 review_service.py、expense_service.py 中实现。
#   - 截止日：截止日当天仍可操作，只有 date.today() > deadline 才锁定（见 is_past_deadline）。
#   - 落选终局：学院/校级/专家驳回视为落选，不可改后重提；仅指导教师驳回可重提。
# =============================================================================
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case
from sqlalchemy.exc import IntegrityError

from app.core.security import RoleEnum, ROLE_NAME_MAP, is_super_admin, is_college_admin
from app.core.exceptions import (
    PermissionDeniedException, ResourceNotFoundException, ParamValidateException,
    DataConflictException,
)
from app.core.deps import PaginationParams, DataScope
from app.crud.user import CollegeCRUD, UserCRUD
from app.crud.project import ProjectCRUD, AchievementCRUD
from app.crud.review import ReviewCRUD, MidtermCRUD
from app.schemas.review import (
    REVIEW_STAGE_COLLEGE, REVIEW_STAGE_TEACHER, REVIEW_STAGE_UNIVERSITY, REVIEW_STAGE_EXPERT,
    REVIEW_STAGE_FINAL, REVIEW_RESULT_REJECT, REVIEW_RESULT_MODIFY,
)
from app.models import (
    ProjProject, ProjTeamMember, SysUser, ProjAchievement, ProjAchievementReview, ProjBudget,
    ProjReview, ProjExpense, ProjChangeRequest, Competition,
)
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectQueryParams,
    ProjectListItem, ProjectDetailResponse, ProjectSubmitResponse,
    AchievementCreate, AchievementUpdate, AchievementReviewRequest, AchievementResponse,
    ProjectStatisticsResponse,
    StatisticsTrendItem, CollegeStatisticsItem, PROJECT_STATUS_DRAFT, PROJECT_STATUS_PENDING_COLLEGE,
    PROJECT_STATUS_PENDING_TEACHER, PROJECT_STATUS_PENDING_UNIVERSITY, PROJECT_STATUS_PENDING_EXPERT,
    PROJECT_STATUS_PENDING_EXPERT_ASSIGN,
    PROJECT_STATUS_APPROVED, PROJECT_STATUS_MIDTERM, PROJECT_STATUS_PENDING_FINAL,
    PROJECT_STATUS_REJECTED, PROJECT_STATUS_CANCELLED, PROJECT_STATUS_NAME,
    EXPENSE_STATUS_COMPLETED, EXPENSE_STATUS_REJECTED,
)
from app.schemas.review import (
    CHANGE_STATUS_PENDING, CHANGE_STATUS_EXPIRED,
)
from app.services.notification_service import (
    NotificationService, NOTICE_LEVEL_INFO, NOTICE_LEVEL_WARNING, NOTICE_LEVEL_SUCCESS,
)


class ProjectService:
    """项目全生命周期业务服务。

    覆盖申报（草稿/提交/撤回/删除）、审核推进（教师→学院→校级→专家）、
    中期与结题验收、变更延期截止日锁定、统计分析与结项条件校验。
    所有方法均为静态方法，本身不持有状态；调用方负责传入已开启的事务 Session，
    方法内部按需 commit（写操作）或只读查询（统计/详情）。
    """

    # 可提交变更/延期申请的项目阶段：仅「待校级复审」「待专家评审」两个审核段
    # 业务原因：变更/延期会改动项目关键信息，只能在仍有后续审核环节兜底时提出；
    # 学院初审前信息尚未定稿，已立项后则走线下/结题口径，均不开放。
    CHANGE_WINDOW_STATUSES = {
        PROJECT_STATUS_PENDING_UNIVERSITY, PROJECT_STATUS_PENDING_EXPERT,
    }

    # 不占用比赛申报名额的状态：草稿 / 已驳回 / 已撤销
    # 即“未真正进入比赛”的项目；其余状态（含待指导教师确认）都算占用名额，
    # 防止同一学生反复提交占坑。
    NON_OCCUPYING_STATUSES = (
        PROJECT_STATUS_DRAFT, PROJECT_STATUS_REJECTED, PROJECT_STATUS_CANCELLED,
    )

    # ================= 流程截止日（截止日驱动锁定） =================
    # 统一约定：所有截止日都来自 Competition 时间表，而不是每个项目单独存字段。
    # 这样比赛调整时间表时，全部项目的锁定状态会自动跟随，避免逐项目改数据。
    @staticmethod
    def _get_competition(db: Session, project: ProjProject) -> Optional[Competition]:
        """项目所关联的比赛（时间表来源）；未关联返回 None

        参数:
            db: 当前事务会话
            project: 项目 ORM 对象，允许为空
        返回:
            Competition 或 None（项目为空 / 未选比赛 / 比赛已被物理删除）
        注意:
            这里不校验 Competition.is_deleted：即使比赛下架，已申报项目仍需用其
            时间表判断截止，否则历史项目会突然“解禁”。
        """
        if not project or not project.competition_id:
            return None
        return db.query(Competition).filter(Competition.id == project.competition_id).first()

    @staticmethod
    def is_past_deadline(deadline: Optional[date]) -> bool:
        """是否已过截止日（截止日当天仍可用）；未配置(None)视为不锁

        边界说明:
            用 ``date.today() > deadline`` 而不是 ``>=``，保证截止日 23:59 前
            提交仍算按时；未配置时间表属于“未启用限制”，一律放行。
        返回:
            True 表示已过期，调用方应拒绝操作；False 表示仍可操作。
        """
        if deadline is None:
            return False
        return date.today() > deadline

    @staticmethod
    def get_change_deadline_for_status(db: Session, project: ProjProject, status: Optional[int]) -> Optional[date]:
        """指定审核段的变更/延期锁死日（比赛未配置时间表则不锁）

        参数:
            status: 期望判断的审核段状态，不一定等于项目当前状态。
                传入历史状态（obj.project_status_at_submit）可还原“提交时”的口径，
                避免项目推进后缓冲期被意外放宽。
        返回:
            该审核段对应的比赛审核日；比赛不存在或该状态不在变更窗口内返回 None。
        """
        comp = ProjectService._get_competition(db, project)
        if not comp:
            return None
        return {
            PROJECT_STATUS_PENDING_UNIVERSITY: comp.university_review_date,  # 待校级复审
            PROJECT_STATUS_PENDING_EXPERT: comp.expert_review_date,          # 待专家评审
        }.get(status)

    @staticmethod
    def get_change_deadline(db: Session, project: ProjProject) -> Optional[date]:
        """项目『当前阶段审核日』= 变更/延期申请的锁死日（比赛未配置时间表则不锁）

        业务含义:
            变更/延期必须在“当前审核段真正开审之前”提出；一旦到了审核日，
            审核人已按旧信息评审，再改会造成评审结论与材料不一致。
        """
        return ProjectService.get_change_deadline_for_status(db, project, project.status)

    @staticmethod
    def get_teacher_confirm_deadline(db: Session, project: ProjProject) -> Optional[date]:
        """指导教师确认截止日 = 学院初审审核日

        设计原因:
            指导教师确认是学院初审的前置动作，因此复用学院初审日作为最后期限；
            不再单独维护一套教师确认时间表，减少配置不一致。
        """
        comp = ProjectService._get_competition(db, project)
        return comp.college_review_date if comp else None

    @staticmethod
    def get_midterm_deadline(db: Session, project: ProjProject) -> Optional[date]:
        """中期报告提交/审核截止日

        返回比赛配置的 midterm_deadline；未关联比赛返回 None（视为不限制）。
        """
        comp = ProjectService._get_competition(db, project)
        return comp.midterm_deadline if comp else None

    @staticmethod
    def get_final_deadline(db: Session, project: ProjProject) -> Optional[date]:
        """结题报告提交/审核截止日

        返回比赛配置的 final_deadline；未关联比赛返回 None（视为不限制）。
        """
        comp = ProjectService._get_competition(db, project)
        return comp.final_deadline if comp else None

    # ================= 超期自动作废清扫（读详情 / 审核列表时顺带执行） =================
    # 采用“惰性清扫”而非定时任务：读取详情或审核待办时顺带把过期数据落库。
    # 好处是不依赖调度器、任何部署环境都能生效；代价是清理有延迟（首次被读取时）。
    # 调用点：本文件 get_detail；review_service.py 的审核详情/待办列表。
    @staticmethod
    def sweep_expired_change_requests(db: Session, project_ids: Optional[List[int]] = None) -> int:
        """把已过『审核日 + 1 天缓冲期』仍待审核的变更/延期申请置为『已作废』；记录保留以便追责

        参数:
            db: 事务会话
            project_ids: 限定清扫范围；None 表示全表清扫，空列表直接返回 0
        返回:
            本次实际作废的申请条数
        副作用:
            会修改 ProjChangeRequest.status / reject_reason，有变更时 commit
        注意:
            1) 缓冲期为 1 天：审核日当天和次日仍给审核人处理时间；
            2) 必须以“提交时所属审核段”的审核日为准（project_status_at_submit），
               否则项目一旦推进到下一阶段，截止日会变松，过期申请永远清不掉；
            3) 只置状态不物理删除，保留申请内容与作废原因用于追责/审计。
        """
        # 1. 先筛出所有待审核且未删除的变更/延期申请（可按项目集合缩小范围）
        q = db.query(ProjChangeRequest).filter(
            ProjChangeRequest.is_deleted == 0,
            ProjChangeRequest.status == CHANGE_STATUS_PENDING,
        )
        if project_ids is not None:
            if not project_ids:
                return 0
            q = q.filter(ProjChangeRequest.project_id.in_(project_ids))
        voided = 0
        for obj in q.all():
            project = ProjectCRUD.get_by_id(db, obj.project_id)
            # 以提交时所属审核段的审核日为准，避免项目已推进导致缓冲期被放宽
            deadline = ProjectService.get_change_deadline_for_status(
                db, project, obj.project_status_at_submit or project.status
            ) if project else None
            # 2. 超过“审核日 + 1 天”才作废；未配置时间表(deadline=None)则不作废
            if deadline is not None and date.today() > deadline + timedelta(days=1):
                obj.status = CHANGE_STATUS_EXPIRED
                obj.reject_reason = "超过审批缓冲期自动作废"
                voided += 1
        # 3. 有实际变更才提交事务，避免只读请求产生空 commit
        if voided:
            db.commit()
        return voided

    @staticmethod
    def sweep_expired_midterm(db: Session, project_id: int) -> None:
        """中期检查截止日清扫：
        - 截止日前已提交(待审核 status=1)的报告继续保留，指导教师仍可审核（避免流程死锁）
        - 截止日时仍未提交/未通过(草稿/修改/驳回) → 项目终止为「已撤销(11)」，留档追责

        参数:
            db: 事务会话
            project_id: 单个项目 ID（详情/列表读取时逐个调用）
        副作用:
            可能把中期报告置为已作废(5)、项目置为已撤销(11) 并 commit
        注意:
            1) 只处理“已立项(6) / 中期检查(7)”的项目，已结题或未立项项目不受影响；
            2) 已提交待审核(1)或已通过(2)必须保留：如果截止后直接终止项目，
               按时提交的学生会因审核人未及时处理而被误杀；
            3) 这是“到了截止日仍未提交”的兜底终止，不是审核结果。
        """
        project = ProjectCRUD.get_by_id(db, project_id)
        # 状态守卫：仅立项后、结题前的项目适用中期终止
        if not project or project.status not in (PROJECT_STATUS_APPROVED, PROJECT_STATUS_MIDTERM):
            return
        deadline = ProjectService.get_midterm_deadline(db, project)
        # 未配置截止日或尚未到期 → 不处理（截止日当天仍允许提交）
        if deadline is None or date.today() <= deadline:
            return
        midterm = MidtermCRUD.get_by_project(db, project_id)
        if midterm and midterm.status in (1, 2):
            # 已按时提交待审核 / 已通过：保留，审核不再受截止日限制
            return
        # 草稿/修改中/驳回/无记录：视为未按期完成，报告作废 + 项目终止
        if midterm:
            midterm.status = 5  # 已作废
            midterm.review_comment = "超过中期报告提交截止日未通过，项目自动终止"
        project.status = PROJECT_STATUS_CANCELLED
        project.reject_reason = "超过中期检查截止日仍未通过中期检查，项目自动终止"
        db.commit()

    @staticmethod
    def sweep_expired_final(db: Session, project_id: int) -> None:
        """结题报告截止日清扫：
        - 截止日前已提交报告（占位记录）→ 保留，专家仍可继续验收
        - 截止日时仍未提交报告 → 项目终止为「已撤销(11)」，避免永久卡在待结题(8)

        参数:
            db: 事务会话
            project_id: 单个项目 ID
        副作用:
            可能把项目置为已撤销(11) 并 commit
        注意:
            只对 status=8（待结题）生效；判定“已提交”看是否存在
            review_stage=4(结题)、review_result=99 的占位记录，
            而不是看项目字段，避免报告正文与流程状态不一致。
        """
        project = ProjectCRUD.get_by_id(db, project_id)
        # 状态守卫：仅待结题项目适用，已结题(9)/其他阶段直接跳过
        if not project or project.status != PROJECT_STATUS_PENDING_FINAL:
            return
        deadline = ProjectService.get_final_deadline(db, project)
        if deadline is None or date.today() <= deadline:
            return
        # 1. 检查是否在截止日前已提交报告占位记录（result=99）
        has_report = db.query(ProjReview.id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.review_result == 99,
            ProjReview.is_deleted == 0,
        ).first()
        # 2. 已提交则保留，专家验收不受截止日限制（否则会误杀按时提交的项目）
        if has_report:
            return
        # 3. 未提交 → 自动终止并写明原因，便于学生/管理员追溯
        project.status = PROJECT_STATUS_CANCELLED
        project.reject_reason = "超过结题报告提交截止日未提交结项报告，项目自动终止"
        db.commit()

    @staticmethod
    def _to_list_item(obj: ProjProject) -> ProjectListItem:
        """ORM -> Pydantic 列表项（只补齐字典名称，不做额外查询）

        参数:
            obj: 已加载 leader/teacher/competition 关系的项目对象
        返回:
            ProjectListItem；类型/级别/状态的中文名由 ProjectCRUD 的字典映射填充
        注意:
            列表页为了性能不应逐条查库；college_name 在这里只是兜底，
            批量场景由 paginate 预取 college_map 覆盖。单条调用时依赖
            obj 所属 Session 按需查询（可能产生一次额外查询）。
        """
        item = ProjectListItem.model_validate(obj)
        # 字典值 -> 中文名：未知 code 返回空串，避免前端展示 undefined
        item.project_type_name = ProjectCRUD.PROJECT_TYPE_NAME.get(item.project_type, "")
        item.project_level_name = ProjectCRUD.PROJECT_LEVEL_NAME.get(item.project_level, "")
        item.status_name = ProjectCRUD.STATUS_NAME.get(item.status, "")
        if obj.leader:
            item.leader_name = obj.leader.real_name
        if obj.teacher:
            item.teacher_name = obj.teacher.real_name
        if obj.competition_id and obj.competition:
            item.competition_name = obj.competition.title
        if obj.college_id:
            # 仅当 ORM 对象仍绑定 Session 时才能安全懒加载，否则保持为空由调用方批量填充
            college = CollegeCRUD.get_by_id(obj._sa_instance_state.session, obj.college_id) \
                if hasattr(obj, "_sa_instance_state") and obj._sa_instance_state.session else None
            if college:
                item.college_name = college.college_name
        return item

    @staticmethod
    def _to_detail(db: Session, obj: ProjProject, operator: Optional[SysUser] = None) -> ProjectDetailResponse:
        """ORM -> Pydantic 详情（含团队/预算等子表）

        参数:
            db: 事务会话
            obj: 项目 ORM 对象
            operator: 当前操作人；传入时才计算“专家验收入口/我是否已验收”等个性化字段
        返回:
            ProjectDetailResponse，包含结项报告状态、检查清单、截止日与附件列表
        注意:
            这是“重型”转换：会多次查询 proj_review / proj_achievement / sys_attachment，
            仅供详情接口使用，不要放进列表循环（列表请用 _to_list_item）。
        """
        item = ProjectDetailResponse.model_validate(obj)
        item.project_type_name = ProjectCRUD.PROJECT_TYPE_NAME.get(item.project_type, "")
        item.project_level_name = ProjectCRUD.PROJECT_LEVEL_NAME.get(item.project_level, "")
        item.status_name = ProjectCRUD.STATUS_NAME.get(item.status, "")
        if obj.leader:
            item.leader_name = obj.leader.real_name
        if obj.teacher:
            item.teacher_name = obj.teacher.real_name
        if obj.competition_id and obj.competition:
            item.competition_name = obj.competition.title
        college = CollegeCRUD.get_by_id(db, obj.college_id)
        if college:
            item.college_name = college.college_name
        # ---------- 是否允许修改后重新提交 ----------
        # 是否「可修改后重新提交」：仅「指导教师驳回」允许；学院/校级/专家驳回即落选（终局）
        item.resubmittable = (
            item.status == PROJECT_STATUS_REJECTED
            and not ProjectService._is_eliminated(db, obj)
        )
        # ---------- 结项报告正文与验收状态 ----------
        # 结项报告（占位记录：阶段=结题验收4、结果=99）正文与验收状态
        report_record = ProjectService._final_report_record(db, obj.id)
        item.final_report_submitted = report_record is not None
        item.final_report = ProjectService._strip_report_prefix(
            report_record.review_comment
        ) if report_record else None
        # final_report_status：0 未提交 / 1 待验收 / 2 已通过(已结题) / 3 验收驳回可重提
        # 判断顺序不能颠倒：已结题(9)优先于 reject_reason，避免历史驳回原因造成误判
        if obj.status == 9:
            item.final_report_status = 2  # 已通过（已结题）
        elif report_record and obj.reject_reason:
            item.final_report_status = 3  # 验收驳回，可修改后重新提交
        elif report_record:
            item.final_report_status = 1  # 待验收
        else:
            item.final_report_status = 0  # 未提交
        # ---------- 本轮驳回意见（仅在“验收驳回”态展示） ----------
        # 驳回意见：取本轮最新一条驳回记录（仅驳回态展示，避免验收中误提示）
        item.final_reject_reason = None
        if item.final_report_status == 3:
            # 只取本轮、非“通过”的意见；按 id 最大者视为最新，防止多专家并发覆盖
            rejects = [
                r for r in ProjectService.final_latest_reviews(db, obj.id).values()
                if r.review_result != 1
            ]
            if rejects:
                item.final_reject_reason = max(rejects, key=lambda r: r.id).review_comment
        # 应参与验收专家数 / 本轮已提交意见专家数（前端进度条）
        item.final_review_total, item.final_review_done = ProjectService.final_review_stats(db, obj.id)
        # 专家验收入口：被分配到该项目的专家或超级管理员
        # 注意：仅 status=8（待结题）开放验收，已结题(9)不能再改结论
        if operator is not None:
            item.final_can_accept = (
                obj.status == 8
                and (
                    is_super_admin(operator)
                    or operator.id in ProjectService.assigned_expert_ids(db, obj.id)
                )
            )
            item.final_reviewed_by_me = operator.id in ProjectService.final_latest_reviews(db, obj.id)
        # 结项硬性条件清单（中期/成果/报销/报告），前端展示用，提交时另有强校验
        item.final_checklist = ProjectService.get_final_checklist(db, obj)
        # ---------- 流程截止日与锁定状态 ----------
        # 流程截止日（截止日驱动锁定）：变更/延期锁死日 = 当前阶段审核日
        item.change_deadline = ProjectService.get_change_deadline(db, obj)
        # 两种锁定原因：不在变更窗口状态，或已过审核日；前端据此禁用“申请变更”按钮
        item.change_locked = (
            obj.status not in ProjectService.CHANGE_WINDOW_STATUSES
            or ProjectService.is_past_deadline(item.change_deadline)
        )
        item.midterm_deadline = ProjectService.get_midterm_deadline(db, obj)
        item.final_deadline = ProjectService.get_final_deadline(db, obj)
        # 竞赛获奖成果数量
        # achievement_type=4 专指竞赛获奖，与普通成果分开统计（归档页“获奖”列）
        item.award_count = db.query(func.count(ProjAchievement.id)).filter(
            ProjAchievement.project_id == obj.id,
            ProjAchievement.achievement_type == 4,
            ProjAchievement.is_deleted == 0,
        ).scalar() or 0
        # ---------- 项目附件 ----------
        # 加载项目附件
        from app.models.user import SysAttachment
        atts = db.query(SysAttachment).filter(
            SysAttachment.biz_type == "project",
            SysAttachment.biz_id == obj.id,
            SysAttachment.is_deleted == 0,
        ).order_by(SysAttachment.created_at.desc()).all()
        item.attachments = [{
            "id": a.id, "file_name": a.file_name, "file_size": a.file_size,
            "file_type": a.file_type, "uploader_name": a.uploader_name,
            "download_count": a.download_count, "created_at": a.created_at,
            "download_url": f"/api/files/download/{a.id}",
            "preview_url": f"/api/files/preview/{a.id}",
        } for a in atts]
        return item

    @staticmethod
    def _assign_project_no(db: Session, obj: ProjProject) -> None:
        """分配唯一项目编号：先按当年最大编号+1，撞唯一键时序号递增重试（最多5次）。
        在 SAVEPOINT 内 flush，冲突回滚到保存点后仅重试编号，不影响已构建的其他待写数据。

        参数:
            db: 事务会话
            obj: 待落库的项目对象（方法内直接写入 project_no）
        异常:
            DataConflictException：连续 5 次仍编号冲突（高并发极端场景），由上层提示重试
        注意:
            - 编号按“年份”分段（date.today().year），跨年自然换段；
            - begin_nested() 生成 SAVEPOINT，保证捕获 IntegrityError 后 Session 仍可继续使用；
            - 方法不 commit，事务边界由调用方（create/submit）控制。
        """
        year = date.today().year
        candidate = ProjectCRUD.generate_project_no(db, year)
        for _ in range(5):
            obj.project_no = candidate
            try:
                with db.begin_nested():
                    db.flush()
                return
            except IntegrityError:
                # 唯一键冲突：仅在保存点内回滚，序号 +1 后重试
                candidate = ProjectCRUD.bump_project_no(candidate)
        raise DataConflictException(message="项目编号生成冲突，请重试")

    @staticmethod
    def _sync_current_approver(db: Session, project: ProjProject) -> None:
        """根据项目阶段刷新"当前审批人"字段（供项目详情展示审批进度）：
        - 待指导教师确认(12)：指导教师
        - 待学院初审(1) / 待分配评审专家(13)：该学院的管理员
        - 其他阶段（待校级复审/专家评审/已立项及之后）：无单一审批人，置空

        参数:
            db: 事务会话
            project: 项目对象，方法内直接修改 current_approver_id（不 commit）
        注意:
            该字段仅用于展示“卡在谁那里”，不是权限判断依据；
            学院管理员可能有多人，取 id 最小的一个作为展示代表（排序保证稳定）。
        """
        if project.status == PROJECT_STATUS_PENDING_TEACHER:
            project.current_approver_id = project.teacher_id
        elif project.status in (PROJECT_STATUS_PENDING_COLLEGE, PROJECT_STATUS_PENDING_EXPERT_ASSIGN):
            admin = db.query(SysUser).filter(
                SysUser.role == RoleEnum.ADMIN,
                SysUser.college_id == project.college_id,
                SysUser.is_deleted == 0,
            ).order_by(SysUser.id).first()
            project.current_approver_id = admin.id if admin else None
        else:
            project.current_approver_id = None

    @staticmethod
    def _derive_competition_session(db: Session, data: Dict[str, Any]) -> None:
        """根据所选比赛回填/刷新「参赛届次」（冗余存储，便于比赛下架后仍可追溯届次）。
        仅当 data 中显式含 competition_id 时处理；未选择比赛则置空。

        参数:
            db: 事务会话
            data: 待写入项目的字段字典（原地修改 competition_session）
        注意:
            用 ``"competition_id" not in data`` 判断“本次是否修改了比赛”，
            避免局部更新（PATCH）时把已有届次误清空。
        """
        if "competition_id" not in data:
            return
        cid = data.get("competition_id")
        if not cid:
            data["competition_session"] = None
            return
        from app.models import Competition
        comp = db.query(Competition).filter(
            Competition.id == cid, Competition.is_deleted == 0
        ).first()
        data["competition_session"] = comp.session if comp else None

    @staticmethod
    def _assert_competition_submittable(db: Session, competition_id: Optional[int]) -> None:
        """提交审核前校验参赛比赛：必须存在且处于报名中/进行中

        参数:
            competition_id: 项目选择的比赛 ID
        异常:
            ParamValidateException：比赛不存在/已删除，或状态不在 (1 报名中, 2 进行中)
        注意:
            草稿创建允许先选比赛，真正卡口在“提交审核”时；已结束比赛不能再报。
        """
        from app.models import Competition
        comp = db.query(Competition).filter(
            Competition.id == competition_id, Competition.is_deleted == 0
        ).first()
        if not comp:
            raise ParamValidateException(message="所选比赛不存在或已被删除，请重新选择")
        if comp.status not in (1, 2):
            raise ParamValidateException(message="所选比赛已结束或未开放报名，请重新选择")

    @staticmethod
    def _assert_competition_entry_unique(
        db: Session,
        competition_id: Optional[int],
        leader_id: int,
        member_ids: Optional[List[int]] = None,
        exclude_project_id: Optional[int] = None,
    ) -> None:
        """同一比赛的申报名额校验：
        - 每名负责人仅可申报 1 个有效项目；
        - 每名学生（含团队成员）仅可参与 1 个项目；
        - 草稿/已驳回/已撤销不占用名额。

        参数:
            competition_id: 比赛 ID；为空则不做名额限制（历史/无比赛项目）
            leader_id: 本次申报的负责人学生 ID
            member_ids: 本次申报的团队成员学生 ID 列表
            exclude_project_id: 编辑/重提时排除自身项目，避免“和自己冲突”
        异常:
            ParamValidateException：负责人已申报/已参与，或某个团队成员已被占用
        注意:
            校验基于“当前有效项目集合”，不依赖数据库唯一索引；
            并发提交的极端情况下仍需唯一索引/事务锁兜底（见模块头部约束）。
        """
        if not competition_id:
            return
        # 1. 取出该比赛下所有“占用名额”的项目（软删与三种释放状态除外）
        q = db.query(ProjProject).filter(
            ProjProject.competition_id == competition_id,
            ProjProject.is_deleted == 0,
            ProjProject.status.notin_(ProjectService.NON_OCCUPYING_STATUSES),
        )
        if exclude_project_id:
            q = q.filter(ProjProject.id != exclude_project_id)
        occupied = q.all()
        if not occupied:
            return

        # 学生ID -> (占用名额的项目名称, 是否项目负责人)
        project_names = {p.id: p.project_name for p in occupied}
        taken: Dict[int, Tuple[str, bool]] = {
            p.leader_id: (p.project_name, True) for p in occupied
        }
        # 2. 团队成员同样占用名额：先收集，再与负责人一起判断
        members = db.query(ProjTeamMember).filter(
            ProjTeamMember.project_id.in_(list(project_names)),
            ProjTeamMember.is_deleted == 0,
        ).all()
        for tm in members:
            taken.setdefault(tm.student_id, (project_names.get(tm.project_id, ""), False))

        # 3. 负责人校验：先判断“作为负责人”还是“作为成员”，提示语不同
        if leader_id in taken:
            name, as_leader = taken[leader_id]
            if as_leader:
                raise ParamValidateException(
                    message=f"您已在本次比赛中申报项目「{name}」，"
                            "同一比赛每人仅可申报 1 个有效项目（草稿/已驳回/已撤销不计）"
                )
            raise ParamValidateException(
                message=f"您已在本次比赛中参与项目「{name}」，"
                        "同一比赛每名学生仅可参与 1 个项目"
            )

        # 4. 团队成员校验：逐个给出具体学生姓名，便于用户定位
        for mid in member_ids or []:
            if mid not in taken:
                continue
            name, _ = taken[mid]
            student = UserCRUD.get_by_id(db, mid)
            student_name = student.real_name if student else str(mid)
            raise ParamValidateException(
                message=f"团队成员「{student_name}」已在本次比赛中参与项目「{name}」，"
                        "同一比赛每名学生仅可参与 1 个项目"
            )

    @staticmethod
    def _is_eliminated(db: Session, project: ProjProject) -> bool:
        """是否「落选」：在指导教师确认之后的环节（学院/校级/专家）被驳回。
        这类驳回为终局，任何角色都不得再修改或重新提交；
        仅「指导教师驳回」允许学生改后重提。

        参数:
            project: 项目对象
        返回:
            True = 落选（终局）；False = 未被后置环节驳回
        注意:
            教师阶段(stage=0)的驳回不在此列表，因此教师驳回后仍可重提；
            result=3（修改后重提）在后置环节同样视为落选，避免绕过审核。
        """
        return db.query(ProjReview.id).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage.in_(
                (REVIEW_STAGE_COLLEGE, REVIEW_STAGE_UNIVERSITY, REVIEW_STAGE_EXPERT)
            ),
            ProjReview.review_result.in_((REVIEW_RESULT_REJECT, REVIEW_RESULT_MODIFY)),
            ProjReview.is_deleted == 0,
        ).first() is not None

    @staticmethod
    def _check_edit_permission(db: Session, project: ProjProject, operator: SysUser) -> None:
        """编辑权限：
        - 草稿状态(0)：仅项目负责人(学生)可编辑
        - 已驳回状态(10)：仅项目负责人可编辑（指导教师驳回后由学生修改重提）；「落选」项目不可编辑
        - 真超级管理员可编辑全校项目；学院管理员仅可编辑本院已驳回项目
        - 指导教师、专家不可编辑项目

        参数:
            db: 事务会话（用于判断是否落选）
            project: 项目对象
            operator: 当前操作人
        异常:
            PermissionDeniedException：无编辑权限 / 项目已落选 / 状态不在可编辑范围
        注意:
            该方法同时被 update 与 submit 复用；它只管“谁能改”，不校验字段合法性。
        """
        # 落选（学院/校级/专家驳回）为终局，任何角色不可再修改
        if project.status == PROJECT_STATUS_REJECTED and ProjectService._is_eliminated(db, project):
            raise PermissionDeniedException(message="该项目已落选，不可再修改")
        # 分级判断
        if is_super_admin(operator):
            # 超级管理员也不允许编辑草稿（草稿仅学生可见可编辑）
            if project.status == PROJECT_STATUS_DRAFT:
                raise PermissionDeniedException(message="草稿项目仅项目负责人可编辑")
            return
        if is_college_admin(operator):
            # 学院管理员：仅本院已驳回项目可编辑
            if project.status == PROJECT_STATUS_DRAFT:
                raise PermissionDeniedException(message="草稿项目仅项目负责人可编辑")
            if operator.college_id and project.college_id and operator.college_id != project.college_id:
                raise PermissionDeniedException(message="学院管理员仅可编辑本院项目")
            if project.status != 10:
                raise PermissionDeniedException(message="当前状态不可修改，如有需要请先撤回")
            return
        # 普通教师 / 学生：仅项目负责人本人可编辑
        if project.status not in (PROJECT_STATUS_DRAFT, 10):
            raise PermissionDeniedException(message="当前状态不可修改，如有需要请先撤回")
        if project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可编辑本项目")

    # ========== 列表 / 详情 ==========
    @staticmethod
    def paginate(db: Session, pager: PaginationParams, params: ProjectQueryParams,
                 data_scope: DataScope) -> Tuple[List[ProjectListItem], int]:
        """项目分页列表：按查询条件 + 角色数据权限过滤。

        参数:
            pager: 分页与排序参数（offset/limit/order_by/order_dir）
            params: 关键字、类型、级别、学院、负责人、教师、状态、年份等筛选条件
            data_scope: 角色数据权限（超管全校/学院本院/教师本人/学生本人/专家被分配）
        返回:
            (列表项, 总数)；总数用于前端分页器
        注意:
            列表项里的学院名、比赛名、专家进度、获奖数全部批量预取，
            禁止在循环里逐条查库（N+1）；软删过滤由 ProjectCRUD.paginate 统一处理。
        """
        # ---------- 主查询：由 CRUD 统一拼接筛选条件与数据权限 ----------
        items, total = ProjectCRUD.paginate(
            db,
            offset=pager.offset,
            limit=pager.limit,
            keyword=params.keyword,
            project_type=params.project_type,
            project_level=params.project_level,
            college_id=params.college_id,
            leader_id=params.leader_id,
            teacher_id=params.teacher_id,
            status=params.status,
            start_year=params.start_year,
            end_year=params.end_year,
            data_scope=data_scope,
            order_by=pager.order_by or "created_at",
            order_dir=pager.order_dir,
        )
        # ---------- 批量预取学院名称（避免 N+1） ----------
        # 批量查学院名称（避免N+1）
        college_ids = list({i.college_id for i in items if i.college_id})
        college_map = {}
        if college_ids:
            from app.models import SysCollege
            colleges = db.query(SysCollege).filter(SysCollege.id.in_(college_ids)).all()
            college_map = {c.id: c.college_name for c in colleges}
        # ---------- 批量预取比赛名称（避免 N+1） ----------
        # 批量查比赛名称（避免N+1）
        competition_ids = list({i.competition_id for i in items if i.competition_id})
        competition_map = {}
        if competition_ids:
            from app.models import Competition
            competitions = db.query(Competition).filter(Competition.id.in_(competition_ids)).all()
            competition_map = {c.id: c.title for c in competitions}
        result = []
        for obj in items:
            it = ProjectService._to_list_item(obj)
            # 用批量结果覆盖单条兜底查询，保证列表页不产生额外 SQL
            if it.college_id and college_map.get(it.college_id):
                it.college_name = college_map[it.college_id]
            if it.competition_id and competition_map.get(it.competition_id):
                it.competition_name = competition_map[it.competition_id]
            result.append(it)
        # ---------- 批量统计：专家分配/已评审/获奖数/落选标记 ----------
        # 批量查已分配专家数（review_stage=3 专家评审阶段）
        if items:
            project_ids = [p.id for p in items]
            # 已分配专家数 = 专家阶段记录总数（占位行也算“已分配”，但不代表已评）
            counts = db.query(
                ProjReview.project_id,
                func.count(ProjReview.id).label("cnt")
            ).filter(
                ProjReview.project_id.in_(project_ids),
                ProjReview.review_stage == 3,
                ProjReview.is_deleted == 0,
            ).group_by(ProjReview.project_id).all()
            cnt_map = {c.project_id: c.cnt for c in counts}
            # 已提交评审的专家数（>0 时专家名单锁定，前端据此禁用分配弹窗）
            # 过滤 result=99（占位）后才是“真正提交过意见”的专家数
            reviewed_counts = db.query(
                ProjReview.project_id,
                func.count(ProjReview.id).label("cnt")
            ).filter(
                ProjReview.project_id.in_(project_ids),
                ProjReview.review_stage == 3,
                ProjReview.review_result != 99,
                ProjReview.is_deleted == 0,
            ).group_by(ProjReview.project_id).all()
            reviewed_map = {c.project_id: c.cnt for c in reviewed_counts}
            # 批量查竞赛获奖成果数（归档页「获奖」列与筛选依赖）
            # achievement_type=4 是“竞赛获奖”，普通论文/专利等不计入该列
            award_counts = db.query(
                ProjAchievement.project_id,
                func.count(ProjAchievement.id).label("cnt")
            ).filter(
                ProjAchievement.project_id.in_(project_ids),
                ProjAchievement.achievement_type == 4,
                ProjAchievement.is_deleted == 0,
            ).group_by(ProjAchievement.project_id).all()
            award_map = {c.project_id: c.cnt for c in award_counts}
            for it in result:
                it.assigned_expert_count = cnt_map.get(it.id, 0)
                it.reviewed_expert_count = reviewed_map.get(it.id, 0)
                it.award_count = award_map.get(it.id, 0)
            # 批量标记「落选」（状态10 且在指导教师之后的环节被驳回 → 不可修改重提）
            # 用 distinct 一次取出所有落选项目 id，避免逐个调用 _is_eliminated 造成 N+1
            rejected_ids = [it.id for it in result if it.status == PROJECT_STATUS_REJECTED]
            eliminated_ids = set()
            if rejected_ids:
                elim_rows = db.query(ProjReview.project_id).filter(
                    ProjReview.project_id.in_(rejected_ids),
                    ProjReview.review_stage.in_(
                        (REVIEW_STAGE_COLLEGE, REVIEW_STAGE_UNIVERSITY, REVIEW_STAGE_EXPERT)
                    ),
                    ProjReview.review_result.in_((REVIEW_RESULT_REJECT, REVIEW_RESULT_MODIFY)),
                    ProjReview.is_deleted == 0,
                ).distinct().all()
                eliminated_ids = {r[0] for r in elim_rows}
            # 前端据此显示/隐藏“修改后重提”按钮
            for it in result:
                it.resubmittable = (
                    it.status == PROJECT_STATUS_REJECTED and it.id not in eliminated_ids
                )
        return result, total

    @staticmethod
    def paginate_announcement(db: Session, pager: PaginationParams,
                              params: ProjectQueryParams) -> Tuple[List[ProjectListItem], int]:
        """立项结果公示：已立项及之后阶段的项目，不做数据权限过滤，全校可见

        参数:
            pager: 分页参数
            params: 关键字/学院/年份筛选（不含状态，状态由方法硬编码）
        返回:
            (公示列表, 总数)
        注意:
            公示面向全校（甚至对外），因此必须严格限定状态白名单；
            草稿(0)、待教师确认(12)、审核中的项目绝不能出现在这里。
        """
        # 仅已立项(6)及之后：中期检查中(7)、待结题(8)、已结题(9)
        # 注意：12=待指导教师确认，绝不能纳入公示（否则未审核项目会被公开）
        approved_statuses = [6, 7, 8, 9]
        # data_scope=None：公示不做角色过滤；排序固定按提交时间倒序，最新立项优先展示
        items, total = ProjectCRUD.paginate(
            db,
            offset=pager.offset,
            limit=pager.limit,
            keyword=params.keyword,
            college_id=params.college_id,
            status_in=approved_statuses,
            start_year=params.start_year,
            end_year=params.end_year,
            data_scope=None,
            order_by="submit_time",
            order_dir="desc",
        )
        # 批量查学院名称
        college_ids = list({i.college_id for i in items if i.college_id})
        college_map = {}
        if college_ids:
            from app.models import SysCollege
            colleges = db.query(SysCollege).filter(SysCollege.id.in_(college_ids)).all()
            college_map = {c.id: c.college_name for c in colleges}
        result = []
        for obj in items:
            it = ProjectService._to_list_item(obj)
            if it.college_id and college_map.get(it.college_id):
                it.college_name = college_map[it.college_id]
            result.append(it)
        return result, total

    @staticmethod
    def get_detail(db: Session, project_id: int, operator: SysUser) -> ProjectDetailResponse:
        """项目详情（含数据权限校验）。

        参数:
            project_id: 项目主键
            operator: 当前操作人（决定草稿可见性与数据范围）
        返回:
            ProjectDetailResponse（含个性化结项/截止日字段）
        异常:
            ResourceNotFoundException：项目不存在（或已软删）
            PermissionDeniedException：草稿非学生 / 超出数据权限范围
        副作用:
            读取前先执行三类超期清扫，可能顺带把过期变更/中期/结题状态落库并 commit
        注意:
            查询顺序是先判存在、再判权限，因此无权用户可能感知“项目存在”；
            这是既有接口约定（前端依赖“不存在/无权限”区分提示），改动需同步前端。
        """
        # 顺带清扫超期未审的变更申请 / 中期报告 / 结项报告（自动作废，留档）
        # 为什么放在权限校验之前：状态需要先落到最新，后续展示/可操作性才准确
        ProjectService.sweep_expired_change_requests(db, [project_id])
        ProjectService.sweep_expired_midterm(db, project_id)
        ProjectService.sweep_expired_final(db, project_id)
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 草稿项目(0)仅学生（负责人/团队成员）可见，其他角色（管理员/教师/专家）一律不可见
        if obj.status == PROJECT_STATUS_DRAFT and operator.role != RoleEnum.STUDENT:
            raise PermissionDeniedException(message="草稿项目仅项目负责人可见")
        # ---------- 数据权限：构造 DataScope 并逐角色判定 ----------
        # 数据权限
        # 这里手工构造 DataScope（而非依赖注入）是为了在服务层内部复用同一套范围计算
        scope = DataScope.__new__(DataScope)
        scope.user = operator
        scope.db = db
        scope.role = operator.role
        scope.college_id = operator.college_id
        scope.user_id = operator.id
        scope.scope = scope._compute_scope()
        ok = False
        if scope.scope.get("all"):
            # 超级管理员/全局范围：直接放行
            ok = True
        elif scope.scope.get("is_student"):
            # 学生：负责人本人或团队成员（成员也能看项目详情，但不能编辑）
            if obj.leader_id == operator.id:
                ok = True
            else:
                from app.models import ProjTeamMember
                m = db.query(ProjTeamMember).filter(
                    ProjTeamMember.project_id == project_id,
                    ProjTeamMember.student_id == operator.id
                ).first()
                ok = m is not None
        elif scope.scope.get("teacher_user_ids"):
            # 教师：本人指导的项目，或本院项目（学院范围由 DataScope 提供）
            ok = obj.teacher_id == operator.id or \
                 (scope.scope.get("college_ids") and obj.college_id in scope.scope["college_ids"])
        elif scope.scope.get("college_ids"):
            # 学院管理员：仅本院
            ok = obj.college_id in scope.scope["college_ids"]
        elif scope.scope.get("expert_user_id"):
            # 专家：仅被分配到该项目（软删的分配记录不授予可见性）
            from app.models import ProjReview
            ok = db.query(ProjReview).filter(
                ProjReview.project_id == project_id,
                ProjReview.reviewer_id == operator.id,
                ProjReview.is_deleted == 0,  # 已取消的分配记录不再授予可见性
            ).first() is not None
        if not ok:
            raise PermissionDeniedException(message="无权查看该项目")
        return ProjectService._to_detail(db, obj, operator)

    # ========== 创建 / 修改 / 删除 ==========
    @staticmethod
    def create(db: Session, req: ProjectCreate, operator: SysUser,
               as_draft: bool = True) -> ProjectDetailResponse:
        """创建项目：
        - 学生：负责人=自己
        - 真超级管理员：可指定任意学院、任意负责人（演示代录用）
        - 学院管理员：仅能创建本院项目（college_id 自动锁定）

        参数:
            req: 创建请求（项目名、学院、教师、团队、预算、比赛、附件等）
            operator: 当前操作人
            as_draft: True 存草稿(0)；False 直接提交审核(12)并按提交口径校验
        返回:
            ProjectDetailResponse（含新项目 id、编号、状态等）
        副作用:
            写入 proj_project 及子表；直接提交时分配项目编号、写教师确认占位审核记录、
            绑定临时附件；最后 commit
        异常:
            PermissionDeniedException：身份不允许创建 / 越学院创建
            ParamValidateException：学院/教师/负责人/成员/必填项/比赛名额校验失败
            DataConflictException：项目编号冲突重试仍失败
        注意:
            as_draft=False 时的校验必须与 submit() 保持一致，
            否则会出现“创建即提交”绕过必填/名额限制的漏洞。
        """
        # ---------- 身份与学院归属 ----------
        if operator.role == RoleEnum.STUDENT:
            pass  # OK
        elif is_college_admin(operator):
            # 学院管理员：college_id 强制为本院，禁止越学院建项目
            if operator.college_id:
                if req.college_id and req.college_id != operator.college_id:
                    raise PermissionDeniedException(message="学院管理员仅可创建本院项目")
                req.college_id = operator.college_id
        elif not is_super_admin(operator):
            raise PermissionDeniedException(message="学生身份方可创建申报项目")

        # ---------- 基础外键与角色校验 ----------
        # 校验学院存在
        if not CollegeCRUD.get_by_id(db, req.college_id):
            raise ParamValidateException(message="所选学院不存在")
        # 校验指导教师存在且为教师角色
        if req.teacher_id:
            t = UserCRUD.get_by_id(db, req.teacher_id)
            if not t:
                raise ParamValidateException(message="指导教师不存在")
            if t.role not in (RoleEnum.TEACHER, RoleEnum.ADMIN):
                raise ParamValidateException(message="所选用户不是指导教师")

        data = req.model_dump()
        # 学生身份 => 默认自己是负责人
        # 同时用学生所属学院覆盖前端传值，防止伪造他人学院
        if operator.role == RoleEnum.STUDENT:
            data["leader_id"] = operator.id
            data["college_id"] = operator.college_id or data["college_id"]
        elif "leader_id" not in data or not data.get("leader_id"):
            raise ParamValidateException(message="管理员创建需额外指定负责人（通过扩展字段，此示例暂不支持）")

        # 校验负责人/团队成员存在，避免外键错误直接抛 500
        # 注意成员按 is_deleted=0 过滤，已删除用户不能继续作为成员
        if not UserCRUD.get_by_id(db, data["leader_id"]):
            raise ParamValidateException(message="项目负责人不存在")
        member_ids = [tm.student_id for tm in req.team_members]
        if member_ids:
            existing_ids = {
                uid for (uid,) in db.query(SysUser.id).filter(
                    SysUser.id.in_(member_ids), SysUser.is_deleted == 0
                ).all()
            }
            missing_ids = sorted(set(member_ids) - existing_ids)
            if missing_ids:
                raise ParamValidateException(
                    message="团队成员不存在：" + "、".join(str(i) for i in missing_ids)
                )

        # 指导教师须属于该项目所在学院（真超级管理员可跨院指定，用于演示代录）
        if data.get("teacher_id") and not is_super_admin(operator):
            t = UserCRUD.get_by_id(db, data["teacher_id"])
            if t and t.college_id != data.get("college_id"):
                raise ParamValidateException(message="指导教师不属于该项目所在学院")

        # ---------- 直接提交时的必填/比赛名额校验 ----------
        # 直接提交时，必须先校验必填项（与 submit 方法保持一致）
        if not as_draft:
            missing = []
            if not req.project_name:
                missing.append("项目名称")
            if not req.teacher_id:
                missing.append("指导教师")
            if not req.team_members or len(req.team_members) == 0:
                missing.append("团队成员(至少1人)")
            if not req.budgets or len(req.budgets) == 0:
                missing.append("预算明细")
            if not req.competition_id:
                missing.append("参赛比赛")
            if missing:
                raise ParamValidateException(message="提交前请完善以下必填项：" + "、".join(missing))
            # 比赛必须仍在报名/进行中；同一比赛名额不得重复占用
            ProjectService._assert_competition_submittable(db, req.competition_id)
            ProjectService._assert_competition_entry_unique(
                db, req.competition_id, data["leader_id"], member_ids
            )

        # ---------- 初始化状态与冗余字段 ----------
        # 草稿不写 submit_time；直接提交则记录当前时间，供公示排序/统计使用
        data["status"] = PROJECT_STATUS_DRAFT if as_draft else PROJECT_STATUS_PENDING_TEACHER
        if not as_draft:
            data["submit_time"] = datetime.now()
        # 根据所选比赛回填参赛届次
        ProjectService._derive_competition_session(db, data)

        # ---------- 落库与提交后的附属动作 ----------
        obj = ProjectCRUD.create(db, data)
        # 提交时自动生成编号（唯一键冲突自动递增重试）
        if not as_draft:
            ProjectService._assign_project_no(db, obj)
            ProjectService._sync_current_approver(db, obj)
            # 创建指导教师确认占位审核记录
            # 占位记录 result=99：让项目出现在教师待办中，但尚未产生正式审核结论
            if obj.teacher_id and not ReviewCRUD.exist_by_project_stage_reviewer(
                db, obj.id, REVIEW_STAGE_TEACHER, obj.teacher_id
            ):
                teacher = UserCRUD.get_by_id(db, obj.teacher_id)
                ReviewCRUD.create(db, {
                    "project_id": obj.id,
                    "review_stage": REVIEW_STAGE_TEACHER,
                    "reviewer_id": obj.teacher_id,
                    "reviewer_name": teacher.real_name if teacher else "",
                    "review_result": 99,
                    "review_comment": None,
                    "review_time": datetime.now(),
                })

        # 4. 关联临时附件（biz_id=0 的附件）到新项目（仅限本人上传的临时附件）
        # 三重限制（biz_type/biz_id=0/uploader_id）防止把他人或其他业务的附件“劫持”过来
        if req.attachment_ids:
            from app.models.user import SysAttachment
            db.query(SysAttachment).filter(
                SysAttachment.id.in_(req.attachment_ids),
                SysAttachment.biz_type == "project",
                SysAttachment.biz_id == 0,
                SysAttachment.uploader_id == operator.id,
                SysAttachment.is_deleted == 0,
            ).update({SysAttachment.biz_id: obj.id}, synchronize_session=False)

        db.commit()
        db.refresh(obj)
        return ProjectService._to_detail(db, obj, operator)

    @staticmethod
    def update(db: Session, project_id: int, req: ProjectUpdate, operator: SysUser) -> ProjectDetailResponse:
        """修改项目（局部更新，仅写入请求中显式传入的字段）。

        参数:
            project_id: 项目主键
            req: 更新请求；exclude_unset 保证未传字段不被覆盖
            operator: 当前操作人
        返回:
            更新后的项目详情
        异常:
            ResourceNotFoundException / PermissionDeniedException / ParamValidateException
        副作用:
            更新 proj_project 与附件绑定，commit
        注意:
            权限由 _check_edit_permission 统一判定；起止日期需要与库中旧值合并校验，
            不能只看请求里的字段，否则单独改一端可能产生 start > end。
        """
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 先判权限再校验字段：无权限用户不应通过错误信息探测数据合法性
        ProjectService._check_edit_permission(db, obj, operator)
        data = req.model_dump(exclude_unset=True)
        # 起止日期顺序校验：仅更新一端时，与库中另一端合并后再判断
        new_start = data.get("start_date", obj.start_date)
        new_end = data.get("end_date", obj.end_date)
        if new_start and new_end and new_start > new_end:
            raise ParamValidateException(message="开始日期不能晚于结束日期")
        # 若变更了参赛比赛，同步刷新参赛届次
        ProjectService._derive_competition_session(db, data)
        # ---------- 指导教师变更校验 ----------
        # 如果包含 teacher_id，校验
        if req.teacher_id:
            t = UserCRUD.get_by_id(db, req.teacher_id)
            if not t or t.role not in (RoleEnum.TEACHER, RoleEnum.ADMIN):
                raise ParamValidateException(message="指导教师无效")
            # 指导教师须属于该项目所在学院（真超级管理员可跨院指定，用于演示代录）
            if not is_super_admin(operator) and t.college_id != data.get("college_id", obj.college_id):
                raise ParamValidateException(message="指导教师不属于该项目所在学院")
        # ---------- 字段落库与附件绑定 ----------
        # attachment_ids 不直接写入项目表，单独处理附件关联
        attachment_ids = data.pop("attachment_ids", None)
        obj = ProjectCRUD.update(db, obj, data)
        # 关联临时附件（biz_id=0）到项目（仅限本人上传的临时附件）
        if attachment_ids:
            from app.models.user import SysAttachment
            db.query(SysAttachment).filter(
                SysAttachment.id.in_(attachment_ids),
                SysAttachment.biz_type == "project",
                SysAttachment.biz_id == 0,
                SysAttachment.uploader_id == operator.id,
                SysAttachment.is_deleted == 0,
            ).update({SysAttachment.biz_id: obj.id}, synchronize_session=False)
        db.commit()
        db.refresh(obj)
        return ProjectService._to_detail(db, obj, operator)

    @staticmethod
    def submit(db: Session, project_id: int, operator: SysUser) -> ProjectSubmitResponse:
        """草稿/已驳回 -> 提交审核。

        规则：
          - 首次提交、或「指导教师驳回」后重提：从「待指导教师确认」重走；
          - 指导教师确认之后的环节（学院/校级/专家）驳回即「落选」，不可重提。

        参数:
            project_id: 项目主键
            operator: 当前操作人（仅负责人/有编辑权限者可提交）
        返回:
            ProjectSubmitResponse（项目 id、目标状态 12、状态名、提示语含项目编号）
        异常:
            ResourceNotFoundException / PermissionDeniedException / ParamValidateException
        副作用:
            更新状态与提交时间、软删上一轮审核记录、重建教师占位记录、
            首次提交分配项目编号；commit
        注意:
            重提会“重置整条审核链”，而不是从被驳回的那一环继续——
            避免上一轮某环节的通过记录让新版本材料继承旧结论。
        """
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # ---------- 权限与状态门槛 ----------
        # 落选项目在 _check_edit_permission 中即被拒绝
        ProjectService._check_edit_permission(db, obj, operator)
        # 仅草稿(0)或已驳回(10)可提交；审核中/已立项不可重复提交
        if obj.status != PROJECT_STATUS_DRAFT and obj.status != 10:
            raise ParamValidateException(message="当前项目状态不可提交审核")
        # ---------- 必填项校验 ----------
        # 必填校验
        missing = []
        if not obj.project_name:
            missing.append("项目名称")
        if not obj.teacher_id:
            missing.append("指导教师")
        if not obj.team_members or len(obj.team_members) == 0:
            missing.append("团队成员(至少1人)")
        if not obj.budgets or len(obj.budgets) == 0:
            missing.append("预算明细")
        if not obj.competition_id:
            missing.append("参赛比赛")
        if missing:
            raise ParamValidateException(message="提交前请完善以下必填项：" + "、".join(missing))
        # ---------- 比赛窗口与名额校验 ----------
        # 比赛必须在报名/进行中；名额校验排除自身，避免重提时与自己冲突
        ProjectService._assert_competition_submittable(db, obj.competition_id)
        member_ids = [tm.student_id for tm in db.query(ProjTeamMember).filter(
            ProjTeamMember.project_id == obj.id,
            ProjTeamMember.is_deleted == 0,
        ).all()]
        ProjectService._assert_competition_entry_unique(
            db, obj.competition_id, obj.leader_id, member_ids, exclude_project_id=obj.id
        )

        # ---------- 重置状态与历史审核记录 ----------
        obj.submit_time = datetime.now()
        # 重提清除上一轮驳回原因，避免旧状态残留
        obj.reject_reason = None
        # 整条流程从「待指导教师确认」重走，清空上一轮审核记录
        # 软删而非物理删：保留审核轨迹，便于事后追责/统计
        obj.status = PROJECT_STATUS_PENDING_TEACHER
        db.query(ProjReview).filter(
            ProjReview.project_id == obj.id,
            ProjReview.is_deleted == 0,
        ).update({ProjReview.is_deleted: 1}, synchronize_session=False)

        # 刷新当前审批人（随目标状态：待学院初审→学院管理员；待校级复审/待专家评审→清空等）
        ProjectService._sync_current_approver(db, obj)

        # ---------- 编号与教师待办占位 ----------
        # 首次提交时生成项目编号（唯一键冲突自动递增重试）
        if obj.project_no:
            db.flush()
        else:
            ProjectService._assign_project_no(db, obj)

        # 创建指导教师确认占位审核记录，使指导教师在待审核列表中看到该项目
        # 若历史记录刚被软删，这里会重新创建一条，保证新一轮流程有完整轨迹
        if obj.teacher_id and not ReviewCRUD.exist_by_project_stage_reviewer(
            db, obj.id, REVIEW_STAGE_TEACHER, obj.teacher_id
        ):
            teacher = UserCRUD.get_by_id(db, obj.teacher_id)
            ReviewCRUD.create(db, {
                "project_id": obj.id,
                "review_stage": REVIEW_STAGE_TEACHER,
                "reviewer_id": obj.teacher_id,
                "reviewer_name": teacher.real_name if teacher else "",
                "review_result": 99,  # 占位=待评审
                "review_comment": None,
                "review_time": datetime.now(),
            })

        db.commit()
        status_name = PROJECT_STATUS_NAME.get(obj.status, "")
        return ProjectSubmitResponse(
            project_id=obj.id,
            status=obj.status,
            status_name=status_name,
            message=f"已提交，等待指导教师确认，项目编号：{obj.project_no}",
        )

    # ================= 结项验收：报告状态 / 检查清单 / 专家进度 =================
    # 设计要点：结项报告不复用项目字段，而是存成一条“占位审核记录”
    # （review_stage=4, review_result=99, review_comment 前缀 [结项报告]），
    # 这样报告与专家验收意见共用 proj_review，天然具备轮次/轨迹能力。
    FINAL_REPORT_PREFIX = "[结项报告] "

    @staticmethod
    def _strip_report_prefix(comment: Optional[str]) -> Optional[str]:
        """去掉结项报告正文的存储前缀，返回纯报告内容。

        参数:
            comment: 占位记录的 review_comment（可能带 ``[结项报告] `` 前缀）
        返回:
            去前缀后的正文；空值返回 None
        注意:
            只剥离一次前缀，历史数据若重复拼接也不会在这里递归处理。
        """
        if not comment:
            return None
        if comment.startswith(ProjectService.FINAL_REPORT_PREFIX):
            return comment[len(ProjectService.FINAL_REPORT_PREFIX):]
        return comment

    @staticmethod
    def _final_report_record(db: Session, project_id: int) -> Optional[ProjReview]:
        """结项报告占位记录（result=99）；其 review_time 同时标记「本轮验收」起点

        参数:
            project_id: 项目主键
        返回:
            最新一条结题占位记录，未提交过返回 None
        注意:
            取 id 最大的一条：重提会更新同一条占位记录，但历史脏数据可能有多条，
            以最新为准才能反映当前报告版本。
        """
        return db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.review_result == 99,
            ProjReview.is_deleted == 0,
        ).order_by(ProjReview.id.desc()).first()

    @staticmethod
    def _final_round_start(db: Session, project_id: int) -> Optional[datetime]:
        """本轮结题验收的起始时间 = 报告占位记录的提交时间。

        用途:
            专家可能对同一项目验收多轮（驳回→重提），用该时间过滤掉上一轮意见，
            保证进度/驳回原因/通过判定只反映“当前这一版报告”。
        返回:
            起始时间；未提交报告返回 None（此时不按时间过滤）
        """
        record = ProjectService._final_report_record(db, project_id)
        return record.review_time if record else None

    @staticmethod
    def assigned_expert_ids(db: Session, project_id: int) -> set:
        """被分配到该项目（专家评审阶段）的专家ID集合

        参数:
            project_id: 项目主键
        返回:
            set[int]；分配记录被软删的专家不会出现在集合中
        注意:
            这里只认 review_stage=3（专家评审）的分配记录；
            结题验收阶段(stage=4)的评审人沿用同一批专家，不重复分配。
        """
        rows = db.query(ProjReview.reviewer_id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.is_deleted == 0,
        ).all()
        return {r[0] for r in rows if r[0]}

    @staticmethod
    def final_latest_reviews(db: Session, project_id: int) -> Dict[int, ProjReview]:
        """本轮结题验收中每位专家最新的一条正式意见（占位记录不计）

        参数:
            project_id: 项目主键
        返回:
            {reviewer_id: ProjReview}；同一专家多条意见时只保留 id 最大（最新）
        注意:
            - result=99 是报告占位行，不是专家意见，必须排除；
            - 若存在本轮起点，则只统计 review_time >= 起点 的意见；
              老数据没有起点时退回“全部历史”，避免功能不可用。
        """
        start = ProjectService._final_round_start(db, project_id)
        q = db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.is_deleted == 0,
            ProjReview.review_result.isnot(None),
            ProjReview.review_result != 99,
        )
        if start is not None:
            q = q.filter(ProjReview.review_time >= start)
        latest: Dict[int, ProjReview] = {}
        # 按 id 升序覆盖写入 → 天然保留每位专家最后一条
        for row in q.order_by(ProjReview.id).all():
            latest[row.reviewer_id] = row
        return latest

    @staticmethod
    def final_review_stats(db: Session, project_id: int) -> Tuple[int, int]:
        """返回 (应参与验收专家数, 本轮已提交意见专家数)

        业务含义:
            应参与数取“被分配的专家集合”；已提交数取“集合内且有本轮意见”的专家数。
            取交集而不是直接数意见条数，可避免已取消分配的专家继续拉高进度。
        注意:
            若没有分配记录（历史项目），应参与数返回 0，已提交数退回全部意见人数，
            前端按“0/0”展示，不阻塞结题。
        """
        assigned = ProjectService.assigned_expert_ids(db, project_id)
        latest = ProjectService.final_latest_reviews(db, project_id)
        if assigned:
            return len(assigned), len(assigned & set(latest.keys()))
        return 0, len(latest)

    @staticmethod
    def _latest_final_review(db: Session, project_id: int) -> Optional[ProjReview]:
        """最近一次正式结题验收意见（任意轮次），用于展示驳回意见

        注意:
            与 final_latest_reviews 不同：这里不限轮次、不限专家，只取全局最新一条，
            仅用于“展示最近一次结论”的场景，不能用于进度统计。
        """
        return db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.is_deleted == 0,
            ProjReview.review_result.isnot(None),
            ProjReview.review_result != 99,
        ).order_by(ProjReview.id.desc()).first()

    @staticmethod
    def final_rejected_current_round(db: Session, project_id: int) -> bool:
        """本轮报告是否已被专家驳回（驳回后可直接修改重提，不受截止日限制）

        判定:
            最近一条正式意见非“通过(1)”，且该意见发生在本轮报告提交之后。
        业务原因:
            如果不放行，逾期后才被驳回的项目将永久无法重提，流程彻底卡死；
            但只放行“本轮被驳回”的情况，防止用历史驳回记录绕过新的截止日。
        """
        latest = ProjectService._latest_final_review(db, project_id)
        start = ProjectService._final_round_start(db, project_id)
        if not latest or latest.review_result == 1:
            return False
        return start is None or latest.review_time >= start

    @staticmethod
    def _final_condition_stats(db: Session, project: ProjProject) -> Tuple[bool, int, int]:
        """结项三条件统计：中期已通过 / 成果数 / 未结清报销单数

        参数:
            project: 项目对象
        返回:
            (中期是否通过, 成果数量, 未结清报销单数量)
        注意:
            1) 中期通过要求 midterm.status == 2（“已提交待审核”不算）；
            2) 成果统计排除软删；
            3) 未结清 = 状态既不是已完成(6) 也不是已驳回(7)，
               即仍在审批链路上（含草稿，需提交人完成或删除）。
        """
        midterm = MidtermCRUD.get_by_project(db, project.id)
        ach_count = db.query(func.count(ProjAchievement.id)).filter(
            ProjAchievement.project_id == project.id,
            ProjAchievement.is_deleted == 0,
        ).scalar() or 0
        pending_expense = db.query(func.count(ProjExpense.id)).filter(
            ProjExpense.project_id == project.id,
            ProjExpense.is_deleted == 0,
            ProjExpense.status.notin_([EXPENSE_STATUS_COMPLETED, EXPENSE_STATUS_REJECTED]),
        ).scalar() or 0
        return bool(midterm and midterm.status == 2), int(ach_count), int(pending_expense)

    @staticmethod
    def get_final_checklist(db: Session, project: ProjProject) -> List[dict]:
        """结项条件检查清单（前端展示；前 3 项为提交/验收硬性条件）

        参数:
            project: 项目对象
        返回:
            4 个字典项：midterm / achievement / expense / report，
            每项含 key、label、passed、detail，前端直接渲染勾选状态
        注意:
            第 4 项 report 只是“报告是否已提交”的展示，不是提交前置条件；
            真正的提交强校验见 _ensure_final_conditions（不含 report 自身）。
        """
        midterm_ok, ach_count, pending_expense = ProjectService._final_condition_stats(db, project)
        report_ok = ProjectService._final_report_record(db, project.id) is not None
        return [
            {
                "key": "midterm", "label": "中期检查已通过", "passed": midterm_ok,
                "detail": "中期检查已审核通过" if midterm_ok else "中期检查尚未通过",
            },
            {
                "key": "achievement", "label": "已登记项目成果", "passed": ach_count >= 1,
                "detail": f"已登记 {ach_count} 项成果" if ach_count else "至少需登记 1 项成果",
            },
            {
                "key": "expense", "label": "经费报销已结清", "passed": pending_expense == 0,
                "detail": "无未结清报销" if pending_expense == 0 else f"{pending_expense} 笔报销待审批",
            },
            {
                "key": "report", "label": "结项验收报告已提交", "passed": report_ok,
                "detail": "报告已提交" if report_ok else "尚未提交结项验收报告",
            },
        ]

    @staticmethod
    def _ensure_final_conditions(db: Session, project: ProjProject) -> None:
        """结项三条件校验（统一入口，供结项提交复用）：
        1) 中期检查报告已审核通过
        2) 至少登记 1 项项目成果
        3) 经费报销已全部结清（无处于审批中间态的报销单）

        参数:
            project: 项目对象
        异常:
            ParamValidateException：任一条件不满足，消息直接说明缺什么
        注意:
            三项都必须在“提交结项报告”时校验，而不是等到专家验收时才发现，
            否则专家会收到不满足结项条件的项目进行无效评审。
        """
        midterm_ok, ach_count, pending_expense = ProjectService._final_condition_stats(db, project)
        if not midterm_ok:
            raise ParamValidateException(message="结项前需先完成中期检查并通过审核")
        if ach_count < 1:
            raise ParamValidateException(message="结项前需至少登记 1 项项目成果")
        if pending_expense > 0:
            raise ParamValidateException(message="结项前需先完成全部经费报销的审批")

    @staticmethod
    def submit_final(db: Session, project_id: int, final_report: str,
                     attachment_ids: list, operator: SysUser) -> ProjectSubmitResponse:
        """提交结项验收报告：仅登记报告并进入待专家验收（状态保持 8待结题）。

        注意：已结题(9)只能由"被分配到该项目的专家"通过结题验收审核流转，
        项目负责人不得提交即自批，避免绕过专家结题验收。

        参数:
            project_id: 项目主键
            final_report: 结项报告正文（不能为空白）
            attachment_ids: 本次绑定的临时附件 id 列表（仅本人上传）
            operator: 当前操作人（负责人或超管代操作）
        返回:
            ProjectSubmitResponse（状态仍为 8，提示等待专家验收）
        异常:
            ResourceNotFoundException / PermissionDeniedException / ParamValidateException
        副作用:
            写入/更新结题占位审核记录（result=99）、绑定附件、清空 reject_reason；commit
        注意:
            状态不变是有意设计：报告提交与“已结题”解耦，防止学生自行把项目改成已结题。
        """
        from app.models import SysAttachment, ProjReview
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # ---------- 权限与状态门槛 ----------
        # 仅项目负责人本人可提交（真超级管理员可代操作）
        if not is_super_admin(operator) and obj.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可提交结项报告")
        if obj.status != 8:
            raise ParamValidateException(message="仅待结题状态可提交结项验收报告")
        # 截止日限制：驳回后的修改重提不受截止日限制，否则逾期驳回的项目将永久无法结项
        # 这就是 final_rejected_current_round 存在的唯一原因
        if (
            ProjectService.is_past_deadline(ProjectService.get_final_deadline(db, obj))
            and not ProjectService.final_rejected_current_round(db, obj.id)
        ):
            raise ParamValidateException(message="已超过结题报告提交截止日，无法提交结项验收报告")
        if not final_report or not final_report.strip():
            raise ParamValidateException(message="请填写结项验收报告")

        # ---------- 结项硬性条件 ----------
        # 结项三条件校验：中期已批 + 成果≥1 + 报销已结清
        ProjectService._ensure_final_conditions(db, obj)

        # 重新提交即开启新一轮验收：清除上一轮驳回标记，供专家重新验收
        # 注意：final_report_status 依赖 reject_reason 判断，这里清空才能从“驳回”回到“待验收”
        obj.reject_reason = None

        # ---------- 附件绑定 ----------
        # 关联结项附件（仅限本人上传的 project 临时附件，防止劫持他人/其他业务附件）
        if attachment_ids:
            db.query(SysAttachment).filter(
                SysAttachment.id.in_(attachment_ids),
                SysAttachment.biz_type == "project",
                SysAttachment.biz_id == 0,
                SysAttachment.uploader_id == operator.id,
                SysAttachment.is_deleted == 0,
            ).update({SysAttachment.biz_type: "project", SysAttachment.biz_id: obj.id},
                     synchronize_session=False)
        # ---------- 写/更新报告占位记录 ----------
        # 以占位记录(review_result=99)登记"结项验收报告已提交"，供专家结题验收时校验
        # 同一轮重提直接覆盖同一条记录，review_time 刷新为“本轮起点”
        existing = db.query(ProjReview).filter(
            ProjReview.project_id == obj.id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.review_result == 99,
            ProjReview.is_deleted == 0,
        ).first()
        if existing:
            existing.review_comment = f"[结项报告] {final_report}"
            existing.review_time = datetime.now()
        else:
            db.add(ProjReview(
                project_id=obj.id,
                review_stage=REVIEW_STAGE_FINAL,
                reviewer_id=operator.id,
                reviewer_name=operator.real_name or operator.username,
                review_result=99,  # 占位=报告已提交待专家验收
                review_comment=f"[结项报告] {final_report}",
                review_time=datetime.now(),
            ))
        db.commit()
        return ProjectSubmitResponse(
            project_id=obj.id,
            status=obj.status,
            status_name=PROJECT_STATUS_NAME.get(obj.status, ""),
            message="结项验收报告已提交，等待专家验收"
        )

    @staticmethod
    def withdraw_final(db: Session, project_id: int, operator: SysUser) -> ProjectSubmitResponse:
        """撤回结项验收报告提交：仅项目负责人本人（真超级管理员可代操作）。
        撤回后删除报告占位记录，项目仍停留在「待结题(8)」，可修改后重新提交。

        参数:
            project_id: 项目主键
            operator: 当前操作人
        返回:
            ProjectSubmitResponse（状态仍为 8，提示可修改后重提）
        异常:
            ResourceNotFoundException / PermissionDeniedException / ParamValidateException
        副作用:
            物理删除报告占位记录（不是软删）、commit
        注意:
            - 截止日后禁止撤回：撤回后将无法再次提交，会把项目永久卡在待结题；
            - 占位记录是专家验收的前置凭证，删除后专家无法验收，必须重新提交。
        """
        from app.models import ProjReview
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        if not is_super_admin(operator) and obj.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可撤回结项报告提交")
        if obj.status != 8:
            raise ParamValidateException(message="仅待结题状态可撤回结项报告提交")
        # 截止日校验：超过结题报告截止日不允许撤回，否则撤回后将无法再次提交而卡死流程
        if ProjectService.is_past_deadline(ProjectService.get_final_deadline(db, obj)):
            raise ParamValidateException(message="已超过结题报告提交截止日，无法撤回结项验收报告")
        # 只允许撤回“尚未被专家验收”的报告；已有正式意见则说明验收已开始
        placeholder = db.query(ProjReview).filter(
            ProjReview.project_id == obj.id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.review_result == 99,  # 占位=报告已提交待验收
            ProjReview.is_deleted == 0,
        ).first()
        if not placeholder:
            raise ParamValidateException(message="尚未提交结项验收报告，无需撤回")
        # 删除报告占位记录：专家结题验收前须存在该记录，撤回后需重新提交
        db.delete(placeholder)
        db.commit()
        return ProjectSubmitResponse(
            project_id=obj.id,
            status=obj.status,
            status_name=PROJECT_STATUS_NAME.get(obj.status, ""),
            message="结项验收报告已撤回，可修改后重新提交"
        )

    @staticmethod
    def withdraw(db: Session, project_id: int, operator: SysUser) -> None:
        """学生/负责人撤回项目（状态->草稿）

        参数:
            project_id: 项目主键
            operator: 当前操作人
        副作用:
            软删该项目全部审核记录、状态置 0、清空 reject_reason/current_approver_id；commit
        异常:
            ResourceNotFoundException / PermissionDeniedException / ParamValidateException
        注意:
            只允许在「待指导教师确认(12)」阶段撤回：一旦进入学院初审，
            审核人可能已开始工作，撤回会造成审核资源浪费与状态不一致。
        """
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 撤回权限分级：超管全校 / 学院管理员仅本院 / 学生仅本人负责
        if is_super_admin(operator):
            pass
        elif is_college_admin(operator):
            if not operator.college_id or obj.college_id != operator.college_id:
                raise PermissionDeniedException(message="学院管理员仅可撤回本院项目")
        elif operator.role == RoleEnum.STUDENT:
            if obj.leader_id != operator.id:
                raise PermissionDeniedException(message="仅负责人可撤回")
        else:
            raise PermissionDeniedException(message="无权限撤回该项目")
        # 仅在「待指导教师确认」阶段可撤回；进入学院初审(1)/校级复审(3)等后续环节后不可撤回
        if obj.status != PROJECT_STATUS_PENDING_TEACHER:
            raise ParamValidateException(message="仅『待指导教师确认』阶段可撤回，进入学院初审后不可撤回")
        # 清除该项目已产生的审核记录，使重新提交后可再次审核
        # 软删而不是物理删：保留撤回前的处理轨迹
        db.query(ProjReview).filter(
            ProjReview.project_id == obj.id,
            ProjReview.is_deleted == 0,
        ).update({ProjReview.is_deleted: 1}, synchronize_session=False)
        obj.status = PROJECT_STATUS_DRAFT
        # 撤回后清空驳回原因与当前审批人，回到干净的草稿态
        obj.reject_reason = None
        obj.current_approver_id = None
        db.commit()

    @staticmethod
    def delete(db: Session, project_id: int, operator: SysUser) -> None:
        """软删除项目：
        - 真超级管理员：全校任意项目
        - 学院管理员：仅本院项目
        - 学生：仅本人负责的草稿项目

        参数:
            project_id: 项目主键
            operator: 当前操作人
        副作用:
            级联软删所有子表（团队/审核/预算/报销/成果/中期/变更），项目 is_deleted=1；commit
        异常:
            ResourceNotFoundException / PermissionDeniedException
        注意:
            一律软删，不物理删除：统计、追溯与唯一性校验都依赖 is_deleted 过滤；
            删除后附件不在此处理（仍可通过 biz_id 追溯到已删项目，属于既有行为）。
        """
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # ---------- 权限分级 ----------
        if is_super_admin(operator):
            pass
        elif is_college_admin(operator):
            if not operator.college_id or obj.college_id != operator.college_id:
                raise PermissionDeniedException(message="学院管理员仅可删除本院项目")
        elif operator.role == RoleEnum.STUDENT:
            # 学生只能删自己的草稿，避免误删已进入流程的项目
            if obj.status != PROJECT_STATUS_DRAFT:
                raise PermissionDeniedException(message="仅草稿状态可删除，其他状态请联系管理员")
            if obj.leader_id != operator.id:
                raise PermissionDeniedException(message="仅负责人可删除草稿")
        else:
            raise PermissionDeniedException(message="无权限删除该项目")
        # ---------- 级联软删 ----------
        # 级联软删除所有子数据，避免报销/成果/预算/审核记录在列表与统计中残留
        from app.models import ProjTeamMember, ProjMidtermCheck, ProjChangeRequest
        for model in (ProjTeamMember, ProjReview, ProjBudget, ProjExpense,
                      ProjAchievement, ProjMidtermCheck, ProjChangeRequest):
            db.query(model).filter(
                model.project_id == obj.id, model.is_deleted == 0
            ).update({model.is_deleted: 1}, synchronize_session=False)
        obj.is_deleted = 1
        db.commit()

    # ========== 统计分析 ==========
    # 统计口径统一原则：
    #   1) 先应用 UI 筛选条件（学院/类型/年份），再应用角色数据权限；
    #   2) 所有口径都排除软删项目；
    #   3) “待审核”按角色定义不同，不能简单用 status 统一计数；
    #   4) 金额汇总使用 coalesce(sum, 0) 并转 Decimal，避免空集返回 None/浮点误差。
    @staticmethod
    def statistics_overview(db: Session, data_scope: DataScope,
                            college_id: Optional[int] = None,
                            project_type: Optional[int] = None,
                            start_year: Optional[int] = None,
                            end_year: Optional[int] = None,
                            ) -> ProjectStatisticsResponse:
        """项目概览统计（支持按学院/类型/立项年份过滤）

        参数:
            data_scope: 角色数据权限（决定统计范围与“待审核”定义）
            college_id: UI 筛选的学院
            project_type: UI 筛选的项目类别
            start_year/end_year: 按 created_at 年份过滤（含边界）
        返回:
            ProjectStatisticsResponse：总数/待审/立项/结题、预算与已用金额、
            立项率，以及类别/状态/经费科目三个分布
        注意:
            - total_budget/total_used 直接取项目表冗余汇总字段，不再二次汇总预算明细；
            - 立项率 = 已立项及以上 / (已立项及以上 + 已驳回)，分母为 0 时返回 0；
            - 各分布查询与总览使用同一套过滤+权限，保证数字能对上。
        """
        from app.models import ProjProject, ProjReview
        q = db.query(func.count(ProjProject.id)).filter(ProjProject.is_deleted == 0)
        # ---------- 待审核口径（按角色区分） ----------
        # 待审核数按角色区分：仅统计需要当前用户处理的项目
        scope = data_scope.scope
        if scope.get("is_student"):
            # 学生：自己名下“已驳回待修改重提”的项目
            q_pending = q.filter(ProjProject.status == 10, ProjProject.leader_id == data_scope.user_id)
        elif scope.get("teacher_user_ids"):
            # 教师：待自己确认(12)的项目
            q_pending = q.filter(ProjProject.status == 12, ProjProject.teacher_id == data_scope.user_id)
        elif scope.get("is_college_admin"):
            # 学院初审 + 本院项目的专家分配（待分配评审专家 13 同样需要管理员处理）
            q_pending = q.filter(
                ProjProject.status.in_([PROJECT_STATUS_PENDING_COLLEGE, PROJECT_STATUS_PENDING_EXPERT_ASSIGN]),
                ProjProject.college_id == data_scope.college_id,
            )
        elif scope.get("expert_user_id"):
            # 专家：被分配且处于待专家评审(5)的项目
            assigned_ids = db.query(ProjReview.project_id).filter(
                ProjReview.reviewer_id == data_scope.user_id,
                ProjReview.review_stage == 3,
                ProjReview.is_deleted == 0,
            ).distinct()
            q_pending = q.filter(ProjProject.status == 5, ProjProject.id.in_(assigned_ids))
        else:
            # 超管：待校级复审 + 待分配评审专家（两项都是超管的待办）
            q_pending = q.filter(
                ProjProject.status.in_([PROJECT_STATUS_PENDING_UNIVERSITY, PROJECT_STATUS_PENDING_EXPERT_ASSIGN])
            )
        # 已立项及以上（6/7/8/9）；已结题仅 9
        q_approved = q.filter(ProjProject.status.in_([6, 7, 8, 9]))
        q_finished = q.filter(ProjProject.status == 9)

        def apply_filters_and_scope(query):
            """在给定查询上叠加“软删 + UI 筛选 + 角色数据权限”。"""
            # 所有统计口径都排除软删除项目（含预算/经费汇总查询）
            query = query.filter(ProjProject.is_deleted == 0)
            # 1) 用户前端 UI 显式选中的筛选条件
            if college_id is not None:
                query = query.filter(ProjProject.college_id == college_id)
            if project_type is not None:
                query = query.filter(ProjProject.project_type == project_type)
            if start_year is not None:
                # created_at 年份 >= start_year
                query = query.filter(extract("year", ProjProject.created_at) >= start_year)
            if end_year is not None:
                # created_at 年份 <= end_year
                query = query.filter(extract("year", ProjProject.created_at) <= end_year)
            # 2) 角色数据权限范围
            if data_scope.scope.get("all"):
                return query
            if data_scope.scope.get("college_ids"):
                return query.filter(ProjProject.college_id.in_(data_scope.scope["college_ids"]))
            if data_scope.scope.get("is_student"):
                return query.filter(ProjProject.leader_id == data_scope.user_id)
            if data_scope.scope.get("teacher_user_ids"):
                return query.filter(ProjProject.teacher_id.in_(data_scope.scope["teacher_user_ids"]))
            if data_scope.scope.get("expert_user_id"):
                expert_assigned = db.query(ProjReview.project_id).filter(
                    ProjReview.reviewer_id == data_scope.user_id,
                    ProjReview.review_stage == 3,
                    ProjReview.is_deleted == 0,
                ).distinct()
                return query.filter(ProjProject.id.in_(expert_assigned))
            # 未知角色：不加范围（依赖上游 DataScope 已给出正确 scope）
            return query

        # ---------- 核心指标 ----------
        total = apply_filters_and_scope(q.with_entities(func.count(ProjProject.id))).scalar() or 0
        pending = apply_filters_and_scope(q_pending.with_entities(func.count(ProjProject.id))).scalar() or 0
        approved = apply_filters_and_scope(q_approved.with_entities(func.count(ProjProject.id))).scalar() or 0
        finished = apply_filters_and_scope(q_finished.with_entities(func.count(ProjProject.id))).scalar() or 0
        # 金额取项目表冗余汇总；coalesce 保证空集返回 0 而不是 None
        total_budget = apply_filters_and_scope(db.query(func.coalesce(func.sum(ProjProject.budget_amount), 0))).scalar() or 0
        total_used = apply_filters_and_scope(db.query(func.coalesce(func.sum(ProjProject.used_amount), 0))).scalar() or 0

        rate = 0.0
        # 立项率：在相同过滤范围下，已立项及以上 / (已立项及以上 + 已驳回)
        denied = apply_filters_and_scope(db.query(func.count(ProjProject.id))
                                         .filter(ProjProject.status == 10)).scalar() or 0
        rate = round((approved / (approved + denied) * 100.0), 2) if (approved + denied) > 0 else 0.0

        # ===== 项目类别分布（真实数据）=====
        type_rows = apply_filters_and_scope(db.query(
            ProjProject.project_type, func.count(ProjProject.id)
        ).group_by(ProjProject.project_type)).all()
        category_dist = [
            {"name": ProjectCRUD.PROJECT_TYPE_NAME.get(int(r[0]), "其他"), "value": int(r[1] or 0)}
            for r in type_rows
        ]

        # ===== 项目状态分布（真实数据，用于状态饼图 + 桑基图）=====
        # 额外带 status 原值，前端桑基图需要按状态码连接流程节点
        status_rows = apply_filters_and_scope(db.query(
            ProjProject.status, func.count(ProjProject.id)
        ).group_by(ProjProject.status)).all()
        status_dist = [
            {"name": PROJECT_STATUS_NAME.get(int(r[0]), f"状态{r[0]}"), "value": int(r[1] or 0), "status": int(r[0])}
            for r in status_rows
        ]

        # ===== 经费科目使用分布（真实数据，从 proj_budget 汇总 used_amount）=====
        # 注意这里 join 项目表后会再应用一次项目级筛选/权限，且预算明细自身也要 is_deleted=0
        budget_rows = apply_filters_and_scope(db.query(
            ProjBudget.budget_item,
            func.coalesce(func.sum(ProjBudget.used_amount), 0).label("used")
        ).join(ProjProject, ProjBudget.project_id == ProjProject.id)
            .filter(ProjBudget.is_deleted == 0)).group_by(ProjBudget.budget_item).all()
        budget_by_category = [
            {"name": str(r[0]), "amount": float(r[1] or 0)}
            for r in budget_rows
        ]

        return ProjectStatisticsResponse(
            total_projects=total,
            pending_review=pending,
            approved_projects=approved,
            finished_projects=finished,
            total_budget=Decimal(str(total_budget)),
            total_used=Decimal(str(total_used)),
            approval_rate=rate,
            category_dist=category_dist,
            status_dist=status_dist,
            budget_by_category=budget_by_category,
        )

    @staticmethod
    def _apply_scope_to_query(db: Session, query, data_scope: DataScope):
        """把数据权限范围应用到查询；无任何数据范围时返回空结果集（避免默认放行全校）

        参数:
            query: 已含业务过滤条件的 SQLAlchemy 查询（列需包含 ProjProject）
            data_scope: 角色数据权限
        返回:
            叠加了范围过滤的查询
        注意:
            兜底 ``id == -1`` 是“默认拒绝”策略：若 DataScope 未识别出任何角色，
            宁可返回空数据，也不能悄悄放开成全校可见。
        """
        from app.models import ProjProject, ProjReview
        scope = data_scope.scope
        if scope.get("all"):
            return query
        if scope.get("college_ids"):
            return query.filter(ProjProject.college_id.in_(scope["college_ids"]))
        if scope.get("is_student"):
            return query.filter(ProjProject.leader_id == data_scope.user_id)
        if scope.get("teacher_user_ids"):
            return query.filter(ProjProject.teacher_id.in_(scope["teacher_user_ids"]))
        if scope.get("expert_user_id"):
            expert_assigned = db.query(ProjReview.project_id).filter(
                ProjReview.reviewer_id == data_scope.user_id,
                ProjReview.review_stage == 3,
                ProjReview.is_deleted == 0,
            ).distinct()
            return query.filter(ProjProject.id.in_(expert_assigned))
        return query.filter(ProjProject.id == -1)

    @staticmethod
    def trend_by_month(db: Session, start_year: int, end_year: int,
                       data_scope: DataScope) -> List[StatisticsTrendItem]:
        """按月统计申报/立项趋势（ECharts适配）

        参数:
            start_year/end_year: 统计年份区间（含边界，按 created_at）
            data_scope: 角色数据权限
        返回:
            按年月升序的 StatisticsTrendItem 列表，period 形如 2026-03
        注意:
            approved_count 用 case 求和：状态 6/7/8/9 记为已立项，
            与列表/总览的“已立项及以上”口径保持一致；
            只返回“有数据”的月份，前端自行补齐空月份即可。
        """
        from app.models import ProjProject, ProjReview
        q = db.query(
            extract("year", ProjProject.created_at).label("y"),
            extract("month", ProjProject.created_at).label("m"),
            func.count(ProjProject.id).label("apply_count"),
            func.sum(case((ProjProject.status.in_([6, 7, 8, 9]), 1), else_=0)).label("approved_count"),
        ).filter(
            ProjProject.is_deleted == 0,
            extract("year", ProjProject.created_at).between(start_year, end_year),
        )
        # 按数据权限范围过滤（学生/教师/专家不得看到全校趋势）
        if not data_scope.scope.get("all"):
            q = ProjectService._apply_scope_to_query(db, q, data_scope)
        q = q.group_by("y", "m").order_by("y", "m")
        rows = q.all()
        return [
            StatisticsTrendItem(
                period=f"{int(r.y):04d}-{int(r.m):02d}",
                apply_count=int(r.apply_count or 0),
                approved_count=int(r.approved_count or 0),
            )
            for r in rows
        ]

    @staticmethod
    def college_breakdown(db: Session, data_scope: DataScope,
                          college_id: Optional[int] = None,
                          project_type: Optional[int] = None,
                          start_year: Optional[int] = None,
                          end_year: Optional[int] = None) -> List[CollegeStatisticsItem]:
        """各学院统计数据（雷达图/热力图/学院立项率柱状图），支持与总览一致的筛选条件

        参数:
            data_scope: 角色数据权限（决定能看到哪些学院）
            college_id/project_type/start_year/end_year: 与总览一致的 UI 筛选
        返回:
            每个学院一条 CollegeStatisticsItem：项目数/立项/结题/预算/已用/
            立项率/成果数/专家平均分
        注意:
            - 学院列表先按权限收敛，再逐学院做聚合查询；
            - 平均分只统计 score 非空的评审记录（未打分不计入分母）；
            - 无学院归属的受限角色返回空列表，不展示任何学院统计。
        """
        from app.models import SysCollege, ProjReview

        # 学院列表（按数据权限过滤）：超管全校；学院管理员限本院；学生/教师/专家仅本人所属学院
        colleges = CollegeCRUD.list_all(db)
        scope = data_scope.scope
        if not scope.get("all"):
            if scope.get("college_ids"):
                allowed = set(scope["college_ids"])
                colleges = [c for c in colleges if c.id in allowed]
            elif data_scope.college_id:
                colleges = [c for c in colleges if c.id == data_scope.college_id]
            else:
                # 无学院归属的受限角色 → 不展示任何学院统计
                colleges = []
        # UI 再按单个学院过滤（用于“只看某学院”的钻取）
        if college_id:
            colleges = [c for c in colleges if c.id == college_id]

        def base_cond(col) -> list:
            """与总览统计一致的筛选条件（学院 + 类别 + 年份）"""
            # 每个学院的基础条件都从 is_deleted=0 开始，避免已删项目进入任何指标
            cond = [ProjProject.is_deleted == 0, ProjProject.college_id == col.id]
            if project_type is not None:
                cond.append(ProjProject.project_type == project_type)
            if start_year is not None:
                cond.append(extract("year", ProjProject.created_at) >= start_year)
            if end_year is not None:
                cond.append(extract("year", ProjProject.created_at) <= end_year)
            return cond

        result: List[CollegeStatisticsItem] = []
        for col in colleges:
            # 项目规模指标
            q = db.query(ProjProject).filter(*base_cond(col))

            total = q.count()
            approved = q.filter(ProjProject.status.in_([6, 7, 8, 9])).count()
            finished = q.filter(ProjProject.status == 9).count()
            denied = q.filter(ProjProject.status == 10).count()
            # 金额指标：取项目表冗余字段，coalesce 防 None
            budget = db.query(func.coalesce(func.sum(ProjProject.budget_amount), 0)).filter(
                *base_cond(col)).scalar() or 0
            used = db.query(func.coalesce(func.sum(ProjProject.used_amount), 0)).filter(
                *base_cond(col)).scalar() or 0

            # 成果数
            # join 项目表是为了复用同一套项目筛选；成果自身也要排除软删
            achievements = db.query(func.count(ProjAchievement.id)).join(
                ProjProject, ProjAchievement.project_id == ProjProject.id
            ).filter(
                *base_cond(col),
                ProjAchievement.is_deleted == 0,
            ).scalar() or 0

            # 专家评审平均分
            # 仅统计有分数的评审记录；未打分/占位记录不进入平均值
            avg_score_row = db.query(func.avg(ProjReview.score)).join(
                ProjProject, ProjReview.project_id == ProjProject.id
            ).filter(
                *base_cond(col),
                ProjReview.score.isnot(None),
            ).scalar()
            avg_score = round(float(avg_score_row or 0), 2)

            # 立项率口径与总览一致：已立项及以上 / (已立项及以上 + 已驳回)
            rate = round((approved / (approved + denied) * 100.0), 2) if (approved + denied) > 0 else 0.0

            result.append(CollegeStatisticsItem(
                college_id=col.id,
                college_name=col.college_name,
                total_projects=total,
                approved_projects=approved,
                finished_projects=finished,
                total_budget=Decimal(str(budget)),
                total_used=Decimal(str(used)),
                approval_rate=rate,
                achievements=int(achievements),
                avg_score=avg_score,
            ))

        return result


class AchievementService:
    """项目成果业务服务。

    负责成果的登记、修改、认定/撤销认定、删除及证明材料绑定。
    权限模型与项目不同：
      - 登记/编辑：项目负责人、该项目指导教师、本院学院管理员、超管；
      - 认定/撤销认定：项目指导教师、本院学院管理员、超管（负责人不得自认）；
      - 已认定成果对负责人“锁定”，必须先由可认定角色撤销后才能修改/删除，
        以保证认定结论与材料版本一一对应，避免事后偷改已认定材料。
    """

    # 可登记/编辑成果的项目阶段：已立项及之后
    # 业务含义：未立项项目没有成果归属，已撤销/已驳回项目也不应再新增成果
    EDITABLE_PROJECT_STATUSES = (6, 7, 8, 9)
    # 成果认定状态
    # 0 待认定（新增/修改后重置）、1 已认定（锁定负责人编辑）、2 不通过（需修改后重认）
    REVIEW_STATUS_NAME = {0: "待认定", 1: "已认定", 2: "不通过"}

    @staticmethod
    def _ensure_project_status(project: ProjProject) -> None:
        """校验项目处于可登记/编辑成果的阶段。

        异常:
            ParamValidateException：项目不在已立项(6)~已结题(9) 区间
        注意:
            只有“已立项及之后”才有成果归属；草稿/审核中/已撤销项目不允许登记。
        """
        if project.status not in AchievementService.EDITABLE_PROJECT_STATUSES:
            raise ParamValidateException(message="仅已立项及之后阶段可登记或编辑成果")

    @staticmethod
    def _ensure_permission(project: ProjProject, operator: SysUser, deny_message: str) -> None:
        """登记/编辑权限：超管全校；学院管理员限本院；项目负责人或该项目指导教师本人

        参数:
            project: 成果所属项目
            operator: 当前操作人
            deny_message: 兜底拒绝时的提示语（登记与编辑文案不同）
        异常:
            PermissionDeniedException：越学院 / 非负责人 / 非指导教师
        """
        if is_super_admin(operator):
            return
        if is_college_admin(operator):
            if not operator.college_id or project.college_id != operator.college_id:
                raise PermissionDeniedException(message="学院管理员仅可管理本院项目成果")
            return
        # 负责人不限制角色（理论上只能是学生）；指导教师必须是该项目的教师本人
        if project.leader_id == operator.id or (
            operator.role == RoleEnum.TEACHER and project.teacher_id == operator.id
        ):
            return
        raise PermissionDeniedException(message=deny_message)

    @staticmethod
    def _can_review(project: ProjProject, operator: SysUser) -> bool:
        """是否具备认定权限：超管、本院学院管理员、项目指导教师

        返回:
            True 表示可认定；False 表示不可（负责人即使是本院学生也不可自认）
        注意:
            该方法只做布尔判断，不抛异常；需要报错时用 _ensure_review_permission。
        """
        if is_super_admin(operator):
            return True
        if is_college_admin(operator):
            return bool(operator.college_id) and project.college_id == operator.college_id
        return operator.role == RoleEnum.TEACHER and project.teacher_id == operator.id

    @staticmethod
    def _ensure_review_permission(project: ProjProject, operator: SysUser) -> None:
        """成果认定权限：该项目指导教师、学院管理员、超级管理员（负责人不得自认）

        异常:
            PermissionDeniedException：不满足条件；学院管理员越院时给出更具体提示
        """
        if AchievementService._can_review(project, operator):
            return
        if is_college_admin(operator):
            raise PermissionDeniedException(message="学院管理员仅可认定本院项目成果")
        raise PermissionDeniedException(message="仅项目指导教师或管理员可认定成果")

    @staticmethod
    def _validate_publish_date(project: ProjProject, publish_date: Optional[date]) -> None:
        """成果日期须落在「项目开始日期 ~ 今天」区间内

        参数:
            project: 成果所属项目（提供 start_date）
            publish_date: 成果发表/获奖/授权日期，允许为空
        异常:
            ParamValidateException：晚于今天，或早于项目开始日期
        注意:
            不限制“项目结束日期”，因为结题后仍可能补录成果（如专利授权滞后）；
            只禁止“未来日期”和“项目开始前”两种明显不可能的情况。
        """
        if publish_date is None:
            return
        if publish_date > date.today():
            raise ParamValidateException(message="成果日期不能晚于今天")
        if project.start_date and publish_date < project.start_date:
            raise ParamValidateException(message=f"成果日期不能早于项目开始日期（{project.start_date}）")

    @staticmethod
    def _bind_attachments(db: Session, ach_id: int, attachment_ids: List[int], operator: SysUser) -> None:
        """把本人上传的临时证明材料（biz_type=achievement, biz_id=0）绑定到成果

        参数:
            ach_id: 成果主键
            attachment_ids: 待绑定附件 id（可为空）
            operator: 上传者本人
        注意:
            biz_id=0 代表“尚未归属”的临时附件；限定 uploader_id 防止绑定他人材料。
            不 commit，由调用方统一提交事务。
        """
        if not attachment_ids:
            return
        from app.models import SysAttachment
        db.query(SysAttachment).filter(
            SysAttachment.id.in_(attachment_ids),
            SysAttachment.biz_type == "achievement",
            SysAttachment.biz_id == 0,
            SysAttachment.uploader_id == operator.id,
            SysAttachment.is_deleted == 0,
        ).update({SysAttachment.biz_id: ach_id}, synchronize_session=False)

    @staticmethod
    def _review_map(db: Session, ach_ids: List[int]) -> Dict[int, ProjAchievementReview]:
        """批量取成果认定记录，避免列表接口 N+1。

        参数:
            ach_ids: 成果 id 列表
        返回:
            {achievement_id: ProjAchievementReview}；软删记录不返回
        注意:
            一条成果最多一条认定记录（业务上唯一），若历史脏数据有多条，
            这里以后查到的为准（未做排序），列表展示以最新写入为主。
        """
        if not ach_ids:
            return {}
        rows = db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id.in_(ach_ids),
            ProjAchievementReview.is_deleted == 0,
        ).all()
        return {r.achievement_id: r for r in rows}

    @staticmethod
    def _reset_review(db: Session, ach_id: int) -> ProjAchievementReview:
        """成果新增/修改后回到「待认定」，清空上一轮认定结论

        参数:
            ach_id: 成果主键
        返回:
            已重置（未 commit）的认定记录对象
        副作用:
            无记录时新建一条 status=0 的记录并 add 到 Session
        注意:
            调用方在 review() 中也会先调用本方法再写入认定结论，
            这样“认定”与“重置”共用同一套字段初始化，避免漏清字段。
        """
        row = db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id == ach_id
        ).first()
        if not row:
            row = ProjAchievementReview(achievement_id=ach_id, status=0)
            db.add(row)
        row.status = 0
        row.reviewer_id = None
        row.reviewer_name = None
        row.review_comment = None
        row.review_time = None
        # submit_time 记录“本次提交认定”的时间，用于排序/追踪
        row.submit_time = datetime.now()
        # 若之前被软删（成果删除后恢复场景），重置时必须复活记录
        row.is_deleted = 0
        return row

    @staticmethod
    def _to_response(db: Session, ach: ProjAchievement,
                     review: Optional[ProjAchievementReview] = None) -> AchievementResponse:
        """ORM -> 成果响应，附带证明材料与认定信息。

        参数:
            ach: 成果对象
            review: 认定记录；None 表示历史成果无认定数据
        返回:
            AchievementResponse（含附件下载/预览 URL、认定状态及意见）
        注意:
            历史成果若无认定记录按“已认定(1)”展示：这批数据早于认定功能上线，
            若显示“待认定”会让教师面对大量无意义待办。
        """
        from app.models import SysAttachment
        item = AchievementResponse.model_validate(ach)
        # 证明材料：按上传时间倒序，最新材料优先
        atts = db.query(SysAttachment).filter(
            SysAttachment.biz_type == "achievement",
            SysAttachment.biz_id == ach.id,
            SysAttachment.is_deleted == 0,
        ).order_by(SysAttachment.created_at.desc()).all()
        item.attachments = [{
            "id": a.id, "file_name": a.file_name, "file_size": a.file_size,
            "file_type": a.file_type, "uploader_name": a.uploader_name,
            "download_count": a.download_count, "created_at": a.created_at,
            "download_url": f"/api/files/download/{a.id}",
            "preview_url": f"/api/files/preview/{a.id}",
        } for a in atts]
        # 历史成果无认定记录，按「已认定」展示，避免全量显示为待认定
        item.review_status = review.status if review else 1
        item.review_status_name = AchievementService.REVIEW_STATUS_NAME.get(item.review_status, "")
        item.review_comment = review.review_comment if review else None
        item.reviewer_name = review.reviewer_name if review else None
        item.review_time = review.review_time if review else None
        return item

    @staticmethod
    def list_by_project(db: Session, project_id: int, operator: SysUser) -> List[AchievementResponse]:
        """项目成果列表（含可见性校验）。

        参数:
            project_id: 项目主键
            operator: 当前操作人
        返回:
            成果响应列表（按 CRUD 默认排序）
        异常:
            ResourceNotFoundException / PermissionDeniedException
        注意:
            这里复用 ProjectService.get_detail 做权限校验（草稿仅本人、教师限本院、
            专家限被分配），因此会触发一次详情组装开销，属于“以正确性优先”的取舍。
        """
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 权限校验：复用项目详情可见性规则（草稿仅本人/成员，教师限本院，专家限被分配）
        ProjectService.get_detail(db, project_id, operator)
        items = AchievementCRUD.list_by_project(db, project_id)
        reviews = AchievementService._review_map(db, [i.id for i in items])
        return [AchievementService._to_response(db, i, reviews.get(i.id)) for i in items]

    @staticmethod
    def create(db: Session, req: AchievementCreate, operator: SysUser) -> AchievementResponse:
        """登记一条项目成果。

        参数:
            req: 成果创建请求（project_id、标题、类型、日期、附件等）
            operator: 当前操作人
        返回:
            AchievementResponse（认定状态为“待认定”）
        异常:
            ResourceNotFoundException / PermissionDeniedException / ParamValidateException
        副作用:
            写 proj_achievement、绑定证明材料、创建待认定记录；给指导教师推送待认定通知；commit
        注意:
            登记人若是指导教师本人则不推送通知，避免自己通知自己。
        """
        obj = ProjectCRUD.get_by_id(db, req.project_id)
        if not obj:
            raise ResourceNotFoundException(message="所属项目不存在")
        # ---------- 阶段与权限 ----------
        AchievementService._ensure_project_status(obj)
        AchievementService._ensure_permission(obj, operator, "仅项目负责人、指导教师或管理员可登记成果")
        # ---------- 字段规范化与校验 ----------
        data = req.model_dump()
        # attachment_ids 不属于成果表字段，单独取出处理
        attachment_ids = data.pop("attachment_ids", []) or []
        AchievementService._validate_publish_date(obj, data.get("publish_date"))
        ach = AchievementCRUD.create(db, data)
        # ---------- 证明材料与认定记录 ----------
        AchievementService._bind_attachments(db, ach.id, attachment_ids, operator)
        # 新成果统一从“待认定”开始；已有记录也会被重置（理论上新建不会有）
        review = AchievementService._reset_review(db, ach.id)
        # 通知指导教师及时认定（登记人本人为教师时不重复通知）
        if obj.teacher_id and obj.teacher_id != operator.id:
            NotificationService.push(
                db, obj.teacher_id, "新成果待认定",
                f"项目「{obj.project_name}」登记了成果「{ach.title}」，请及时认定。",
                level=NOTICE_LEVEL_INFO, biz_type="achievement", biz_id=ach.id,
                link=f"/projects/{obj.id}/achievements",
            )
        db.commit()
        db.refresh(ach)
        db.refresh(review)
        return AchievementService._to_response(db, ach, review)

    @staticmethod
    def update(db: Session, pk: int, req: AchievementUpdate, operator: SysUser) -> AchievementResponse:
        """修改成果（局部更新），修改后重新进入待认定。

        参数:
            pk: 成果主键
            req: 更新请求；exclude_unset 保证未传字段不被覆盖
            operator: 当前操作人
        返回:
            更新后的成果响应（认定状态重置为“待认定”）
        异常:
            ResourceNotFoundException / PermissionDeniedException /
            ParamValidateException（项目阶段或成果日期不合法）
        副作用:
            更新成果字段、绑定新附件、重置认定记录；必要时通知指导教师；commit
        注意:
            “已认定”成果对普通负责人锁定：负责人必须请指导教师/管理员先撤销认定，
            否则任何人都能在认定后偷改材料，认定结论将失去意义。
        """
        from app.models import ProjAchievement
        ach = db.query(ProjAchievement).filter(
            ProjAchievement.id == pk, ProjAchievement.is_deleted == 0
        ).first()
        if not ach:
            raise ResourceNotFoundException(message="成果不存在")
        obj = ProjectCRUD.get_by_id(db, ach.project_id)
        if not obj:
            raise ResourceNotFoundException(message="所属项目不存在")
        # ---------- 阶段与权限 ----------
        AchievementService._ensure_project_status(obj)
        AchievementService._ensure_permission(obj, operator, "仅项目负责人、指导教师或管理员可编辑成果")
        # ---------- 认定状态锁定校验 ----------
        old_review = db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id == ach.id,
            ProjAchievementReview.is_deleted == 0,
        ).first()
        # 历史成果无认定记录按“已认定”处理，与 _to_response 的展示口径保持一致
        old_status = old_review.status if old_review else 1
        # 已认定成果锁定给负责人：需由指导教师/管理员撤销认定后才能修改
        if old_status == 1 and not AchievementService._can_review(obj, operator):
            raise PermissionDeniedException(message="成果已认定，需先撤销认定后才能修改")
        # ---------- 字段更新 ----------
        data = req.model_dump(exclude_unset=True)
        attachment_ids = data.pop("attachment_ids", []) or []
        # 只有显式改日期时才校验；未改则沿用库中原值，避免历史不合法日期阻塞编辑
        if "publish_date" in data:
            AchievementService._validate_publish_date(obj, data["publish_date"])
        for key, value in data.items():
            setattr(ach, key, value)
        AchievementService._bind_attachments(db, ach.id, attachment_ids, operator)
        # ---------- 重置认定并通知 ----------
        # 修改即视为“材料版本变化”，必须重新认定，不能沿用旧结论
        review = AchievementService._reset_review(db, ach.id)
        # 已认定/不通过的成果被修改后需重新认定，通知指导教师
        if old_status in (1, 2) and obj.teacher_id and obj.teacher_id != operator.id:
            NotificationService.push(
                db, obj.teacher_id, "成果已修改，待重新认定",
                f"项目「{obj.project_name}」的成果「{ach.title}」已修改，请重新认定。",
                level=NOTICE_LEVEL_INFO, biz_type="achievement", biz_id=ach.id,
                link=f"/projects/{obj.id}/achievements",
            )
        db.commit()
        db.refresh(ach)
        db.refresh(review)
        return AchievementService._to_response(db, ach, review)

    @staticmethod
    def review(db: Session, pk: int, req: AchievementReviewRequest,
               operator: SysUser) -> AchievementResponse:
        """成果认定：通过(1) / 不通过(2)

        参数:
            pk: 成果主键
            req: 认定请求，result 取值 1/2；不通过时 comment 必填
            operator: 当前操作人（指导教师/学院管理员/超管）
        返回:
            认定后的成果响应
        异常:
            ResourceNotFoundException / PermissionDeniedException / ParamValidateException
        副作用:
            写入认定人/意见/时间，通知项目负责人；commit
        注意:
            - 认定不通过必须填写意见，否则学生不知道如何修改；
            - 通知对象是负责人而不是登记人：最终需要修改材料的是负责人。
        """
        from app.models import ProjAchievement
        ach = db.query(ProjAchievement).filter(
            ProjAchievement.id == pk, ProjAchievement.is_deleted == 0
        ).first()
        if not ach:
            raise ResourceNotFoundException(message="成果不存在")
        obj = ProjectCRUD.get_by_id(db, ach.project_id)
        if not obj:
            raise ResourceNotFoundException(message="所属项目不存在")
        # ---------- 权限与参数校验 ----------
        AchievementService._ensure_project_status(obj)
        AchievementService._ensure_review_permission(obj, operator)
        if req.result == 2 and not (req.comment or "").strip():
            raise ParamValidateException(message="认定不通过时请填写认定意见")
        # ---------- 写入认定结论 ----------
        # 先复用 _reset_review 清空旧结论（含 submit_time 刷新），再覆盖本次认定字段
        row = AchievementService._reset_review(db, ach.id)
        row.status = req.result
        row.reviewer_id = operator.id
        row.reviewer_name = operator.real_name
        row.review_comment = (req.comment or "").strip() or None
        row.review_time = datetime.now()
        # ---------- 通知负责人 ----------
        passed = req.result == 1
        title = "成果认定通过" if passed else "成果认定未通过"
        content = f"项目「{obj.project_name}」的成果「{ach.title}」已{'通过' if passed else '未通过'}认定。"
        if row.review_comment:
            content += f"认定意见：{row.review_comment}"
        NotificationService.push(
            db, obj.leader_id, title, content,
            level=NOTICE_LEVEL_SUCCESS if passed else NOTICE_LEVEL_WARNING,
            biz_type="achievement", biz_id=ach.id,
            link=f"/projects/{obj.id}/achievements",
        )
        db.commit()
        db.refresh(ach)
        db.refresh(row)
        return AchievementService._to_response(db, ach, row)

    @staticmethod
    def revoke_review(db: Session, pk: int, operator: SysUser) -> AchievementResponse:
        """撤销成果认定：回到「待认定」，清空认定结论，允许负责人修改后重新认定

        参数:
            pk: 成果主键
            operator: 当前操作人（必须具有认定权限）
        返回:
            撤销后的成果响应（状态 0 待认定）
        异常:
            ResourceNotFoundException / PermissionDeniedException / ParamValidateException
        副作用:
            清空认定人/意见/时间，刷新 submit_time，通知负责人；commit
        注意:
            只有“已认定(1)”可撤销；“不通过(2)”本身已允许负责人修改，无需撤销。
            撤销是解除“成果锁定”的唯一入口，因此必须校验认定权限。
        """
        from app.models import ProjAchievement
        ach = db.query(ProjAchievement).filter(
            ProjAchievement.id == pk, ProjAchievement.is_deleted == 0
        ).first()
        if not ach:
            raise ResourceNotFoundException(message="成果不存在")
        obj = ProjectCRUD.get_by_id(db, ach.project_id)
        if not obj:
            raise ResourceNotFoundException(message="所属项目不存在")
        AchievementService._ensure_project_status(obj)
        AchievementService._ensure_review_permission(obj, operator)
        row = db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id == ach.id,
            ProjAchievementReview.is_deleted == 0,
        ).first()
        if not row or row.status != 1:
            raise ParamValidateException(message="仅已认定的成果可撤销认定")
        # 回到待认定：清空结论，保留记录本身（submit_time 更新为撤销/重提时间）
        row.status = 0
        row.reviewer_id = None
        row.reviewer_name = None
        row.review_comment = None
        row.review_time = None
        row.submit_time = datetime.now()
        NotificationService.push(
            db, obj.leader_id, "成果认定已撤销",
            f"项目「{obj.project_name}」的成果「{ach.title}」认定已被撤销，"
            "可在编辑修改后重新提交认定。",
            level=NOTICE_LEVEL_WARNING, biz_type="achievement", biz_id=ach.id,
            link=f"/projects/{obj.id}/achievements",
        )
        db.commit()
        db.refresh(ach)
        db.refresh(row)
        return AchievementService._to_response(db, ach, row)

    @staticmethod
    def delete(db: Session, pk: int, operator: SysUser) -> None:
        """软删除成果及其认定记录。

        参数:
            pk: 成果主键
            operator: 当前操作人
        异常:
            ResourceNotFoundException / PermissionDeniedException
        副作用:
            proj_achievement.is_deleted=1，认定记录同步软删；commit
        注意:
            - 权限：超管全校 / 学院管理员本院 / 负责人本人；
            - 已认定成果仅“可认定角色”可删除，负责人需先撤销认定，
              避免删除后认定历史与成果数据不一致（虽然记录会软删，仍保留可追溯性）。
        """
        from app.models import ProjAchievement
        ach = db.query(ProjAchievement).filter(
            ProjAchievement.id == pk, ProjAchievement.is_deleted == 0
        ).first()
        if not ach:
            raise ResourceNotFoundException(message="成果不存在")
        obj = ProjectCRUD.get_by_id(db, ach.project_id)
        if not obj:
            raise ResourceNotFoundException(message="所属项目不存在")
        # ---------- 删除权限分级 ----------
        if not is_super_admin(operator):
            if is_college_admin(operator):
                if not operator.college_id or obj.college_id != operator.college_id:
                    raise PermissionDeniedException(message="学院管理员仅可删除本院成果")
            elif obj.leader_id != operator.id:
                raise PermissionDeniedException(message="仅负责人或管理员可删除成果")
        # ---------- 已认定成果的额外锁定 ----------
        # 已认定成果仅管理员可删除；负责人需先撤销认定，保留认定历史可追溯
        review = db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id == ach.id,
            ProjAchievementReview.is_deleted == 0,
        ).first()
        if review and review.status == 1 and not AchievementService._can_review(obj, operator):
            raise PermissionDeniedException(message="成果已认定，请先撤销认定后再删除")
        # 成果与认定记录一起软删，避免孤立的认定记录被统计/列表误读
        ach.is_deleted = 1
        db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id == ach.id
        ).update({ProjAchievementReview.is_deleted: 1}, synchronize_session=False)
        db.commit()
