"""
项目审核模块 数据访问层(CRUD)
"""
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ProjReview, ProjProject, SysUser, ProjMidtermCheck, ProjChangeRequest,
)
from app.schemas.review import REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL

REVIEW_RESULT_PENDING = 99  # 仅分配、尚未出结果的占位记录


class ReviewCRUD:
    """审核记录CRUD"""

    @staticmethod
    def create(db: Session, data: Dict[str, Any]) -> ProjReview:
        obj = ProjReview(**data)
        db.add(obj)
        db.flush()
        return obj

    @staticmethod
    def list_by_project(db: Session, project_id: int) -> List[ProjReview]:
        return db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.is_deleted == 0,
        ).order_by(ProjReview.review_stage.asc(), ProjReview.review_time.asc()).all()

    @staticmethod
    def exist_by_project_stage_reviewer(db: Session, project_id: int, stage: int, reviewer_id: int) -> bool:
        """判断某阶段某评审人是否已有审核记录（含占位记录）"""
        return db.query(ProjReview.id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == stage,
            ProjReview.reviewer_id == reviewer_id,
            ProjReview.is_deleted == 0,
        ).first() is not None

    @staticmethod
    def exist_real_review(db: Session, project_id: int, stage: int, reviewer_id: int) -> bool:
        """判断某阶段某评审人是否已正式评审过（排除占位记录 review_result=99）"""
        return db.query(ProjReview.id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == stage,
            ProjReview.reviewer_id == reviewer_id,
            ProjReview.review_result != 99,
            ProjReview.is_deleted == 0,
        ).first() is not None

    @staticmethod
    def paginate(
        db: Session, offset: int, limit: int,
        stage: Optional[int] = None, status: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> Tuple[List[ProjReview], int]:
        q = db.query(ProjReview).filter(ProjReview.is_deleted == 0)
        if stage:
            q = q.filter(ProjReview.review_stage == stage)
        if status is not None:
            q = q.filter(ProjReview.review_result == status)
        if keyword:
            kw = f"%{keyword}%"
            q = q.join(ProjProject, ProjReview.project_id == ProjProject.id).filter(
                or_(ProjProject.project_name.like(kw), ProjProject.project_no.like(kw))
            )
        total = q.with_entities(func.count(ProjReview.id)).scalar() or 0
        items = q.order_by(ProjReview.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def _expert_stage_subqueries(db: Session, expert_id: int):
        """专家相关的项目ID子查询，供"待评审"与"已评审"两个列表共用，
        以保证两者口径一致，避免同一项目同时出现在两个列表。

        返回 (assigned, expert_scored, final_scored)：
          - assigned：该专家被分配的项目（stage=3 存在记录）
          - expert_scored：该专家本人已出专家评审结果（排除 result=99 占位）
          - final_scored：该专家本人已出结题验收结果（排除 result=99 占位）
        """
        assigned_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.is_deleted == 0,
        ).distinct()
        expert_scored_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.review_result != REVIEW_RESULT_PENDING,
            ProjReview.is_deleted == 0,
        ).distinct()
        final_scored_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.review_result != REVIEW_RESULT_PENDING,
            ProjReview.is_deleted == 0,
        ).distinct()
        return assigned_q, expert_scored_q, final_scored_q

    @staticmethod
    def _expert_still_pending_clause(expert_scored_q, final_scored_q):
        """该专家仍待操作的项目条件（待专家评审未打分 / 待结题未验收），
        待办列表取它、已评审列表取它的取反，两者互斥。"""
        return or_(
            # 待专家评审(5)：仅当该专家本人尚未打分时才算待办
            and_(ProjProject.status == 5, ~ProjProject.id.in_(expert_scored_q)),
            # 待结题(8)：仅当该专家本人尚未提交结题验收时才算待办
            and_(ProjProject.status == 8, ~ProjProject.id.in_(final_scored_q)),
        )

    @staticmethod
    def expert_pending_projects(db: Session, expert_id: int, offset: int, limit: int,
                                keyword: Optional[str] = None) -> Tuple[List[ProjProject], int]:
        """
        查询专家"待办"项目列表：
        规则：该专家已被分配(proj_review.stage=3, reviewer_id=expert_id)，
              且项目当前仍处于需要该专家操作的阶段：
                - 待专家评审(5)：需打分评审
                - 待结题(8)：需结题验收
        说明：已立项(6)/中期(7)/已结题(9)/驳回(10)等已决项目不再进入该列表，
              否则专家端会出现"有行但无操作按钮"的空按钮行。
        """
        assigned_q, expert_scored_q, final_scored_q = ReviewCRUD._expert_stage_subqueries(db, expert_id)
        q = db.query(ProjProject).filter(
            ProjProject.is_deleted == 0,
            ProjProject.id.in_(assigned_q),
            ReviewCRUD._expert_still_pending_clause(expert_scored_q, final_scored_q),
        )
        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(or_(
                ProjProject.project_name.like(kw),
                ProjProject.project_no.like(kw),
            ))
        total = q.with_entities(func.count(ProjProject.id)).scalar() or 0
        items = q.order_by(ProjProject.submit_time.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def expert_reviewed_projects(db: Session, expert_id: int, offset: int, limit: int,
                                 keyword: Optional[str] = None) -> Tuple[List[ProjProject], int]:
        """
        查询专家"已评审"历史项目列表（与待办列表互斥，供回看）：
        规则：该专家本人已对项目出过结果记录（专家评审已打分 / 结题验收已提交），
              且项目当前不再需要该专家操作。
        说明：用 _expert_still_pending_clause 取反，确保仍待该专家打分或结题验收的
              项目只出现在"待评审"列表，不会同时出现在"已评审"里。
        不限制项目当前状态，因此已立项/已结题/被驳回的历史项目均可回看。
        """
        _, expert_scored_q, final_scored_q = ReviewCRUD._expert_stage_subqueries(db, expert_id)
        reviewed_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage.in_((REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL)),
            ProjReview.review_result != REVIEW_RESULT_PENDING,
            ProjReview.is_deleted == 0,
        ).distinct()
        q = db.query(ProjProject).filter(
            ProjProject.is_deleted == 0,
            ProjProject.id.in_(reviewed_q),
            ~ReviewCRUD._expert_still_pending_clause(expert_scored_q, final_scored_q),
        )
        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(or_(
                ProjProject.project_name.like(kw),
                ProjProject.project_no.like(kw),
            ))
        total = q.with_entities(func.count(ProjProject.id)).scalar() or 0
        items = q.order_by(ProjProject.submit_time.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def get_expert_score(db: Session, project_id: int, expert_id: int) -> Optional[ProjReview]:
        return db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == 3,
            ProjReview.is_deleted == 0,
        ).first()


