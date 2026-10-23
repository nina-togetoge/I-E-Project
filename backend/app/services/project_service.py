"""
项目申报与审核 业务逻辑层(Service)
"""
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
    """项目申报业务服务"""

    # 可提交变更/延期申请的项目阶段：仅「待校级复审」「待专家评审」两个审核段
    CHANGE_WINDOW_STATUSES = {
        PROJECT_STATUS_PENDING_UNIVERSITY, PROJECT_STATUS_PENDING_EXPERT,
    }

    # 不占用比赛申报名额的状态：草稿 / 已驳回 / 已撤销
    NON_OCCUPYING_STATUSES = (
        PROJECT_STATUS_DRAFT, PROJECT_STATUS_REJECTED, PROJECT_STATUS_CANCELLED,
    )

    # ================= 流程截止日（截止日驱动锁定） =================
    @staticmethod
    def _get_competition(db: Session, project: ProjProject) -> Optional[Competition]:
        """项目所关联的比赛（时间表来源）；未关联返回 None"""
        if not project or not project.competition_id:
            return None
        return db.query(Competition).filter(Competition.id == project.competition_id).first()

    @staticmethod
    def is_past_deadline(deadline: Optional[date]) -> bool:
        """是否已过截止日（截止日当天仍可用）；未配置(None)视为不锁"""
        if deadline is None:
            return False
        return date.today() > deadline

    @staticmethod
    def get_change_deadline_for_status(db: Session, project: ProjProject, status: Optional[int]) -> Optional[date]:
        """指定审核段的变更/延期锁死日（比赛未配置时间表则不锁）"""
        comp = ProjectService._get_competition(db, project)
        if not comp:
            return None
        return {
            PROJECT_STATUS_PENDING_UNIVERSITY: comp.university_review_date,  # 待校级复审
            PROJECT_STATUS_PENDING_EXPERT: comp.expert_review_date,          # 待专家评审
        }.get(status)

    @staticmethod
    def get_change_deadline(db: Session, project: ProjProject) -> Optional[date]:
        """项目『当前阶段审核日』= 变更/延期申请的锁死日（比赛未配置时间表则不锁）"""
        return ProjectService.get_change_deadline_for_status(db, project, project.status)

    @staticmethod
    def get_teacher_confirm_deadline(db: Session, project: ProjProject) -> Optional[date]:
        """指导教师确认截止日 = 学院初审审核日"""
        comp = ProjectService._get_competition(db, project)
        return comp.college_review_date if comp else None

    @staticmethod
    def get_midterm_deadline(db: Session, project: ProjProject) -> Optional[date]:
        """中期报告提交/审核截止日"""
        comp = ProjectService._get_competition(db, project)
        return comp.midterm_deadline if comp else None

    @staticmethod
    def get_final_deadline(db: Session, project: ProjProject) -> Optional[date]:
        """结题报告提交/审核截止日"""
        comp = ProjectService._get_competition(db, project)
        return comp.final_deadline if comp else None

    # ================= 超期自动作废清扫（读列表/详情时顺带执行） =================
    @staticmethod
    def sweep_expired_change_requests(db: Session, project_ids: Optional[List[int]] = None) -> int:
        """把已过『审核日 + 1 天缓冲期』仍待审核的变更/延期申请置为『已作废』；记录保留以便追责"""
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
            if deadline is not None and date.today() > deadline + timedelta(days=1):
                obj.status = CHANGE_STATUS_EXPIRED
                obj.reject_reason = "超过审批缓冲期自动作废"
                voided += 1
        if voided:
            db.commit()
        return voided

    @staticmethod
    def sweep_expired_midterm(db: Session, project_id: int) -> None:
        """中期检查截止日清扫：
        - 截止日前已提交(待审核 status=1)的报告继续保留，指导教师仍可审核（避免流程死锁）
        - 截止日时仍未提交/未通过(草稿/修改/驳回) → 项目终止为「已撤销(11)」，留档追责
        """
        project = ProjectCRUD.get_by_id(db, project_id)
        if not project or project.status not in (PROJECT_STATUS_APPROVED, PROJECT_STATUS_MIDTERM):
            return
        deadline = ProjectService.get_midterm_deadline(db, project)
        if deadline is None or date.today() <= deadline:
            return
        midterm = MidtermCRUD.get_by_project(db, project_id)
        if midterm and midterm.status in (1, 2):
            # 已按时提交待审核 / 已通过：保留，审核不再受截止日限制
            return
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
        """
        project = ProjectCRUD.get_by_id(db, project_id)
        if not project or project.status != PROJECT_STATUS_PENDING_FINAL:
            return
        deadline = ProjectService.get_final_deadline(db, project)
        if deadline is None or date.today() <= deadline:
            return
        has_report = db.query(ProjReview.id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.review_result == 99,
            ProjReview.is_deleted == 0,
        ).first()
        if has_report:
            return
        project.status = PROJECT_STATUS_CANCELLED
        project.reject_reason = "超过结题报告提交截止日未提交结项报告，项目自动终止"
        db.commit()

    @staticmethod
    def _to_list_item(obj: ProjProject) -> ProjectListItem:
        """ORM -> Pydantic列表项"""
        item = ProjectListItem.model_validate(obj)
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
            college = CollegeCRUD.get_by_id(obj._sa_instance_state.session, obj.college_id) \
                if hasattr(obj, "_sa_instance_state") and obj._sa_instance_state.session else None
            if college:
                item.college_name = college.college_name
        return item

    @staticmethod
    def _to_detail(db: Session, obj: ProjProject, operator: Optional[SysUser] = None) -> ProjectDetailResponse:
        """ORM -> Pydantic详情（含团队/预算等子表）"""
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
        # 是否「可修改后重新提交」：仅「指导教师驳回」允许；学院/校级/专家驳回即落选（终局）
        item.resubmittable = (
            item.status == PROJECT_STATUS_REJECTED
            and not ProjectService._is_eliminated(db, obj)
        )
        # 结项报告（占位记录：阶段=结题验收4、结果=99）正文与验收状态
        report_record = ProjectService._final_report_record(db, obj.id)
        item.final_report_submitted = report_record is not None
        item.final_report = ProjectService._strip_report_prefix(
            report_record.review_comment
        ) if report_record else None
        if obj.status == 9:
            item.final_report_status = 2  # 已通过（已结题）
        elif report_record and obj.reject_reason:
            item.final_report_status = 3  # 验收驳回，可修改后重新提交
        elif report_record:
            item.final_report_status = 1  # 待验收
        else:
            item.final_report_status = 0  # 未提交
        # 驳回意见：取本轮最新一条驳回记录（仅驳回态展示，避免验收中误提示）
        item.final_reject_reason = None
        if item.final_report_status == 3:
            rejects = [
                r for r in ProjectService.final_latest_reviews(db, obj.id).values()
                if r.review_result != 1
            ]
            if rejects:
                item.final_reject_reason = max(rejects, key=lambda r: r.id).review_comment
        item.final_review_total, item.final_review_done = ProjectService.final_review_stats(db, obj.id)
        # 专家验收入口：被分配到该项目的专家或超级管理员
        if operator is not None:
            item.final_can_accept = (
                obj.status == 8
                and (
                    is_super_admin(operator)
                    or operator.id in ProjectService.assigned_expert_ids(db, obj.id)
                )
            )
            item.final_reviewed_by_me = operator.id in ProjectService.final_latest_reviews(db, obj.id)
        item.final_checklist = ProjectService.get_final_checklist(db, obj)
        # 流程截止日（截止日驱动锁定）：变更/延期锁死日 = 当前阶段审核日
        item.change_deadline = ProjectService.get_change_deadline(db, obj)
        item.change_locked = (
            obj.status not in ProjectService.CHANGE_WINDOW_STATUSES
            or ProjectService.is_past_deadline(item.change_deadline)
        )
        item.midterm_deadline = ProjectService.get_midterm_deadline(db, obj)
        item.final_deadline = ProjectService.get_final_deadline(db, obj)
        # 竞赛获奖成果数量
        item.award_count = db.query(func.count(ProjAchievement.id)).filter(
            ProjAchievement.project_id == obj.id,
            ProjAchievement.achievement_type == 4,
            ProjAchievement.is_deleted == 0,
        ).scalar() or 0
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
        在 SAVEPOINT 内 flush，冲突回滚到保存点后仅重试编号，不影响已构建的其他待写数据。"""
        year = date.today().year
        candidate = ProjectCRUD.generate_project_no(db, year)
        for _ in range(5):
            obj.project_no = candidate
            try:
                with db.begin_nested():
                    db.flush()
                return
            except IntegrityError:
                candidate = ProjectCRUD.bump_project_no(candidate)
        raise DataConflictException(message="项目编号生成冲突，请重试")

    @staticmethod
    def _sync_current_approver(db: Session, project: ProjProject) -> None:
        """根据项目阶段刷新"当前审批人"字段（供项目详情展示审批进度）：
        - 待指导教师确认(12)：指导教师
        - 待学院初审(1) / 待分配评审专家(13)：该学院的管理员
        - 其他阶段（待校级复审/专家评审/已立项及之后）：无单一审批人，置空
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
        仅当 data 中显式含 competition_id 时处理；未选择比赛则置空。"""
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
        """提交审核前校验参赛比赛：必须存在且处于报名中/进行中"""
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
        - 草稿/已驳回/已撤销不占用名额。"""
        if not competition_id:
            return
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
        members = db.query(ProjTeamMember).filter(
            ProjTeamMember.project_id.in_(list(project_names)),
            ProjTeamMember.is_deleted == 0,
        ).all()
        for tm in members:
            taken.setdefault(tm.student_id, (project_names.get(tm.project_id, ""), False))

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
        仅「指导教师驳回」允许学生改后重提。"""
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
        - 指导教师、专家不可编辑项目"""
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
        # 批量查学院名称（避免N+1）
        college_ids = list({i.college_id for i in items if i.college_id})
        college_map = {}
        if college_ids:
            from app.models import SysCollege
            colleges = db.query(SysCollege).filter(SysCollege.id.in_(college_ids)).all()
            college_map = {c.id: c.college_name for c in colleges}
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
            if it.college_id and college_map.get(it.college_id):
                it.college_name = college_map[it.college_id]
            if it.competition_id and competition_map.get(it.competition_id):
                it.competition_name = competition_map[it.competition_id]
            result.append(it)
        # 批量查已分配专家数（review_stage=3 专家评审阶段）
        if items:
            project_ids = [p.id for p in items]
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
            for it in result:
                it.resubmittable = (
                    it.status == PROJECT_STATUS_REJECTED and it.id not in eliminated_ids
                )
        return result, total

    @staticmethod
    def paginate_announcement(db: Session, pager: PaginationParams,
                              params: ProjectQueryParams) -> Tuple[List[ProjectListItem], int]:
        """立项结果公示：已立项及之后阶段的项目，不做数据权限过滤，全校可见"""
        # 仅已立项(6)及之后：中期检查中(7)、待结题(8)、已结题(9)
        # 注意：12=待指导教师确认，绝不能纳入公示（否则未审核项目会被公开）
        approved_statuses = [6, 7, 8, 9]
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
        # 顺带清扫超期未审的变更申请 / 中期报告 / 结项报告（自动作废，留档）
        ProjectService.sweep_expired_change_requests(db, [project_id])
        ProjectService.sweep_expired_midterm(db, project_id)
        ProjectService.sweep_expired_final(db, project_id)
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 草稿项目(0)仅学生（负责人/团队成员）可见，其他角色（管理员/教师/专家）一律不可见
        if obj.status == PROJECT_STATUS_DRAFT and operator.role != RoleEnum.STUDENT:
            raise PermissionDeniedException(message="草稿项目仅项目负责人可见")
        # 数据权限
        scope = DataScope.__new__(DataScope)
        scope.user = operator
        scope.db = db
        scope.role = operator.role
        scope.college_id = operator.college_id
        scope.user_id = operator.id
        scope.scope = scope._compute_scope()
        ok = False
        if scope.scope.get("all"):
            ok = True
        elif scope.scope.get("is_student"):
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
            ok = obj.teacher_id == operator.id or \
                 (scope.scope.get("college_ids") and obj.college_id in scope.scope["college_ids"])
        elif scope.scope.get("college_ids"):
            ok = obj.college_id in scope.scope["college_ids"]
        elif scope.scope.get("expert_user_id"):
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
        """
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
        if operator.role == RoleEnum.STUDENT:
            data["leader_id"] = operator.id
            data["college_id"] = operator.college_id or data["college_id"]
        elif "leader_id" not in data or not data.get("leader_id"):
            raise ParamValidateException(message="管理员创建需额外指定负责人（通过扩展字段，此示例暂不支持）")

        # 校验负责人/团队成员存在，避免外键错误直接抛 500
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
            ProjectService._assert_competition_submittable(db, req.competition_id)
            ProjectService._assert_competition_entry_unique(
                db, req.competition_id, data["leader_id"], member_ids
            )

        data["status"] = PROJECT_STATUS_DRAFT if as_draft else PROJECT_STATUS_PENDING_TEACHER
        if not as_draft:
            data["submit_time"] = datetime.now()
        # 根据所选比赛回填参赛届次
        ProjectService._derive_competition_session(db, data)

        obj = ProjectCRUD.create(db, data)
        # 提交时自动生成编号（唯一键冲突自动递增重试）
        if not as_draft:
            ProjectService._assign_project_no(db, obj)
            ProjectService._sync_current_approver(db, obj)
            # 创建指导教师确认占位审核记录
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
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        ProjectService._check_edit_permission(db, obj, operator)
        data = req.model_dump(exclude_unset=True)
        # 起止日期顺序校验：仅更新一端时，与库中另一端合并后再判断
        new_start = data.get("start_date", obj.start_date)
        new_end = data.get("end_date", obj.end_date)
        if new_start and new_end and new_start > new_end:
            raise ParamValidateException(message="开始日期不能晚于结束日期")
        # 若变更了参赛比赛，同步刷新参赛届次
        ProjectService._derive_competition_session(db, data)
        # 如果包含 teacher_id，校验
        if req.teacher_id:
            t = UserCRUD.get_by_id(db, req.teacher_id)
            if not t or t.role not in (RoleEnum.TEACHER, RoleEnum.ADMIN):
                raise ParamValidateException(message="指导教师无效")
            # 指导教师须属于该项目所在学院（真超级管理员可跨院指定，用于演示代录）
            if not is_super_admin(operator) and t.college_id != data.get("college_id", obj.college_id):
                raise ParamValidateException(message="指导教师不属于该项目所在学院")
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
        """
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 落选项目在 _check_edit_permission 中即被拒绝
        ProjectService._check_edit_permission(db, obj, operator)
        if obj.status != PROJECT_STATUS_DRAFT and obj.status != 10:
            raise ParamValidateException(message="当前项目状态不可提交审核")
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
        ProjectService._assert_competition_submittable(db, obj.competition_id)
        member_ids = [tm.student_id for tm in db.query(ProjTeamMember).filter(
            ProjTeamMember.project_id == obj.id,
            ProjTeamMember.is_deleted == 0,
        ).all()]
        ProjectService._assert_competition_entry_unique(
            db, obj.competition_id, obj.leader_id, member_ids, exclude_project_id=obj.id
        )

        obj.submit_time = datetime.now()
        # 重提清除上一轮驳回原因，避免旧状态残留
        obj.reject_reason = None
        # 整条流程从「待指导教师确认」重走，清空上一轮审核记录
        obj.status = PROJECT_STATUS_PENDING_TEACHER
        db.query(ProjReview).filter(
            ProjReview.project_id == obj.id,
            ProjReview.is_deleted == 0,
        ).update({ProjReview.is_deleted: 1}, synchronize_session=False)

        # 刷新当前审批人（随目标状态：待学院初审→学院管理员；待校级复审/待专家评审→清空等）
        ProjectService._sync_current_approver(db, obj)

        # 首次提交时生成项目编号（唯一键冲突自动递增重试）
        if obj.project_no:
            db.flush()
        else:
            ProjectService._assign_project_no(db, obj)

        # 创建指导教师确认占位审核记录，使指导教师在待审核列表中看到该项目
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
    FINAL_REPORT_PREFIX = "[结项报告] "

    @staticmethod
    def _strip_report_prefix(comment: Optional[str]) -> Optional[str]:
        if not comment:
            return None
        if comment.startswith(ProjectService.FINAL_REPORT_PREFIX):
            return comment[len(ProjectService.FINAL_REPORT_PREFIX):]
        return comment

    @staticmethod
    def _final_report_record(db: Session, project_id: int) -> Optional[ProjReview]:
        """结项报告占位记录（result=99）；其 review_time 同时标记「本轮验收」起点"""
        return db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.review_result == 99,
            ProjReview.is_deleted == 0,
        ).order_by(ProjReview.id.desc()).first()

    @staticmethod
    def _final_round_start(db: Session, project_id: int) -> Optional[datetime]:
        record = ProjectService._final_report_record(db, project_id)
        return record.review_time if record else None

    @staticmethod
    def assigned_expert_ids(db: Session, project_id: int) -> set:
        """被分配到该项目（专家评审阶段）的专家ID集合"""
        rows = db.query(ProjReview.reviewer_id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.is_deleted == 0,
        ).all()
        return {r[0] for r in rows if r[0]}

    @staticmethod
    def final_latest_reviews(db: Session, project_id: int) -> Dict[int, ProjReview]:
        """本轮结题验收中每位专家最新的一条正式意见（占位记录不计）"""
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
        for row in q.order_by(ProjReview.id).all():
            latest[row.reviewer_id] = row
        return latest

    @staticmethod
    def final_review_stats(db: Session, project_id: int) -> Tuple[int, int]:
        """返回 (应参与验收专家数, 本轮已提交意见专家数)"""
        assigned = ProjectService.assigned_expert_ids(db, project_id)
        latest = ProjectService.final_latest_reviews(db, project_id)
        if assigned:
            return len(assigned), len(assigned & set(latest.keys()))
        return 0, len(latest)

    @staticmethod
    def _latest_final_review(db: Session, project_id: int) -> Optional[ProjReview]:
        """最近一次正式结题验收意见（任意轮次），用于展示驳回意见"""
        return db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.is_deleted == 0,
            ProjReview.review_result.isnot(None),
            ProjReview.review_result != 99,
        ).order_by(ProjReview.id.desc()).first()

    @staticmethod
    def final_rejected_current_round(db: Session, project_id: int) -> bool:
        """本轮报告是否已被专家驳回（驳回后可直接修改重提，不受截止日限制）"""
        latest = ProjectService._latest_final_review(db, project_id)
        start = ProjectService._final_round_start(db, project_id)
        if not latest or latest.review_result == 1:
            return False
        return start is None or latest.review_time >= start

    @staticmethod
    def _final_condition_stats(db: Session, project: ProjProject) -> Tuple[bool, int, int]:
        """结项三条件统计：中期已通过 / 成果数 / 未结清报销单数"""
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
        """结项条件检查清单（前端展示；前 3 项为提交/验收硬性条件）"""
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
        """
        from app.models import SysAttachment, ProjReview
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 仅项目负责人本人可提交（真超级管理员可代操作）
        if not is_super_admin(operator) and obj.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可提交结项报告")
        if obj.status != 8:
            raise ParamValidateException(message="仅待结题状态可提交结项验收报告")
        # 截止日限制：驳回后的修改重提不受截止日限制，否则逾期驳回的项目将永久无法结项
        if (
            ProjectService.is_past_deadline(ProjectService.get_final_deadline(db, obj))
            and not ProjectService.final_rejected_current_round(db, obj.id)
        ):
            raise ParamValidateException(message="已超过结题报告提交截止日，无法提交结项验收报告")
        if not final_report or not final_report.strip():
            raise ParamValidateException(message="请填写结项验收报告")

        # 结项三条件校验：中期已批 + 成果≥1 + 报销已结清
        ProjectService._ensure_final_conditions(db, obj)

        # 重新提交即开启新一轮验收：清除上一轮驳回标记，供专家重新验收
        obj.reject_reason = None

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
        # 以占位记录(review_result=99)登记"结项验收报告已提交"，供专家结题验收时校验
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
        撤回后删除报告占位记录，项目仍停留在「待结题(8)」，可修改后重新提交。"""
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
        """学生/负责人撤回项目（状态->草稿）"""
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
        """
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        if is_super_admin(operator):
            pass
        elif is_college_admin(operator):
            if not operator.college_id or obj.college_id != operator.college_id:
                raise PermissionDeniedException(message="学院管理员仅可删除本院项目")
        elif operator.role == RoleEnum.STUDENT:
            if obj.status != PROJECT_STATUS_DRAFT:
                raise PermissionDeniedException(message="仅草稿状态可删除，其他状态请联系管理员")
            if obj.leader_id != operator.id:
                raise PermissionDeniedException(message="仅负责人可删除草稿")
        else:
            raise PermissionDeniedException(message="无权限删除该项目")
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
    @staticmethod
    def statistics_overview(db: Session, data_scope: DataScope,
                            college_id: Optional[int] = None,
                            project_type: Optional[int] = None,
                            start_year: Optional[int] = None,
                            end_year: Optional[int] = None,
                            ) -> ProjectStatisticsResponse:
        """项目概览统计（支持按学院/类型/立项年份过滤）"""
        from app.models import ProjProject, ProjReview
        q = db.query(func.count(ProjProject.id)).filter(ProjProject.is_deleted == 0)
        # 待审核数按角色区分：仅统计需要当前用户处理的项目
        scope = data_scope.scope
        if scope.get("is_student"):
            q_pending = q.filter(ProjProject.status == 10, ProjProject.leader_id == data_scope.user_id)
        elif scope.get("teacher_user_ids"):
            q_pending = q.filter(ProjProject.status == 12, ProjProject.teacher_id == data_scope.user_id)
        elif scope.get("is_college_admin"):
            # 学院初审 + 本院项目的专家分配（待分配评审专家 13 同样需要管理员处理）
            q_pending = q.filter(
                ProjProject.status.in_([PROJECT_STATUS_PENDING_COLLEGE, PROJECT_STATUS_PENDING_EXPERT_ASSIGN]),
                ProjProject.college_id == data_scope.college_id,
            )
        elif scope.get("expert_user_id"):
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
        q_approved = q.filter(ProjProject.status.in_([6, 7, 8, 9]))
        q_finished = q.filter(ProjProject.status == 9)

        def apply_filters_and_scope(query):
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
            return query

        total = apply_filters_and_scope(q.with_entities(func.count(ProjProject.id))).scalar() or 0
        pending = apply_filters_and_scope(q_pending.with_entities(func.count(ProjProject.id))).scalar() or 0
        approved = apply_filters_and_scope(q_approved.with_entities(func.count(ProjProject.id))).scalar() or 0
        finished = apply_filters_and_scope(q_finished.with_entities(func.count(ProjProject.id))).scalar() or 0
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
        status_rows = apply_filters_and_scope(db.query(
            ProjProject.status, func.count(ProjProject.id)
        ).group_by(ProjProject.status)).all()
        status_dist = [
            {"name": PROJECT_STATUS_NAME.get(int(r[0]), f"状态{r[0]}"), "value": int(r[1] or 0), "status": int(r[0])}
            for r in status_rows
        ]

        # ===== 经费科目使用分布（真实数据，从 proj_budget 汇总 used_amount）=====
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
        """把数据权限范围应用到查询；无任何数据范围时返回空结果集（避免默认放行全校）"""
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
        """按月统计申报/立项趋势（ECharts适配）"""
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
    def college_breakdown(db: Session, data_scope: DataScope) -> List[CollegeStatisticsItem]:
        """各学院统计数据（雷达图/热力图/学院立项率柱状图）"""
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

        result: List[CollegeStatisticsItem] = []
        for col in colleges:
            q = db.query(ProjProject).filter(ProjProject.is_deleted == 0, ProjProject.college_id == col.id)

            total = q.count()
            approved = q.filter(ProjProject.status.in_([6, 7, 8, 9])).count()
            finished = q.filter(ProjProject.status == 9).count()
            denied = q.filter(ProjProject.status == 10).count()
            budget = db.query(func.coalesce(func.sum(ProjProject.budget_amount), 0)).filter(
                ProjProject.is_deleted == 0, ProjProject.college_id == col.id).scalar() or 0
            used = db.query(func.coalesce(func.sum(ProjProject.used_amount), 0)).filter(
                ProjProject.is_deleted == 0, ProjProject.college_id == col.id).scalar() or 0

            # 成果数
            achievements = db.query(func.count(ProjAchievement.id)).join(
                ProjProject, ProjAchievement.project_id == ProjProject.id
            ).filter(
                ProjProject.college_id == col.id,
                ProjProject.is_deleted == 0,
                ProjAchievement.is_deleted == 0,
            ).scalar() or 0

            # 专家评审平均分
            avg_score_row = db.query(func.avg(ProjReview.score)).join(
                ProjProject, ProjReview.project_id == ProjProject.id
            ).filter(
                ProjProject.college_id == col.id,
                ProjProject.is_deleted == 0,
                ProjReview.score.isnot(None),
            ).scalar()
            avg_score = round(float(avg_score_row or 0), 2)

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
    """项目成果业务服务"""

    # 可登记/编辑成果的项目阶段：已立项及之后
    EDITABLE_PROJECT_STATUSES = (6, 7, 8, 9)
    # 成果认定状态
    REVIEW_STATUS_NAME = {0: "待认定", 1: "已认定", 2: "不通过"}

    @staticmethod
    def _ensure_project_status(project: ProjProject) -> None:
        if project.status not in AchievementService.EDITABLE_PROJECT_STATUSES:
            raise ParamValidateException(message="仅已立项及之后阶段可登记或编辑成果")

    @staticmethod
    def _ensure_permission(project: ProjProject, operator: SysUser, deny_message: str) -> None:
        """登记/编辑权限：超管全校；学院管理员限本院；项目负责人或该项目指导教师本人"""
        if is_super_admin(operator):
            return
        if is_college_admin(operator):
            if not operator.college_id or project.college_id != operator.college_id:
                raise PermissionDeniedException(message="学院管理员仅可管理本院项目成果")
            return
        if project.leader_id == operator.id or (
            operator.role == RoleEnum.TEACHER and project.teacher_id == operator.id
        ):
            return
        raise PermissionDeniedException(message=deny_message)

    @staticmethod
    def _ensure_review_permission(project: ProjProject, operator: SysUser) -> None:
        """成果认定权限：该项目指导教师、学院管理员、超级管理员（负责人不得自认）"""
        if is_super_admin(operator):
            return
        if is_college_admin(operator):
            if not operator.college_id or project.college_id != operator.college_id:
                raise PermissionDeniedException(message="学院管理员仅可认定本院项目成果")
            return
        if operator.role == RoleEnum.TEACHER and project.teacher_id == operator.id:
            return
        raise PermissionDeniedException(message="仅项目指导教师或管理员可认定成果")

    @staticmethod
    def _validate_publish_date(project: ProjProject, publish_date: Optional[date]) -> None:
        """成果日期须落在「项目开始日期 ~ 今天」区间内"""
        if publish_date is None:
            return
        if publish_date > date.today():
            raise ParamValidateException(message="成果日期不能晚于今天")
        if project.start_date and publish_date < project.start_date:
            raise ParamValidateException(message=f"成果日期不能早于项目开始日期（{project.start_date}）")

    @staticmethod
    def _bind_attachments(db: Session, ach_id: int, attachment_ids: List[int], operator: SysUser) -> None:
        """把本人上传的临时证明材料（biz_type=achievement, biz_id=0）绑定到成果"""
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
        if not ach_ids:
            return {}
        rows = db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id.in_(ach_ids),
            ProjAchievementReview.is_deleted == 0,
        ).all()
        return {r.achievement_id: r for r in rows}

    @staticmethod
    def _reset_review(db: Session, ach_id: int) -> ProjAchievementReview:
        """成果新增/修改后回到「待认定」，清空上一轮认定结论"""
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
        row.submit_time = datetime.now()
        row.is_deleted = 0
        return row

    @staticmethod
    def _to_response(db: Session, ach: ProjAchievement,
                     review: Optional[ProjAchievementReview] = None) -> AchievementResponse:
        from app.models import SysAttachment
        item = AchievementResponse.model_validate(ach)
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
        obj = ProjectCRUD.get_by_id(db, req.project_id)
        if not obj:
            raise ResourceNotFoundException(message="所属项目不存在")
        AchievementService._ensure_project_status(obj)
        AchievementService._ensure_permission(obj, operator, "仅项目负责人、指导教师或管理员可登记成果")
        data = req.model_dump()
        attachment_ids = data.pop("attachment_ids", []) or []
        AchievementService._validate_publish_date(obj, data.get("publish_date"))
        ach = AchievementCRUD.create(db, data)
        AchievementService._bind_attachments(db, ach.id, attachment_ids, operator)
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
        AchievementService._ensure_permission(obj, operator, "仅项目负责人、指导教师或管理员可编辑成果")
        old_review = db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id == ach.id,
            ProjAchievementReview.is_deleted == 0,
        ).first()
        old_status = old_review.status if old_review else 1
        data = req.model_dump(exclude_unset=True)
        attachment_ids = data.pop("attachment_ids", []) or []
        if "publish_date" in data:
            AchievementService._validate_publish_date(obj, data["publish_date"])
        for key, value in data.items():
            setattr(ach, key, value)
        AchievementService._bind_attachments(db, ach.id, attachment_ids, operator)
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
        """成果认定：通过(1) / 不通过(2)"""
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
        if req.result == 2 and not (req.comment or "").strip():
            raise ParamValidateException(message="认定不通过时请填写认定意见")
        row = AchievementService._reset_review(db, ach.id)
        row.status = req.result
        row.reviewer_id = operator.id
        row.reviewer_name = operator.real_name
        row.review_comment = (req.comment or "").strip() or None
        row.review_time = datetime.now()
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
    def delete(db: Session, pk: int, operator: SysUser) -> None:
        from app.models import ProjAchievement
        ach = db.query(ProjAchievement).filter(
            ProjAchievement.id == pk, ProjAchievement.is_deleted == 0
        ).first()
        if not ach:
            raise ResourceNotFoundException(message="成果不存在")
        if not is_super_admin(operator):
            obj = ProjectCRUD.get_by_id(db, ach.project_id)
            if is_college_admin(operator):
                if not obj or not operator.college_id or obj.college_id != operator.college_id:
                    raise PermissionDeniedException(message="学院管理员仅可删除本院成果")
            elif not obj or obj.leader_id != operator.id:
                raise PermissionDeniedException(message="仅负责人或管理员可删除成果")
        ach.is_deleted = 1
        db.query(ProjAchievementReview).filter(
            ProjAchievementReview.achievement_id == ach.id
        ).update({ProjAchievementReview.is_deleted: 1}, synchronize_session=False)
        db.commit()
