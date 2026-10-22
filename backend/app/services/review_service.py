"""
项目审核模块 业务逻辑层(Service)
三级流程：学院初审(College) -> 校级复审(University) -> 专家评审(Expert) -> 立项(Approved)
另外含中期检查、变更/延期审批
"""
from typing import List, Tuple, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import RoleEnum, is_super_admin, is_college_admin
from app.core.exceptions import (
    PermissionDeniedException, ResourceNotFoundException, ParamValidateException,
)
from app.core.deps import PaginationParams, DataScope
from app.crud.project import ProjectCRUD
from app.crud.user import UserCRUD, CollegeCRUD
from app.crud.review import ReviewCRUD, MidtermCRUD, ChangeCRUD
from app.models import (
    ProjProject, SysUser, ProjReview, ProjChangeRequest,
)
from app.schemas.review import (
    ReviewCreateRequest, ExpertReviewCreateRequest, ExpertAssignRequest,
    ReviewRecordItem, ProjectReviewFlowResponse, ExpertProjectItem,
    MidtermCheckCreate, MidtermCheckResponse, MidtermReviewRequest,
    ChangeRequestCreate, ChangeRequestResponse,
    REVIEW_STAGE_TEACHER, REVIEW_STAGE_COLLEGE, REVIEW_STAGE_UNIVERSITY, REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL,
    REVIEW_STAGE_NAME, REVIEW_RESULT_PASS,
    REVIEW_RESULT_NAME, CHANGE_TYPE_NAME, CHANGE_STATUS_NAME, MIDTERM_STATUS_NAME,
    CHANGE_STATUS_PENDING, CHANGE_STATUS_APPROVED, CHANGE_STATUS_REJECTED, CHANGE_STATUS_WITHDRAWN,
    CHANGE_STATUS_EXPIRED,
    CHANGE_MAX_TIMES,
)
from app.schemas.project import (
    PROJECT_STATUS_NAME,
    PROJECT_STATUS_PENDING_COLLEGE,
    PROJECT_STATUS_PENDING_UNIVERSITY,
    PROJECT_STATUS_PENDING_EXPERT,
    PROJECT_STATUS_PENDING_EXPERT_ASSIGN,
)


