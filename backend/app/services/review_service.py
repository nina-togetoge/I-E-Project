"""
项目审核模块 业务逻辑层(Service)
三级流程：学院初审(College) -> 校级复审(University) -> 专家评审(Expert) -> 立项(Approved)
另外含中期检查、变更/延期审批
"""
from typing import List, Tuple, Optional
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.security import RoleEnum
from app.core.exceptions import (
    PermissionDeniedException, ResourceNotFoundException, ParamValidateException,
)
from app.core.deps import PaginationParams, DataScope
from app.crud.project import ProjectCRUD
from app.crud.user import UserCRUD, CollegeCRUD
from app.crud.review import ReviewCRUD, MidtermCRUD, ChangeCRUD
from app.models import (
    ProjProject, SysUser,
)
from app.schemas.review import (
    ReviewCreateRequest, ExpertReviewCreateRequest, ExpertAssignRequest,
    ReviewRecordItem, ProjectReviewFlowResponse, ExpertProjectItem,
    MidtermCheckCreate, MidtermCheckResponse, MidtermReviewRequest,
    ChangeRequestCreate, ChangeRequestResponse,
    REVIEW_STAGE_COLLEGE, REVIEW_STAGE_UNIVERSITY, REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL,
    REVIEW_STAGE_NAME, REVIEW_RESULT_PASS, REVIEW_RESULT_REJECT, REVIEW_RESULT_MODIFY,
    REVIEW_RESULT_NAME, CHANGE_TYPE_NAME, CHANGE_STATUS_NAME, MIDTERM_STATUS_NAME,
)
from app.schemas.project import PROJECT_STATUS_NAME


