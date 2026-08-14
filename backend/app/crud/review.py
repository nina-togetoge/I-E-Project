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
        """判断某阶段某评审人是否已评审过"""
        return db.query(ProjReview.id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == stage,
            ProjReview.reviewer_id == reviewer_id,
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
    def expert_pending_projects(db: Session, expert_id: int, offset: int, limit: int,
                                keyword: Optional[str] = None) -> Tuple[List[ProjProject], int]:
        """
        查询专家待评审项目列表：
        规则：状态=待专家评审(5) 且 proj_review 中 reviewer_id=expert_id 且还未给出评分
        或状态>=5且专家已评审过（已评/未评）
        """
        # 子查询：专家被分配的项目ID集合
        assigned_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == 3,  # 专家评审阶段
            ProjReview.is_deleted == 0,
        ).distinct()
        # 如果没有分配记录，也看状态5的（可按学校实际）
        q = db.query(ProjProject).filter(
            ProjProject.is_deleted == 0,
            ProjProject.id.in_(assigned_q)
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
        total = q.with_entities(func.count(ProjChangeRequest.id)).scalar() or 0
        items = q.order_by(ProjChangeRequest.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def get_by_id(db: Session, pk: int) -> Optional[ProjChangeRequest]:
        return db.query(ProjChangeRequest).filter(
            ProjChangeRequest.id == pk, ProjChangeRequest.is_deleted == 0
        ).first()