class MidtermCRUD:
    """中期检查CRUD"""

    @staticmethod
    def get_by_project(db: Session, project_id: int) -> Optional[ProjMidtermCheck]:
        return db.query(ProjMidtermCheck).filter(
            ProjMidtermCheck.project_id == project_id,
            ProjMidtermCheck.is_deleted == 0,
        ).first()

    @staticmethod
    def get_by_id(db: Session, pk: int) -> Optional[ProjMidtermCheck]:
        return db.query(ProjMidtermCheck).filter(
            ProjMidtermCheck.id == pk, ProjMidtermCheck.is_deleted == 0
        ).first()

    @staticmethod
    def create_or_update(db: Session, data: Dict[str, Any]) -> ProjMidtermCheck:
        obj = MidtermCRUD.get_by_project(db, data["project_id"])
        if obj:
            for f, v in data.items():
                if v is not None and hasattr(obj, f):
                    setattr(obj, f, v)
            db.flush()
            return obj
        obj = ProjMidtermCheck(**data)
        db.add(obj)
        db.flush()
        return obj


class ChangeCRUD:
    """变更/延期申请CRUD"""

    @staticmethod
    def create(db: Session, data: Dict[str, Any]) -> ProjChangeRequest:
        obj = ProjChangeRequest(**data)
        db.add(obj)
        db.flush()
        return obj

    @staticmethod
    def paginate(
        db: Session, offset: int, limit: int,
        project_id: Optional[int] = None, change_type: Optional[int] = None,
        status: Optional[int] = None, applicant_id: Optional[int] = None,
        project_ids: Optional[List[int]] = None,
    ) -> Tuple[List[ProjChangeRequest], int]:
        q = db.query(ProjChangeRequest).filter(ProjChangeRequest.is_deleted == 0)
        if project_id:
            q = q.filter(ProjChangeRequest.project_id == project_id)
        if change_type:
            q = q.filter(ProjChangeRequest.change_type == change_type)
        if status is not None:
            q = q.filter(ProjChangeRequest.status == status)
        if applicant_id:
            q = q.filter(ProjChangeRequest.applicant_id == applicant_id)
        # 数据权限：按可见项目范围过滤（None=不限制；空列表=无可见项目）
        if project_ids is not None:
            if len(project_ids) == 0:
                return [], 0
            q = q.filter(ProjChangeRequest.project_id.in_(project_ids))
        total = q.with_entities(func.count(ProjChangeRequest.id)).scalar() or 0
        items = q.order_by(ProjChangeRequest.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def get_by_id(db: Session, pk: int) -> Optional[ProjChangeRequest]:
        return db.query(ProjChangeRequest).filter(
            ProjChangeRequest.id == pk, ProjChangeRequest.is_deleted == 0
        ).first()