class ReviewService:
    """审核流程服务"""

    # ---- 状态流转辅助方法 ----
    @staticmethod
    def _next_status_after_pass(current_status: int, stage: int) -> int:
        """根据当前状态 + 审核阶段，计算审核通过后的下一个状态"""
        # 阶段1学院初审通过 -> 状态2学院初审通过 -> 然后到状态3待校级复审
        if stage == REVIEW_STAGE_COLLEGE:
            return 3  # 学院初审通过后 -> 待校级复审
        if stage == REVIEW_STAGE_UNIVERSITY:
            return 5  # 校级复审通过后 -> 待专家评审
        if stage == REVIEW_STAGE_EXPERT:
            return 6  # 专家评审通过 -> 已立项
        if stage == REVIEW_STAGE_FINAL:
            return 9  # 结题验收通过 -> 已结题
        return current_status

    @staticmethod
    def _get_stage_from_status(status: int) -> int:
        """根据项目当前状态，推断它当前处于哪个审核阶段"""
        if status == 1:
            return REVIEW_STAGE_COLLEGE
        if status == 3:
            return REVIEW_STAGE_UNIVERSITY
        if status == 5:
            return REVIEW_STAGE_EXPERT
        if status == 8:
            return REVIEW_STAGE_FINAL
        return 0

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
        if stage == REVIEW_STAGE_COLLEGE:
            if operator.role == RoleEnum.ADMIN:
                return
            # 学院初审：本院教师/管理员 role==2 且 college_id 相同
            if operator.role == RoleEnum.TEACHER:
                if operator.college_id != project.college_id:
                    raise PermissionDeniedException(message="仅本院教师/管理员可执行学院初审")
                return
            raise PermissionDeniedException(message="当前用户无权进行学院初审")
        if stage == REVIEW_STAGE_UNIVERSITY:
            if operator.role not in (RoleEnum.ADMIN,):
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
                raise PermissionDeniedException(message="您未被分配到该项目的专家评审任务")
            return
        if stage == REVIEW_STAGE_FINAL:
            if operator.role not in (RoleEnum.ADMIN, RoleEnum.EXPERT):
                raise PermissionDeniedException(message="仅管理员或专家可进行结题验收")
            return
        raise PermissionDeniedException(message="无法识别的审核阶段")

    # ---------- 学院/校级/结题 通用审核 ----------
    @staticmethod
    def do_review(db: Session, req: ReviewCreateRequest, operator: SysUser) -> ReviewRecordItem:
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        ReviewService._ensure_can_review(project, req.review_stage, operator)

        # 同一阶段同一人只允许一次
        if ReviewCRUD.exist_by_project_stage_reviewer(db, project.id, req.review_stage, operator.id):
            raise ParamValidateException(message="您已在该阶段审核过此项目，请勿重复提交")

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
        if req.review_result == REVIEW_RESULT_PASS:
            project.status = ReviewService._next_status_after_pass(project.status, req.review_stage)
            if project.status == 6:
                project.approval_time = datetime.now()
            if req.review_stage == REVIEW_STAGE_COLLEGE:
                # 还需先写中间状态2(学院初审通过)，然后流程可配置是否自动到3
                project.status = 2
                # 保存后下一步：直接自动进入待校级复审 (可按实际业务开关)
                project.status = 3
        elif req.review_result == REVIEW_RESULT_REJECT:
            project.status = 10
            project.reject_reason = (req.review_comment or "")[:500]
        elif req.review_result == REVIEW_RESULT_MODIFY:
            # 修改后重提：驳回回草稿，提示原因
            project.status = 10
            project.reject_reason = ("[修改后重提] " + (req.review_comment or ""))[:500]

        db.flush()
        db.commit()
        db.refresh(record)
        return ReviewService._record_to_item(record)

    # ---------- 专家评审(含评分) ----------
    @staticmethod
    def do_expert_review(db: Session, req: ExpertReviewCreateRequest, operator: SysUser) -> ReviewRecordItem:
        if operator.role not in (RoleEnum.EXPERT, RoleEnum.ADMIN):
            raise PermissionDeniedException(message="仅专家可执行专家评审")
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        if project.status != 5:  # 待专家评审
            raise ParamValidateException(message="当前项目不处于专家评审阶段")

        # 专家是否被分配到此项目
        old = ReviewCRUD.get_expert_score(db, project.id, operator.id)
        if old and old.review_result:
            raise ParamValidateException(message="您已完成此项目的评审，不能重复打分")

        # 更新或创建评审记录
        if old:
            old.score = req.score
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
                "review_comment": req.review_comment,
                "review_time": datetime.now(),
            })

        # 简单的自动立项判定：专家评审均分>=60且至少1位专家已评审通过，则进入已立项
        # 真实场景：等所有专家完成后再判定，这里做演示逻辑
        from app.models import ProjReview
        reviews = db.query(ProjReview).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.is_deleted == 0,
            ProjReview.review_result.isnot(None),
        ).all()
        if reviews:
            pass_count = sum(1 for r in reviews if r.review_result == REVIEW_RESULT_PASS)
            total = len(reviews)
            # 简单：多数通过则立项（可根据实际业务调整规则）
            if pass_count * 2 >= total:
                project.status = 6
                project.approval_time = datetime.now()
        db.commit()
        db.refresh(record)
        return ReviewService._record_to_item(record)

    # ---------- 分配专家 ----------
    @staticmethod
    def assign_experts(db: Session, req: ExpertAssignRequest, operator: SysUser):
        if operator.role not in (RoleEnum.ADMIN,):
            raise PermissionDeniedException(message="仅管理员可分配专家")
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")

        # 校验每个ID都是专家角色
        for eid in req.expert_ids:
            u = UserCRUD.get_by_id(db, eid)
            if not u or u.role not in (RoleEnum.EXPERT, RoleEnum.ADMIN):
                raise ParamValidateException(message=f"用户ID={eid} 不是评审专家")
            # 创建空审核记录（占位=已分配，分数/结果待填）
            if not ReviewCRUD.exist_by_project_stage_reviewer(db, project.id, req.review_stage, eid):
                ReviewCRUD.create(db, {
                    "project_id": project.id,
                    "review_stage": req.review_stage,
                    "reviewer_id": u.id,
                    "reviewer_name": u.real_name,
                    "review_result": 99,  # 99 占位=未评审（展示层过滤）
                    "review_comment": None,
                    "review_time": datetime.now(),
                })
        # 分配专家后，如果项目还在4（校级通过），自动进入阶段5（待专家评审）
        if project.status == 4:
            project.status = 5
        db.commit()
        return {"assigned_count": len(req.expert_ids), "project_id": project.id}

    # ---------- 项目审核流程 ----------
    @staticmethod
    def get_review_flow(db: Session, project_id: int, operator: SysUser) -> ProjectReviewFlowResponse:
        project = ProjectCRUD.get_by_id(db, project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        records_orm = ReviewCRUD.list_by_project(db, project_id)
        records: List[ReviewRecordItem] = [
            ReviewService._record_to_item(r) for r in records_orm
            if r.review_result != 99  # 过滤占位记录
        ]
        stage = ReviewService._get_stage_from_status(project.status)
        return ProjectReviewFlowResponse(
            project_id=project_id,
            current_status=project.status,
            current_status_name=PROJECT_STATUS_NAME.get(project.status, str(project.status)),
            current_stage_name=REVIEW_STAGE_NAME.get(stage, "无"),
            records=records,
        )

    # ---------- 专家待评项目列表 ----------
    @staticmethod
    def expert_pending_projects(db: Session, expert_id: int, pager: PaginationParams,
                                keyword: Optional[str] = None):
        items, total = ReviewCRUD.expert_pending_projects(
            db, expert_id, pager.offset, pager.limit, keyword
        )
        result: List[ExpertProjectItem] = []
        for p in items:
            record = ReviewCRUD.get_expert_score(db, p.id, expert_id)
            college = CollegeCRUD.get_by_id(db, p.college_id)
            leader = UserCRUD.get_by_id(db, p.leader_id)
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
        return result, total

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
        obj = MidtermCRUD.get_by_project(db, project_id)
        if not obj:
            return None
        item = MidtermCheckResponse.model_validate(obj)
        item.status_name = MIDTERM_STATUS_NAME.get(item.status, "")
        return item

    @staticmethod
    def submit(db: Session, req: MidtermCheckCreate, operator: SysUser, is_draft: bool) -> MidtermCheckResponse:
        project = ProjectCRUD.get_by_project(db, req.project_id) or ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        if operator.role == RoleEnum.STUDENT and project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可提交中期检查")
        if project.status not in (6, 7, 8):
            raise ParamValidateException(message="仅已立项/中期/待结题阶段可提交中期检查")

        data = req.model_dump()
        if is_draft:
            data["status"] = 0
        else:
            data["status"] = 1
            data["submit_time"] = datetime.now()
            # 项目状态切到中期检查中
            if project.status == 6:
                project.status = 7
        obj = MidtermCRUD.create_or_update(db, data)
        db.commit()
        db.refresh(obj)
        item = MidtermCheckResponse.model_validate(obj)
        item.status_name = MIDTERM_STATUS_NAME.get(item.status, "")
        return item

    @staticmethod
    def review(db: Session, req: MidtermReviewRequest, operator: SysUser) -> MidtermCheckResponse:
        if operator.role not in (RoleEnum.ADMIN, RoleEnum.TEACHER, RoleEnum.EXPERT):
            raise PermissionDeniedException(message="仅教师/管理员/专家可审核中期检查")
        obj = MidtermCRUD.get_by_id(db, req.check_id)
        if not obj:
            raise ResourceNotFoundException(message="中期检查记录不存在")
        if obj.status != 1:
            raise ParamValidateException(message="当前状态不可审核")
        # 1 通过 -> 状态2；2 驳回 -> 状态4；3 修改 -> 状态3
        obj.reviewer_id = operator.id
        obj.review_comment = req.review_comment
        obj.review_time = datetime.now()
        if req.result == 1:
            obj.status = 2
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
        if project.status not in (6, 7, 8):
            raise ParamValidateException(message="仅已立项/中期/待结题阶段可提交变更申请")
        if operator.role == RoleEnum.STUDENT and project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可发起变更申请")
        data = req.model_dump()
        data["applicant_id"] = operator.id
        data["status"] = 0
        data["submit_time"] = datetime.now()
        obj = ChangeCRUD.create(db, data)
        db.commit()
        db.refresh(obj)
        return ChangeService._to_item(obj)

    @staticmethod
    def paginate(db: Session, pager: PaginationParams, project_id=None, change_type=None,
                 status=None, operator: SysUser = None):
        applicant_id = None
        if operator and operator.role == RoleEnum.STUDENT:
            applicant_id = operator.id
        items, total = ChangeCRUD.paginate(
            db, pager.offset, pager.limit, project_id, change_type, status, applicant_id
        )
        return [ChangeService._to_item(i) for i in items], total

    @staticmethod
    def approve(db: Session, change_id: int, approve: bool, comment: str, operator: SysUser):
        if operator.role not in (RoleEnum.TEACHER, RoleEnum.ADMIN):
            raise PermissionDeniedException(message="仅教师/管理员可审批变更")
        obj = ChangeCRUD.get_by_id(db, change_id)
        if not obj:
            raise ResourceNotFoundException(message="申请不存在")
        if obj.status in (3, 4):
            raise ParamValidateException(message="该申请已完成审批，不可重复")
        # 简单流程：一级审批即完成（可扩展多级）
        if not approve:
            obj.status = 4
            obj.reject_reason = comment
        else:
            obj.status = 3
            obj.approval_time = datetime.now()
        db.commit()
        db.refresh(obj)
        return ChangeService._to_item(obj)

    @staticmethod
    def _to_item(obj) -> ChangeRequestResponse:
        item = ChangeRequestResponse.model_validate(obj)
        item.change_type_name = CHANGE_TYPE_NAME.get(item.change_type, "")
        item.status_name = CHANGE_STATUS_NAME.get(item.status, "")
        return item