class ReviewService:
    """审核流程服务"""

    # ---- 状态流转辅助方法 ----
    @staticmethod
    def _next_status_after_pass(current_status: int, stage: int) -> int:
        """根据当前状态 + 审核阶段，计算审核通过后的下一个状态"""
        # 阶段0指导教师确认通过 -> 状态1待学院初审
        if stage == REVIEW_STAGE_TEACHER:
            return 1  # 指导教师确认通过后 -> 待学院初审
        # 阶段1学院初审通过 -> 状态2学院初审通过 -> 然后到状态3待校级复审
        if stage == REVIEW_STAGE_COLLEGE:
            return 3  # 学院初审通过后 -> 待校级复审
        if stage == REVIEW_STAGE_UNIVERSITY:
            return 13  # 校级复审通过后 -> 待分配评审专家（分配完成后转 5 待专家评审）
        if stage == REVIEW_STAGE_EXPERT:
            return 6  # 专家评审通过 -> 已立项
        if stage == REVIEW_STAGE_FINAL:
            return 9  # 结题验收通过 -> 已结题
        return current_status

    @staticmethod
    def _get_stage_from_status(status: int) -> int:
        """根据项目当前状态，推断它当前处于哪个审核阶段；
        非审核流程中的状态（草稿0/已立项6/中期检查中7/已结题9/驳回10/撤销11）返回 -1"""
        if status == 12:
            return REVIEW_STAGE_TEACHER
        if status == 1:
            return REVIEW_STAGE_COLLEGE
        if status == 3:
            return REVIEW_STAGE_UNIVERSITY
        if status == 5:
            return REVIEW_STAGE_EXPERT
        if status == 8:
            return REVIEW_STAGE_FINAL
        return -1

    # ---------- 通用权限校验 ----------
    @staticmethod
    def _ensure_can_review(project: ProjProject, stage: int, operator: SysUser):
        """校验操作者在该阶段是否有审核权限"""
        if project.status in (10, 11):
            raise ParamValidateException(message="该项目已被驳回或撤销，不可审核")
        expected_stage = ReviewService._get_stage_from_status(project.status)
        if stage != expected_stage:
            raise ParamValidateException(
                message=f"当前项目状态[{PROJECT_STATUS_NAME.get(project.status, project.status)}]"
                        f"不匹配请求的审核阶段[{REVIEW_STAGE_NAME.get(stage, stage)}]"
            )
        # 角色与阶段匹配
        if stage == REVIEW_STAGE_TEACHER:
            # 指导教师确认：仅项目的指导教师本人
            if is_super_admin(operator):
                return
            if operator.id != project.teacher_id:
                raise PermissionDeniedException(message="仅该项目的指导教师可进行确认")
            return
        if stage == REVIEW_STAGE_COLLEGE:
            # 学院初审：仅真超级管理员 / 本院学院管理员
            # （指导教师只负责"指导教师确认"，不参与学院初审）
            if is_super_admin(operator):
                return
            if operator.role == RoleEnum.ADMIN:
                # 学院管理员必须绑定且匹配项目所属学院，未绑定不得跨院审核
                if not operator.college_id or operator.college_id != project.college_id:
                    raise PermissionDeniedException(message="仅本院学院管理员可执行学院初审")
                return
            raise PermissionDeniedException(message="当前用户无权进行学院初审")
        if stage == REVIEW_STAGE_UNIVERSITY:
            # 校级复审：仅真·超级管理员（绑定学院的学院管理员不得越权）
            if not is_super_admin(operator):
                raise PermissionDeniedException(message="仅系统管理员可执行校级复审")
            return
        if stage == REVIEW_STAGE_EXPERT:
            # 专家评审：需要是该项目被分配的专家
            from app.crud.review import ReviewCRUD as RC
            exists = RC.exist_by_project_stage_reviewer(
                project._sa_instance_state.session or Session.object_session(project),
                project.id, stage, operator.id
            )
            if not exists:
                # 真超级管理员可代专家操作（演示用），其他用户直接拒绝
                if not is_super_admin(operator):
                    raise PermissionDeniedException(message="您未被分配到该项目的专家评审任务")
            return
        if stage == REVIEW_STAGE_FINAL:
            # 结题验收：仅"被分配到该项目的专家" + 真超级管理员
            # （学院管理员不允许结题，避免学院干预校级终审）
            if is_super_admin(operator):
                return
            if operator.role != RoleEnum.EXPERT:
                raise PermissionDeniedException(message="仅系统管理员或被分配的专家可进行结题验收")
            assigned = ReviewCRUD.exist_by_project_stage_reviewer(
                Session.object_session(project), project.id, REVIEW_STAGE_EXPERT, operator.id
            )
            if not assigned:
                raise PermissionDeniedException(message="您未被分配到该项目的专家评审任务，无法进行结题验收")
            return
        raise PermissionDeniedException(message="无法识别的审核阶段")

    # ---------- 学院/校级/结题 通用审核 ----------
    @staticmethod
    def do_review(db: Session, req: ReviewCreateRequest, operator: SysUser) -> ReviewRecordItem:
        # 专家评审(阶段3)必须走专用打分接口，禁止经通用审核接口旁路立项
        if req.review_stage == REVIEW_STAGE_EXPERT:
            raise ParamValidateException(message="专家评审请使用专家评审接口 /api/reviews/expert")
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        ReviewService._ensure_can_review(project, req.review_stage, operator)

        from app.services.project_service import ProjectService
        # 截止日校验：指导教师确认最晚到学院初审审核日；结题验收上限为结题报告提交截止日
        if req.review_stage == REVIEW_STAGE_TEACHER and \
                ProjectService.is_past_deadline(ProjectService.get_teacher_confirm_deadline(db, project)):
            raise ParamValidateException(message="已超过指导教师确认截止日（学院初审审核日），无法确认")
        # 说明：结题报告"提交"受截止日限制，但验审核不再受截止日限制，
        # 否则按时提交的报告在截止日后无法验收，项目会永久停留在待结题(8)。

        # 结题验收前置：负责人须已提交结项验收报告，且满足结项三条件
        if req.review_stage == REVIEW_STAGE_FINAL:
            from app.services.project_service import ProjectService
            ProjectService._ensure_final_conditions(db, project)
            has_report = db.query(ProjReview).filter(
                ProjReview.project_id == project.id,
                ProjReview.review_stage == REVIEW_STAGE_FINAL,
                ProjReview.review_result == 99,  # 占位：报告已提交待验收
                ProjReview.is_deleted == 0,
            ).first()
            if not has_report:
                raise ParamValidateException(message="项目尚未提交结项验收报告，无法进行结题验收")

        # 同一阶段同一人只允许一次（排除占位记录）
        if ReviewCRUD.exist_real_review(db, project.id, req.review_stage, operator.id):
            if req.review_stage == REVIEW_STAGE_FINAL:
                # 结题验收：仅允许针对「最近一次重新提交的报告」再次验收；
                # 本轮已给出正式结论的不可重复提交（驳回后负责人修改重提可再次验收）
                from app.services.project_service import ProjectService
                round_start = ProjectService._final_round_start(db, project.id)
                latest = db.query(ProjReview).filter(
                    ProjReview.project_id == project.id,
                    ProjReview.review_stage == REVIEW_STAGE_FINAL,
                    ProjReview.reviewer_id == operator.id,
                    ProjReview.is_deleted == 0,
                    ProjReview.review_result.isnot(None),
                    ProjReview.review_result != 99,
                ).order_by(ProjReview.id.desc()).first()
                if latest and (round_start is None or latest.review_time >= round_start):
                    raise ParamValidateException(message="您已在本轮结题验收中提交过意见，请勿重复提交")
            else:
                raise ParamValidateException(message="您已在该阶段审核过此项目，请勿重复提交")

        # 如果存在占位记录，先删除再写正式记录
        placeholder = db.query(ProjReview).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage == req.review_stage,
            ProjReview.reviewer_id == operator.id,
            ProjReview.review_result == 99,
            ProjReview.is_deleted == 0,
        ).first()
        # 注意：结题验收阶段不能删除 result=99 的记录，它承载"报告正文+本轮验收起点"
        if placeholder and req.review_stage != REVIEW_STAGE_FINAL:
            db.delete(placeholder)

        # 写审核记录
        record = ReviewCRUD.create(db, {
            "project_id": project.id,
            "review_stage": req.review_stage,
            "reviewer_id": operator.id,
            "reviewer_name": operator.real_name,
            "review_result": req.review_result,
            "review_comment": req.review_comment,
            "review_time": datetime.now(),
        })

        # 更新项目状态
        if req.review_stage == REVIEW_STAGE_FINAL:
            # 结题验收：待所有被分配专家提交后按多数判定，避免一人通过即结题；
            # 超级管理员代理验收（本人未被分配为专家）时立即判定。
            from app.services.project_service import ProjectService
            assigned = ProjectService.assigned_expert_ids(db, project.id)
            latest = ProjectService.final_latest_reviews(db, project.id)
            done = (assigned & set(latest.keys())) if assigned else set(latest.keys())
            is_proxy = is_super_admin(operator) and operator.id not in assigned
            results: List[int] = []
            if is_proxy:
                results = [req.review_result]
            elif assigned and done >= assigned:
                results = [latest[rid].review_result for rid in assigned]
            if results:
                pass_count = sum(1 for r in results if r == REVIEW_RESULT_PASS)
                total = len(results)
                if pass_count * 2 >= total:
                    project.status = 9  # 多数通过 -> 已结题
                    project.reject_reason = None
                else:
                    project.status = 8  # 多数驳回 -> 退回待结题，可修改后重提
                    reason = f"结题验收未通过（{pass_count}/{total} 位专家同意）"
                    if req.review_result != REVIEW_RESULT_PASS and (req.review_comment or "").strip():
                        reason += f"：{req.review_comment.strip()}"
                    project.reject_reason = reason[:500]
            else:
                # 尚未全部提交：保持待结题，报告继续等待其余专家验收
                project.status = 8
        elif req.review_result == REVIEW_RESULT_PASS:
            project.status = ReviewService._next_status_after_pass(project.status, req.review_stage)
            if project.status == 6:
                project.approval_time = datetime.now()
            # 校级复审通过后默认进入「待分配评审专家(13)」；
            # 若复审前已预登记过专家占位记录，则直接进入「待专家评审(5)」
            if project.status == PROJECT_STATUS_PENDING_EXPERT_ASSIGN:
                has_placeholder = db.query(ProjReview.id).filter(
                    ProjReview.project_id == project.id,
                    ProjReview.review_stage == REVIEW_STAGE_EXPERT,
                    ProjReview.review_result == 99,
                    ProjReview.is_deleted == 0,
                ).first()
                if has_placeholder:
                    project.status = PROJECT_STATUS_PENDING_EXPERT
            # 说明：学院初审通过(2)、校级复审通过(4)为瞬时中间态，不落库；
            # 目标持久态已由 _next_status_after_pass 直接给出（3 / 13 / 5）
        else:
            # 驳回（含已废弃的 result=3"修改后重提"，统一按驳回处理）
            project.status = 10
            project.reject_reason = (req.review_comment or "")[:500]

        # 状态流转后同步"当前审批人"（待学院初审→学院管理员；其余阶段清空）
        from app.services.project_service import ProjectService
        ProjectService._sync_current_approver(db, project)

        db.flush()
        db.commit()
        db.refresh(record)
        return ReviewService._record_to_item(record)

    # ---------- 专家评审(含评分) ----------
    @staticmethod
    def do_expert_review(db: Session, req: ExpertReviewCreateRequest, operator: SysUser) -> ReviewRecordItem:
        # 打分动作：必须是专家本人，或真超级管理员（演示用代操作）；学院管理员不得代打
        if operator.role != RoleEnum.EXPERT and not is_super_admin(operator):
            raise PermissionDeniedException(message="仅专家可执行专家评审")
        # 行级锁：串行化同一项目的并发专家评审，
        # 避免"最后一位专家"并发判定导致重复立项/驳回判定或状态双写
        project = db.query(ProjProject).filter(
            ProjProject.id == req.project_id, ProjProject.is_deleted == 0
        ).with_for_update().first()
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        if project.status != 5:  # 待专家评审
            raise ParamValidateException(message="当前项目不处于专家评审阶段")

        # 专家是否被分配到此项目
        old = ReviewCRUD.get_expert_score(db, project.id, operator.id)
        # 占位记录 review_result=99 表示"已分配但未评审"，不能视为已完成
        if old and old.review_result and old.review_result != 99:
            raise ParamValidateException(message="您已完成此项目的评审，不能重复打分")
        # 未被分配的专家无权评审（超管可代操作）
        if not old and not is_super_admin(operator):
            raise PermissionDeniedException(message="您未被分配到该项目的专家评审任务")

        # 更新或创建评审记录
        if old:
            old.score = req.score
            old.dim_scores = req.dim_scores
            old.review_result = req.review_result
            old.review_comment = req.review_comment
            old.review_time = datetime.now()
            db.flush()
            record = old
        else:
            record = ReviewCRUD.create(db, {
                "project_id": project.id,
                "review_stage": REVIEW_STAGE_EXPERT,
                "reviewer_id": operator.id,
                "reviewer_name": operator.real_name,
                "review_result": req.review_result,
                "score": req.score,
                "dim_scores": req.dim_scores,
                "review_comment": req.review_comment,
                "review_time": datetime.now(),
            })

        # 自动立项判定：必须等"所有已分配专家"都完成评审后才判定，
        # 否则某位专家一通过就置为已立项(6)，其余已分配专家会因 status != 5 无法再提交打分。
        from app.models import ProjReview
        pending_assigned = db.query(func.count(ProjReview.id)).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.review_result == 99,  # 占位记录：已分配但尚未评审
            ProjReview.is_deleted == 0,
        ).scalar() or 0
        if pending_assigned == 0:
            reviews = db.query(ProjReview).filter(
                ProjReview.project_id == project.id,
                ProjReview.review_stage == REVIEW_STAGE_EXPERT,
                ProjReview.is_deleted == 0,
                ProjReview.review_result.isnot(None),
                ProjReview.review_result != 99,
            ).all()
            if reviews:
                pass_count = sum(1 for r in reviews if r.review_result == REVIEW_RESULT_PASS)
                total = len(reviews)
                scores = [float(r.score) for r in reviews if r.score is not None]
                avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
                pass_score = settings.EXPERT_PASS_SCORE
                # 双条件立项：多数专家同意（含平票）且平均分达到及格线；
                # 否则驳回，并写明具体依据，避免项目卡死在待专家评审
                if pass_count * 2 >= total and avg_score >= pass_score:
                    project.status = 6
                    project.approval_time = datetime.now()
                else:
                    project.status = 10
                    if pass_count * 2 < total:
                        project.reject_reason = f"专家评审未通过（{pass_count}/{total} 位专家同意，未过半数）"
                    else:
                        project.reject_reason = f"专家评审未通过（平均分 {avg_score}，未达及格线 {pass_score}）"
        # 同步"当前审批人"：立项(6)/驳回(10) 与"待专家评审(5)"均无单一审批人，统一置空
        from app.services.project_service import ProjectService
        ProjectService._sync_current_approver(db, project)
        db.commit()
        db.refresh(record)
        return ReviewService._record_to_item(record)

    # ---------- 分配专家 ----------
    @staticmethod
    def assign_experts(db: Session, req: ExpertAssignRequest, operator: SysUser):
        # 超级管理员可分配全校项目；学院管理员仅可分配本院项目
        if not is_super_admin(operator) and not is_college_admin(operator):
            raise PermissionDeniedException(message="仅管理员可分配专家")
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        # 学院管理员只能为本院项目分配专家
        if is_college_admin(operator) and operator.college_id != project.college_id:
            raise PermissionDeniedException(message="仅可分配本院项目的评审专家")
        # 可分配阶段：待校级复审(3，允许提前登记)、待分配评审专家(13)、待专家评审(5，尚未有人打分时补录)
        if project.status not in (3, 13, 5):
            raise ParamValidateException(
                message=f"当前项目状态为「{PROJECT_STATUS_NAME.get(project.status, project.status)}」，不可分配评审专家"
            )

        # 一旦有专家提交了正式评审，名单即锁定：否则移除专家后其评分仍参与结算，
        # 会出现「票已投、人被踢」的结果失真
        reviewed = db.query(ProjReview.id).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.review_result != 99,
            ProjReview.is_deleted == 0,
        ).first()
        if reviewed:
            raise ParamValidateException(message="该项目已有专家提交评审，无法调整专家名单")

        # 至少需分配 EXPERT_MIN_COUNT 位专家，避免单人一票定生死
        if len(set(req.expert_ids)) < settings.EXPERT_MIN_COUNT:
            raise ParamValidateException(
                message=f"每个项目至少需分配 {settings.EXPERT_MIN_COUNT} 位评审专家"
            )

        # 校验每个ID都是专家角色（管理员不可被当作评审专家分配）
        for eid in req.expert_ids:
            u = UserCRUD.get_by_id(db, eid)
            if not u or u.role != RoleEnum.EXPERT:
                raise ParamValidateException(message=f"用户ID={eid} 不是评审专家")

        # 获取该项目该阶段已有的占位记录（未评审的专家）
        existing = db.query(ProjReview).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.review_result == 99,
            ProjReview.is_deleted == 0,
        ).all()
        existing_ids = {r.reviewer_id for r in existing}
        new_ids = set(req.expert_ids)

        # 移除被取消分配的专家（仅未评审的占位记录可移除）
        for r in existing:
            if r.reviewer_id not in new_ids:
                db.delete(r)

        # 添加新分配的专家
        for eid in new_ids:
            if eid not in existing_ids:
                u = UserCRUD.get_by_id(db, eid)
                ReviewCRUD.create(db, {
                    "project_id": project.id,
                    "review_stage": REVIEW_STAGE_EXPERT,
                    "reviewer_id": u.id,
                    "reviewer_name": u.real_name,
                    "review_result": 99,  # 99 占位=未评审（展示层过滤）
                    "review_comment": None,
                    "review_time": datetime.now(),
                })
        # 13 → 5：完成专家分配后进入待专家评审；
        # 3(待校级复审) 阶段为提前登记，保持原状态，复审通过时再决定落 13 还是 5
        if project.status == PROJECT_STATUS_PENDING_EXPERT_ASSIGN:
            from app.services.project_service import ProjectService
            project.status = PROJECT_STATUS_PENDING_EXPERT
            ProjectService._sync_current_approver(db, project)
        db.commit()
        return {"assigned_count": len(new_ids), "project_id": project.id}

    # ---------- 项目审核流程 ----------
    @staticmethod
    def get_review_flow(db: Session, project_id: int, operator: SysUser) -> ProjectReviewFlowResponse:
        project = ProjectCRUD.get_by_id(db, project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        # 权限校验：复用项目详情的可见性规则（草稿仅本人/成员，教师限本院，专家限被分配）
        from app.services.project_service import ProjectService
        ProjectService.get_detail(db, project_id, operator)
        records_orm = ReviewCRUD.list_by_project(db, project_id)
        # 专家评审独立性：专家仅可见本人的专家/结题评审记录，
        # 不得看到其他专家的评分与评语（管理员/教师/学生仍可见全量流程记录）
        if operator.role == RoleEnum.EXPERT:
            records_orm = [
                r for r in records_orm
                if r.review_stage not in (REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL)
                or r.reviewer_id == operator.id
            ]
        records: List[ReviewRecordItem] = [
            ReviewService._record_to_item(r) for r in records_orm
            if r.review_result != 99  # 过滤占位记录
        ]
        stage = ReviewService._get_stage_from_status(project.status)
        # 已分配但未评审的专家(review_result=99, stage=3)
        assigned_expert_ids = [
            r.reviewer_id for r in records_orm
            if r.review_stage == 3 and r.review_result == 99
        ]
        return ProjectReviewFlowResponse(
            project_id=project_id,
            current_status=project.status,
            current_status_name=PROJECT_STATUS_NAME.get(project.status, str(project.status)),
            current_stage_name=REVIEW_STAGE_NAME.get(stage, "无"),
            records=records,
            assigned_expert_ids=assigned_expert_ids,
        )

    # ---------- 审核列表(教师/管理员) ----------
    @staticmethod
    def paginate(db: Session, pager: PaginationParams, stage: Optional[int] = None,
                 status: Optional[int] = None, keyword: Optional[str] = None):
        items, total = ReviewCRUD.paginate(db, pager.offset, pager.limit, stage, status, keyword)

        # [P1-4] 消除N+1：原来每条 review 都单独查一次 Project
        # 用 IN 查询一次性把所有关联项目拉到内存 dict，再在结果循环中 O(1) 取
        project_id_to_name: dict = {}
        project_ids = list({r.project_id for r in items if r.project_id})
        if project_ids:
            from app.models import ProjProject
            rows = db.query(ProjProject.id, ProjProject.project_name).filter(
                ProjProject.id.in_(project_ids),
                ProjProject.is_deleted == 0,
            ).all()
            project_id_to_name = {pid: pname for pid, pname in rows}

        result = []
        for r in items:
            item = ReviewRecordItem.model_validate(r)
            item.review_stage_name = REVIEW_STAGE_NAME.get(item.review_stage, "")
            item.review_result_name = REVIEW_RESULT_NAME.get(item.review_result, "已分配")
            if item.review_result == 99:
                item.review_result_name = "待评审"
            # 回填项目名（若ReviewRecordItem有project_name字段则自动生效）
            if hasattr(item, "project_name") and not item.project_name:
                item.project_name = project_id_to_name.get(r.project_id)
            result.append(item)
        return result, total

    # ---------- 待我审核项目列表(教师/学院管理员/超管) ----------
    @staticmethod
    def pending_projects(db: Session, operator: SysUser, pager: PaginationParams,
                         keyword: Optional[str] = None):
        """根据当前用户角色，返回待其审核的项目列表"""
        from app.schemas.project import ProjectListItem
        from app.crud.project import ProjectCRUD

        q = db.query(ProjProject).filter(ProjProject.is_deleted == 0)

        if operator.role == RoleEnum.TEACHER:
            # 教师：仅"待指导教师确认(status=12)"且自己是该项目的指导教师
            # （学院初审由学院管理员负责，指导教师不参与）
            q = q.filter(ProjProject.status == 12, ProjProject.teacher_id == operator.id)
        elif operator.role == RoleEnum.ADMIN and operator.college_id:
            # 学院管理员：待学院初审(status=1) 且 本院项目
            q = q.filter(ProjProject.status == 1, ProjProject.college_id == operator.college_id)
        elif operator.role == RoleEnum.ADMIN and not operator.college_id:
            # 超级管理员：待校级复审(3) + 待分配评审专家(13) 均为其待办
            q = q.filter(ProjProject.status.in_(
                [PROJECT_STATUS_PENDING_UNIVERSITY, PROJECT_STATUS_PENDING_EXPERT_ASSIGN]
            ))
        else:
            return [], 0

        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(or_(ProjProject.project_name.like(kw), ProjProject.project_no.like(kw)))

        total = q.with_entities(func.count(ProjProject.id)).scalar() or 0
        items = q.order_by(ProjProject.submit_time.desc()).offset(pager.offset).limit(pager.limit).all()

        # 批量补充学院/负责人/指导教师名称
        college_ids = list({p.college_id for p in items if p.college_id})
        leader_ids = list({p.leader_id for p in items if p.leader_id})
        teacher_ids = list({p.teacher_id for p in items if p.teacher_id})

        college_by_id: dict = {}
        if college_ids:
            colleges = CollegeCRUD.list_by_ids(db, college_ids)
            college_by_id = {c.id: c for c in colleges}
        user_by_id: dict = {}
        all_uids = list(set(leader_ids + teacher_ids))
        if all_uids:
            users = UserCRUD.list_by_ids(db, all_uids)
            user_by_id = {u.id: u for u in users}

        result = []
        for p in items:
            item = ProjectListItem.model_validate(p, from_attributes=True)
            item.project_type_name = ProjectCRUD.PROJECT_TYPE_NAME.get(p.project_type, "")
            item.project_level_name = ProjectCRUD.PROJECT_LEVEL_NAME.get(p.project_level, "")
            college = college_by_id.get(p.college_id)
            item.college_name = college.college_name if college else ""
            leader = user_by_id.get(p.leader_id)
            item.leader_name = leader.real_name if leader else ""
            teacher = user_by_id.get(p.teacher_id)
            item.teacher_name = teacher.real_name if teacher else None
            item.status_name = PROJECT_STATUS_NAME.get(p.status, "")
            result.append(item)
        return result, total

    # ---------- 专家项目列表（待办 / 已评审历史） ----------
    @staticmethod
    def _build_expert_items(db: Session, expert_id: int, items: List[ProjProject]) -> List[ExpertProjectItem]:
        """ORM 列表 -> ExpertProjectItem 列表。

        [P1-4] 消除N+1：原代码每个项目做 3 次DB查询（专家分数/学院/负责人），
        这里一次性批量查出所有需要的数据，然后按 ID 建字典。
        """
        project_ids = [p.id for p in items]
        college_ids = list({p.college_id for p in items if p.college_id})
        leader_ids = list({p.leader_id for p in items if p.leader_id})

        # 1) 各项目分配给该专家的打分 (ProjReview)
        score_by_project: dict = {}
        if project_ids:
            from app.models import ProjReview
            rows = db.query(ProjReview).filter(
                ProjReview.project_id.in_(project_ids),
                ProjReview.reviewer_id == expert_id,
                ProjReview.review_stage == REVIEW_STAGE_EXPERT,
                ProjReview.is_deleted == 0,
            ).all()
            for r in rows:
                score_by_project[r.project_id] = r

        # 2) 学院批量查询
        college_by_id: dict = {}
        if college_ids:
            colleges = CollegeCRUD.list_by_ids(db, college_ids)
            college_by_id = {c.id: c for c in colleges}

        # 3) 负责人批量查询
        leader_by_id: dict = {}
        if leader_ids:
            leaders = UserCRUD.list_by_ids(db, leader_ids)
            leader_by_id = {u.id: u for u in leaders}

        result: List[ExpertProjectItem] = []
        for p in items:
            record = score_by_project.get(p.id)
            college = college_by_id.get(p.college_id)
            leader = leader_by_id.get(p.leader_id)
            result.append(ExpertProjectItem(
                project_id=p.id,
                project_no=p.project_no,
                project_name=p.project_name,
                college_name=college.college_name if college else "",
                leader_name=leader.real_name if leader else "",
                project_type_name=ProjectCRUD.PROJECT_TYPE_NAME.get(p.project_type, ""),
                project_level_name=ProjectCRUD.PROJECT_LEVEL_NAME.get(p.project_level, ""),
                submit_time=p.submit_time,
                status=p.status,
                my_score=record.score if record and record.review_result != 99 else None,
                my_review_result=record.review_result if record and record.review_result != 99 else None,
            ))
        return result

    @staticmethod
    def expert_pending_projects(db: Session, expert_id: int, pager: PaginationParams,
                                keyword: Optional[str] = None):
        """专家"待办"项目：需要该专家本人操作的项目（待评审 5 / 待结题验收 8）。"""
        items, total = ReviewCRUD.expert_pending_projects(
            db, expert_id, pager.offset, pager.limit, keyword
        )
        return ReviewService._build_expert_items(db, expert_id, items), total

    @staticmethod
    def expert_reviewed_projects(db: Session, expert_id: int, pager: PaginationParams,
                                 keyword: Optional[str] = None):
        """专家"已评审"历史项目：该专家本人已出评审/结题验收结果的项目，供回看。"""
        items, total = ReviewCRUD.expert_reviewed_projects(
            db, expert_id, pager.offset, pager.limit, keyword
        )
        return ReviewService._build_expert_items(db, expert_id, items), total

    # ---------- 辅助：ORM -> Pydantic ----------
    @staticmethod
    def _record_to_item(r) -> ReviewRecordItem:
        item = ReviewRecordItem.model_validate(r)
        item.review_stage_name = REVIEW_STAGE_NAME.get(item.review_stage, "")
        item.review_result_name = REVIEW_RESULT_NAME.get(item.review_result, "已分配")
        if item.review_result == 99:
            item.review_result_name = "待评审"
        return item


class MidtermService:
    """中期检查业务服务"""

    @staticmethod
    def get_by_project(db: Session, project_id: int, operator: SysUser) -> Optional[MidtermCheckResponse]:
        project = ProjectCRUD.get_by_id(db, project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        # 归属校验：复用项目详情可见性规则（草稿仅本人/成员，教师限本院，专家限被分配）
        from app.services.project_service import ProjectService
        ProjectService.get_detail(db, project_id, operator)
        obj = MidtermCRUD.get_by_project(db, project_id)
        if not obj:
            return None
        item = MidtermCheckResponse.model_validate(obj)
        item.status_name = MIDTERM_STATUS_NAME.get(item.status, "")
        return item

    @staticmethod
    def submit(db: Session, req: MidtermCheckCreate, operator: SysUser, is_draft: bool) -> MidtermCheckResponse:
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        # 中期检查提交仅限项目负责人本人（真超级管理员可代操作）
        if not is_super_admin(operator) and project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可提交中期检查")
        # 仅"已立项(6)/中期检查中(7)"可提交中期检查：状态 8(待结题) 时中期必已通过，
        # 重复提交会被下方 existing.status==2 拦截，此处置为 6/7 与前端按钮可见范围一致
        if project.status not in (6, 7):
            raise ParamValidateException(message="仅已立项/中期检查中阶段可提交中期检查")
        # 截止日校验：中期报告须在『中期报告提交截止日』前提交（草稿不受限）
        if not is_draft:
            from app.services.project_service import ProjectService
            if ProjectService.is_past_deadline(ProjectService.get_midterm_deadline(db, project)):
                raise ParamValidateException(message="已超过中期报告提交截止日，无法提交中期检查")

        # 检查现有中期检查状态，防止重复提交/修改
        existing = MidtermCRUD.get_by_project(db, req.project_id)
        if existing:
            # 已通过(2)：不可再修改
            if existing.status == 2:
                raise ParamValidateException(message="中期检查已审核通过，不可再修改")
            # 待审核(1)：不可修改或重复提交（如需修改请等待审核结果）
            if existing.status == 1:
                raise ParamValidateException(message="中期检查正在审核中，不可修改")

        data = req.model_dump()
        attachment_ids = data.pop("attachment_ids", None) or []
        if is_draft:
            data["status"] = 0
        else:
            data["status"] = 1
            data["submit_time"] = datetime.now()
            # 项目状态切到中期检查中
            if project.status == 6:
                project.status = 7
        obj = MidtermCRUD.create_or_update(db, data)
        # 关联中期报告附件到项目（仅限本人上传的临时附件，防止劫持他人/其他业务附件）
        if attachment_ids:
            from app.models.user import SysAttachment
            db.query(SysAttachment).filter(
                SysAttachment.id.in_(attachment_ids),
                SysAttachment.biz_type == "project",
                SysAttachment.biz_id == 0,
                SysAttachment.uploader_id == operator.id,
                SysAttachment.is_deleted == 0,
            ).update({SysAttachment.biz_id: req.project_id}, synchronize_session=False)
        db.commit()
        db.refresh(obj)
        item = MidtermCheckResponse.model_validate(obj)
        item.status_name = MIDTERM_STATUS_NAME.get(item.status, "")
        return item

    @staticmethod
    def withdraw(db: Session, check_id: int, operator: SysUser) -> MidtermCheckResponse:
        """撤回中期检查报告提交：仅项目负责人本人（真超级管理员可代操作）。
        撤回后记录退回草稿(0)，项目仍停留在「中期检查中(7)」，可再次修改并重新提交。"""
        obj = MidtermCRUD.get_by_id(db, check_id)
        if not obj:
            raise ResourceNotFoundException(message="中期检查记录不存在")
        project = ProjectCRUD.get_by_id(db, obj.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        if not is_super_admin(operator) and project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可撤回中期检查提交")
        if obj.status != 1:
            raise ParamValidateException(message="仅『待审核』的中期检查可撤回提交")
        # 截止日校验：超过中期报告截止日不允许撤回，否则撤回后将无法再次提交而卡死流程
        from app.services.project_service import ProjectService
        if ProjectService.is_past_deadline(ProjectService.get_midterm_deadline(db, project)):
            raise ParamValidateException(message="已超过中期报告截止日，无法撤回中期检查")
        # 退回草稿：项目状态保持不变（仍为 7 中期检查中），可再次编辑后重新提交
        obj.status = 0
        db.commit()
        db.refresh(obj)
        item = MidtermCheckResponse.model_validate(obj)
        item.status_name = MIDTERM_STATUS_NAME.get(item.status, "")
        return item

    @staticmethod
    def review(db: Session, req: MidtermReviewRequest, operator: SysUser) -> MidtermCheckResponse:
        obj = MidtermCRUD.get_by_id(db, req.check_id)
        if not obj:
            raise ResourceNotFoundException(message="中期检查记录不存在")
        if obj.status != 1:
            raise ParamValidateException(message="当前状态不可审核")
        # 权限校验：仅项目的指导教师本人可审核（超管可代操作）
        project = ProjectCRUD.get_by_id(db, obj.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        if not is_super_admin(operator) and operator.id != project.teacher_id:
            raise PermissionDeniedException(message="仅该项目的指导教师可审核中期检查")
        # 说明：截止日仅限制"提交"，按时提交的报告在截止日后仍可审核，
        # 否则教师未及时审核会导致项目永久停留在中期检查中(7)。
        # 1 通过 -> 状态2；2 驳回 -> 状态4；3 修改 -> 状态3
        obj.reviewer_id = operator.id
        obj.review_comment = req.review_comment
        obj.review_time = datetime.now()
        if req.result == 1:
            obj.status = 2
            # 中期检查通过：项目从"中期检查中(7)"流转到"待结题(8)"
            project = ProjectCRUD.get_by_id(db, obj.project_id)
            if project and project.status == 7:
                project.status = 8
        elif req.result == 2:
            obj.status = 4
        else:
            obj.status = 3
        db.commit()
        db.refresh(obj)
        item = MidtermCheckResponse.model_validate(obj)
        item.status_name = MIDTERM_STATUS_NAME.get(item.status, "")
        return item


class ChangeService:
    """变更/延期申请业务服务"""

    @staticmethod
    def create(db: Session, req: ChangeRequestCreate, operator: SysUser) -> ChangeRequestResponse:
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        from app.services.project_service import ProjectService
        # 先清扫已超审批缓冲期的待审核申请（置为已作废，留档）
        ProjectService.sweep_expired_change_requests(db, [project.id])
        # 提交窗口：截止日驱动（锁死日 = 项目当前阶段的审核日；比赛未配置时间表则不锁）
        if project.status not in ProjectService.CHANGE_WINDOW_STATUSES:
            raise ParamValidateException(message="当前项目阶段不可提交变更/延期申请")
        if ProjectService.is_past_deadline(ProjectService.get_change_deadline(db, project)):
            raise ParamValidateException(message="已超过当前阶段的审核日，项目已锁定，无法提交变更/延期申请")
        # 变更/延期申请仅限项目负责人本人发起（真超级管理员可代操作）
        if not is_super_admin(operator) and project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可发起变更申请")
        # 配额：① 每阶段限 1 次（待校级复审、待专家评审 各 1 次）② 累计上限 CHANGE_MAX_TIMES 次
        # 说明：已撤回占用名额（撤回不退名额）；系统超期自动『已作废』不计入
        counted = (
            ProjChangeRequest.project_id == project.id,
            ProjChangeRequest.is_deleted == 0,
            ProjChangeRequest.status.notin_([CHANGE_STATUS_EXPIRED]),
        )
        stage_used = db.query(func.count(ProjChangeRequest.id)).filter(
            *counted,
            ProjChangeRequest.project_status_at_submit == project.status,
        ).scalar() or 0
        if stage_used >= 1:
            raise ParamValidateException(message="当前阶段已提交过变更/延期申请（每阶段限 1 次）")
        used = db.query(func.count(ProjChangeRequest.id)).filter(*counted).scalar() or 0
        if used >= CHANGE_MAX_TIMES:
            raise ParamValidateException(message=f"变更申请次数已达上限（共{CHANGE_MAX_TIMES}次）")
        # 同一项目不允许同时存在待审核的申请
        pending = db.query(ProjChangeRequest.id).filter(
            ProjChangeRequest.project_id == project.id,
            ProjChangeRequest.is_deleted == 0,
            ProjChangeRequest.status == CHANGE_STATUS_PENDING,
        ).first()
        if pending:
            raise ParamValidateException(message="存在待审批的变更申请，请等待审批完成")
        data = req.model_dump()
        data["applicant_id"] = operator.id
        data["status"] = CHANGE_STATUS_PENDING
        data["submit_time"] = datetime.now()
        # 记录提交时项目所处阶段，作为「每阶段限 1 次」配额依据
        data["project_status_at_submit"] = project.status
        obj = ChangeCRUD.create(db, data)
        db.commit()
        db.refresh(obj)
        return ChangeService._to_item(obj)

    @staticmethod
    def paginate(db: Session, pager: PaginationParams, project_id=None, change_type=None,
                 status=None, operator: SysUser = None):
        applicant_id = None
        project_ids = None
        if operator is not None:
            if operator.role == RoleEnum.STUDENT:
                # 学生：仅本人发起的申请；清扫范围也限制在本人申请涉及的项目
                applicant_id = operator.id
                project_ids = [pid for (pid,) in db.query(ProjChangeRequest.project_id).filter(
                    ProjChangeRequest.applicant_id == operator.id,
                    ProjChangeRequest.is_deleted == 0,
                ).distinct().all()]
            elif is_super_admin(operator):
                # 超级管理员：全校可查
                pass
            elif is_college_admin(operator):
                # 学院管理员：仅本院项目
                project_ids = [pid for (pid,) in db.query(ProjProject.id).filter(
                    ProjProject.is_deleted == 0,
                    ProjProject.college_id == operator.college_id,
                ).all()] if operator.college_id else []
            elif operator.role == RoleEnum.TEACHER:
                # 教师：仅本人指导的项目
                project_ids = [pid for (pid,) in db.query(ProjProject.id).filter(
                    ProjProject.is_deleted == 0,
                    ProjProject.teacher_id == operator.id,
                ).all()]
            elif operator.role == RoleEnum.EXPERT:
                # 专家：仅被分配评审的项目
                project_ids = [pid for (pid,) in db.query(ProjReview.project_id).filter(
                    ProjReview.reviewer_id == operator.id,
                    ProjReview.review_stage == REVIEW_STAGE_EXPERT,
                    ProjReview.is_deleted == 0,
                ).distinct().all()]
            else:
                project_ids = []
        # 查询前先清扫已超审批缓冲期的待审核申请（置为已作废，留档）
        from app.services.project_service import ProjectService
        ProjectService.sweep_expired_change_requests(db, project_ids)
        items, total = ChangeCRUD.paginate(
            db, pager.offset, pager.limit, project_id, change_type, status, applicant_id,
            project_ids=project_ids,
        )
        # 批量回填项目名称，避免逐条查询
        name_map = {}
        pids = {i.project_id for i in items}
        if pids:
            name_map = dict(db.query(ProjProject.id, ProjProject.project_name).filter(
                ProjProject.id.in_(pids)
            ).all())
        result = []
        for i in items:
            it = ChangeService._to_item(i)
            it.project_name = name_map.get(i.project_id)
            result.append(it)
        return result, total

    @staticmethod
    def approve(db: Session, change_id: int, approve: bool, comment: str, operator: SysUser):
        obj = ChangeCRUD.get_by_id(db, change_id)
        if not obj:
            raise ResourceNotFoundException(message="申请不存在")
        project = ProjectCRUD.get_by_id(db, obj.project_id)
        if not project:
            raise ResourceNotFoundException(message="关联项目不存在")
        # 审批人：该项目的指导教师本人 / 项目所属学院的学院管理员（真超级管理员可代操作）
        if not is_super_admin(operator):
            is_project_teacher = operator.role == RoleEnum.TEACHER and project.teacher_id == operator.id
            is_project_college_admin = (
                is_college_admin(operator)
                and operator.college_id == project.college_id
            )
            if not (is_project_teacher or is_project_college_admin):
                raise PermissionDeniedException(message="仅该项目的指导教师或所属学院管理员可审批变更申请")
        if obj.status != CHANGE_STATUS_PENDING:
            raise ParamValidateException(message="该申请已完成审批或已撤回，不可重复审批")
        # 提交时所处的审核段（决定退回目标与审批截止日）
        from_status = obj.project_status_at_submit or project.status
        # 项目可能已被后续审核推进（如校级复审通过），此时不能按旧申请强行回退，
        # 否则会把已进入专家评审/已立项的项目拉回学院初审并清空后续审核记录。
        if project.status != from_status:
            raise ParamValidateException(
                message=f"项目当前状态[{PROJECT_STATUS_NAME.get(project.status, project.status)}]"
                        f"已不同于申请提交时状态[{PROJECT_STATUS_NAME.get(from_status, from_status)}]，"
                        f"无法按原申请回退"
            )
        # 审批须在『提交阶段审核日 + 1 天缓冲期』内完成；超期申请会被自动作废
        from app.services.project_service import ProjectService
        _deadline = ProjectService.get_change_deadline_for_status(db, project, from_status)
        if _deadline is not None and date.today() > _deadline + timedelta(days=1):
            raise ParamValidateException(message="已超过审批缓冲期，该申请已自动作废，不可审批")
        # 驳回：仅记录申请状态，不影响项目流程（项目停留在原阶段可继续处理）
        if not approve:
            obj.status = CHANGE_STATUS_REJECTED
            obj.reject_reason = comment
            db.commit()
            db.refresh(obj)
            return ChangeService._to_item(obj)
        # 通过：按「提交时所处的审核段」退回上一审核段，重走该段之后的流程
        #  - 待校级复审(3) 提交 → 退回待学院初审(1)
        #  - 待专家评审(5) 提交 → 退回待校级复审(3)
        if from_status == PROJECT_STATUS_PENDING_EXPERT:
            target_status = PROJECT_STATUS_PENDING_UNIVERSITY
            clear_stages = [REVIEW_STAGE_UNIVERSITY, REVIEW_STAGE_EXPERT]
        else:
            target_status = PROJECT_STATUS_PENDING_COLLEGE
            clear_stages = [REVIEW_STAGE_COLLEGE, REVIEW_STAGE_UNIVERSITY, REVIEW_STAGE_EXPERT]
        obj.status = CHANGE_STATUS_APPROVED
        obj.approval_time = datetime.now()
        # 清除退回后需重审的评审记录（保留专家分配占位 result=99，使学院/校级/专家可重新评审）
        db.query(ProjReview).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage.in_(clear_stages),
            ProjReview.review_result != 99,
            ProjReview.is_deleted == 0,
        ).update({ProjReview.is_deleted: 1}, synchronize_session=False)
        project.status = target_status
        project.reject_reason = None
        from app.services.project_service import ProjectService
        ProjectService._sync_current_approver(db, project)
        db.commit()
        db.refresh(obj)
        return ChangeService._to_item(obj)

    @staticmethod
    def withdraw(db: Session, change_id: int, operator: SysUser) -> ChangeRequestResponse:
        """撤回变更申请：仅申请人本人（真超级管理员可代操作），且申请处于待审核(0)。"""
        obj = ChangeCRUD.get_by_id(db, change_id)
        if not obj:
            raise ResourceNotFoundException(message="申请不存在")
        if not is_super_admin(operator) and obj.applicant_id != operator.id:
            raise PermissionDeniedException(message="仅申请人可撤回变更申请")
        if obj.status != CHANGE_STATUS_PENDING:
            raise ParamValidateException(message="仅『待审核』的变更申请可撤回")
        obj.status = CHANGE_STATUS_WITHDRAWN
        db.commit()
        db.refresh(obj)
        return ChangeService._to_item(obj)

    @staticmethod
    def resubmit(db: Session, change_id: int, req: ChangeRequestCreate, operator: SysUser) -> ChangeRequestResponse:
        """被驳回的变更申请：申请人修改后复用同一条记录重新提交（已驳回(4) -> 待审核(0)）。"""
        obj = ChangeCRUD.get_by_id(db, change_id)
        if not obj:
            raise ResourceNotFoundException(message="申请不存在")
        if not is_super_admin(operator) and obj.applicant_id != operator.id:
            raise PermissionDeniedException(message="仅申请人可重新提交变更申请")
        if obj.status != CHANGE_STATUS_REJECTED:
            raise ParamValidateException(message="仅『已驳回』的变更申请可修改后重新提交")
        if req.project_id != obj.project_id:
            raise ParamValidateException(message="项目不一致，无法重新提交")
        project = ProjectCRUD.get_by_id(db, obj.project_id)
        from app.services.project_service import ProjectService
        if not project or project.status not in ProjectService.CHANGE_WINDOW_STATUSES:
            raise ParamValidateException(message="当前项目阶段不可提交变更/延期申请")
        if ProjectService.is_past_deadline(ProjectService.get_change_deadline(db, project)):
            raise ParamValidateException(message="已超过当前阶段的审核日，项目已锁定，无法重新提交变更/延期申请")
        # 分阶段配额：当前阶段若已被其他申请占用名额，则不允许改后重提
        other_same_stage = db.query(func.count(ProjChangeRequest.id)).filter(
            ProjChangeRequest.project_id == project.id,
            ProjChangeRequest.id != obj.id,
            ProjChangeRequest.is_deleted == 0,
            ProjChangeRequest.status.notin_([CHANGE_STATUS_EXPIRED]),
            ProjChangeRequest.project_status_at_submit == project.status,
        ).scalar() or 0
        if other_same_stage >= 1:
            raise ParamValidateException(message="当前阶段已提交过变更/延期申请（每阶段限 1 次）")
        obj.change_type = req.change_type
        obj.change_reason = req.change_reason
        obj.original_content = req.original_content
        obj.new_content = req.new_content
        obj.status = CHANGE_STATUS_PENDING
        obj.reject_reason = None
        obj.submit_time = datetime.now()
        # 改后重提占用「当前阶段」名额（原记录所属阶段随之更新）
        obj.project_status_at_submit = project.status
        db.commit()
        db.refresh(obj)
        return ChangeService._to_item(obj)

    @staticmethod
    def _to_item(obj) -> ChangeRequestResponse:
        item = ChangeRequestResponse.model_validate(obj)
        item.change_type_name = CHANGE_TYPE_NAME.get(item.change_type, "")
        item.status_name = CHANGE_STATUS_NAME.get(item.status, "")
        return item
