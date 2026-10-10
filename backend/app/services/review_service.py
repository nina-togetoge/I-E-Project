"""
项目审核模块 业务逻辑层(Service)
三级流程：学院初审(College) -> 校级复审(University) -> 专家评审(Expert) -> 立项(Approved)
另外含中期检查、变更/延期审批
"""
from typing import List, Tuple, Optional
from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.core.security import RoleEnum, is_super_admin, is_college_admin
from app.core.exceptions import (
    PermissionDeniedException, ResourceNotFoundException, ParamValidateException,
)
from app.core.deps import PaginationParams, DataScope
from app.crud.project import ProjectCRUD
from app.crud.user import UserCRUD, CollegeCRUD
from app.crud.review import ReviewCRUD, MidtermCRUD, ChangeCRUD
from app.models import (
    ProjProject, SysUser, ProjReview,
)
from app.schemas.review import (
    ReviewCreateRequest, ExpertReviewCreateRequest, ExpertAssignRequest,
    ReviewRecordItem, ProjectReviewFlowResponse, ExpertProjectItem,
    MidtermCheckCreate, MidtermCheckResponse, MidtermReviewRequest,
    ChangeRequestCreate, ChangeRequestResponse,
    REVIEW_STAGE_TEACHER, REVIEW_STAGE_COLLEGE, REVIEW_STAGE_UNIVERSITY, REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL,
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
        # 阶段0指导教师确认通过 -> 状态1待学院初审
        if stage == REVIEW_STAGE_TEACHER:
            return 1  # 指导教师确认通过后 -> 待学院初审
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
        if stage == REVIEW_STAGE_TEACHER:
            # 指导教师确认：仅项目的指导教师本人
            if is_super_admin(operator):
                return
            if operator.id != project.teacher_id:
                raise PermissionDeniedException(message="仅该项目的指导教师可进行确认")
            return
        if stage == REVIEW_STAGE_COLLEGE:
            # 学院初审：真超级管理员 / 本院学院管理员 / 本院教师
            if is_super_admin(operator):
                return
            # 教师与学院管理员都必须绑定且匹配项目所属学院；
            # 未绑定学院(college_id 为空)的教师不得跨院审核
            if operator.role in (RoleEnum.TEACHER, RoleEnum.ADMIN):
                if not operator.college_id or operator.college_id != project.college_id:
                    raise PermissionDeniedException(message="仅本院教师/学院管理员可执行学院初审")
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
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        ReviewService._ensure_can_review(project, req.review_stage, operator)

        # 同一阶段同一人只允许一次（排除占位记录）
        if ReviewCRUD.exist_real_review(db, project.id, req.review_stage, operator.id):
            raise ParamValidateException(message="您已在该阶段审核过此项目，请勿重复提交")

        # 如果存在占位记录，先删除再写正式记录
        from app.models import ProjReview
        placeholder = db.query(ProjReview).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage == req.review_stage,
            ProjReview.reviewer_id == operator.id,
            ProjReview.review_result == 99,
            ProjReview.is_deleted == 0,
        ).first()
        if placeholder:
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
        if req.review_result == REVIEW_RESULT_PASS:
            project.status = ReviewService._next_status_after_pass(project.status, req.review_stage)
            if project.status == 6:
                project.approval_time = datetime.now()
            # 说明：学院初审通过(2)、校级复审通过(4)为瞬时中间态，不落库；
            # 目标持久态已由 _next_status_after_pass 直接给出（3 / 5）
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
        # 打分动作：必须是专家本人，或真超级管理员（演示用代操作）；学院管理员不得代打
        if operator.role != RoleEnum.EXPERT and not is_super_admin(operator):
            raise PermissionDeniedException(message="仅专家可执行专家评审")
        project = ProjectCRUD.get_by_id(db, req.project_id)
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
                # 多数通过（含平票）则立项
                if pass_count * 2 >= total:
                    project.status = 6
                    project.approval_time = datetime.now()
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

        # 校验每个ID都是专家角色
        for eid in req.expert_ids:
            u = UserCRUD.get_by_id(db, eid)
            if not u or u.role not in (RoleEnum.EXPERT, RoleEnum.ADMIN):
                raise ParamValidateException(message=f"用户ID={eid} 不是评审专家")

        # 获取该项目该阶段已有的占位记录（未评审的专家）
        existing = db.query(ProjReview).filter(
            ProjReview.project_id == project.id,
            ProjReview.review_stage == req.review_stage,
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
                    "review_stage": req.review_stage,
                    "reviewer_id": u.id,
                    "reviewer_name": u.real_name,
                    "review_result": 99,  # 99 占位=未评审（展示层过滤）
                    "review_comment": None,
                    "review_time": datetime.now(),
                })
        # 说明：校级复审通过(4)为瞬时态、不落库，分配专家时项目应已处于 5(待专家评审)；
        # 若项目尚未进入该阶段（如仍为 3 待校级复审）则仅登记分配，不改变主状态。
        db.commit()
        return {"assigned_count": len(new_ids), "project_id": project.id}

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
            # 教师：待指导教师确认(status=12) 且 自己是指导教师
            q = q.filter(ProjProject.status == 12, ProjProject.teacher_id == operator.id)
        elif operator.role == RoleEnum.ADMIN and operator.college_id:
            # 学院管理员：待学院初审(status=1) 且 本院项目
            q = q.filter(ProjProject.status == 1, ProjProject.college_id == operator.college_id)
        elif operator.role == RoleEnum.ADMIN and not operator.college_id:
            # 超级管理员：待校级复审(status=3)
            q = q.filter(ProjProject.status == 3)
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

    # ---------- 专家待评项目列表 ----------
    @staticmethod
    def expert_pending_projects(db: Session, expert_id: int, pager: PaginationParams,
                                keyword: Optional[str] = None):
        items, total = ReviewCRUD.expert_pending_projects(
            db, expert_id, pager.offset, pager.limit, keyword
        )

        # [P1-4] 消除N+1：原代码每个项目做 3 次DB查询（专家分数/学院/负责人）
        # 一次性批量查出所有需要的数据，然后按 ID 建字典
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
        project = ProjectCRUD.get_by_id(db, req.project_id)
        if not project:
            raise ResourceNotFoundException(message="项目不存在")
        if operator.role == RoleEnum.STUDENT and project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可提交中期检查")
        if project.status not in (6, 7, 8):
            raise ParamValidateException(message="仅已立项/中期/待结题阶段可提交中期检查")

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
        obj = ChangeCRUD.get_by_id(db, change_id)
        if not obj:
            raise ResourceNotFoundException(message="申请不存在")
        # 归属校验：超管全校；学院管理员仅本院项目；教师仅本人指导的项目
        project = ProjectCRUD.get_by_id(db, obj.project_id)
        if not project:
            raise ResourceNotFoundException(message="关联项目不存在")
        if is_super_admin(operator):
            pass
        elif is_college_admin(operator):
            if not operator.college_id or project.college_id != operator.college_id:
                raise PermissionDeniedException(message="学院管理员仅可审批本院项目的变更申请")
        elif operator.role == RoleEnum.TEACHER:
            if project.teacher_id != operator.id:
                raise PermissionDeniedException(message="教师仅可审批本人指导项目的变更申请")
        else:
            raise PermissionDeniedException(message="仅教师/管理员可审批变更")
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
