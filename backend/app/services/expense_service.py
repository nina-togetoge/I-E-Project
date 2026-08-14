"""
经费报销 Service 层
"""
from typing import Optional, Tuple
from decimal import Decimal
from datetime import datetime

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models import ProjExpense, ProjProject
from app.schemas.project import (
    ExpenseCreate, ExpenseListItem, ExpenseSummary,
    EXPENSE_STATUS_DRAFT,
    EXPENSE_STATUS_PENDING_ADVISOR,
    EXPENSE_STATUS_ADVISOR_APPROVED,
    EXPENSE_STATUS_PENDING_COLLEGE,
    EXPENSE_STATUS_COLLEGE_APPROVED,
    EXPENSE_STATUS_PENDING_FINANCE,
    EXPENSE_STATUS_COMPLETED,
    EXPENSE_STATUS_REJECTED,
)
from app.core.exceptions import BizException

# 审批状态 → 中文显示文本
EXPENSE_STATUS_MAP = {
    EXPENSE_STATUS_DRAFT: "草稿",
    EXPENSE_STATUS_PENDING_ADVISOR: "待导师审批",
    EXPENSE_STATUS_ADVISOR_APPROVED: "导师审批通过",
    EXPENSE_STATUS_PENDING_COLLEGE: "待学院审批",
    EXPENSE_STATUS_COLLEGE_APPROVED: "学院审批通过",
    EXPENSE_STATUS_PENDING_FINANCE: "待财务审批",
    EXPENSE_STATUS_COMPLETED: "已完成",
    EXPENSE_STATUS_REJECTED: "已驳回",
}

# 可推进状态 → 推进后的下一状态
_NEXT_STATUS = {
    EXPENSE_STATUS_DRAFT: EXPENSE_STATUS_PENDING_ADVISOR,
    EXPENSE_STATUS_PENDING_ADVISOR: EXPENSE_STATUS_ADVISOR_APPROVED,
    EXPENSE_STATUS_ADVISOR_APPROVED: EXPENSE_STATUS_PENDING_COLLEGE,
    EXPENSE_STATUS_PENDING_COLLEGE: EXPENSE_STATUS_COLLEGE_APPROVED,
    EXPENSE_STATUS_COLLEGE_APPROVED: EXPENSE_STATUS_PENDING_FINANCE,
    EXPENSE_STATUS_PENDING_FINANCE: EXPENSE_STATUS_COMPLETED,
}


class ExpenseService:

    @staticmethod
    def paginate(
        db: Session,
        offset: int,
        limit: int,
        applicant_id: Optional[int] = None,
        status: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> Tuple[list, int]:
        q = db.query(ProjExpense).filter(ProjExpense.is_deleted == 0)
        if applicant_id:
            q = q.filter(ProjExpense.applicant_id == applicant_id)
        if status is not None:
            q = q.filter(ProjExpense.status == status)
        if keyword:
            kw = f"%{keyword}%"
            q = q.join(ProjProject, ProjExpense.project_id == ProjProject.id).filter(
                or_(
                    ProjExpense.expense_no.like(kw),
                    ProjExpense.expense_desc.like(kw),
                    ProjProject.project_name.like(kw),
                )
            )
        total = q.with_entities(func.count(ProjExpense.id)).scalar() or 0
        items = q.order_by(ProjExpense.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def to_list_item(db: Session, exp: ProjExpense) -> ExpenseListItem:
        project = db.query(ProjProject).filter(ProjProject.id == exp.project_id).first()
        item = ExpenseListItem.model_validate(exp)
        item.project_name = project.project_name if project else None
        item.status_text = EXPENSE_STATUS_MAP.get(exp.status, "未知")
        return item

    @staticmethod
    def get_summary(db: Session, applicant_id: Optional[int] = None) -> ExpenseSummary:
        q = db.query(ProjExpense).filter(ProjExpense.is_deleted == 0)
        if applicant_id:
            q = q.filter(ProjExpense.applicant_id == applicant_id)
        total_count = q.with_entities(func.count(ProjExpense.id)).scalar() or 0
        total_amount = q.with_entities(func.coalesce(func.sum(ProjExpense.expense_amount), Decimal("0"))).scalar() or Decimal("0")
        # 已完成(已报销)金额
        approved_amount = q.filter(ProjExpense.status == EXPENSE_STATUS_COMPLETED).with_entities(
            func.coalesce(func.sum(ProjExpense.expense_amount), Decimal("0"))
        ).scalar() or Decimal("0")
        # 待处理：草稿 + 各级待审批 + 各级审批通过(尚未完成)
        pending_count = q.filter(ProjExpense.status.in_([
            EXPENSE_STATUS_DRAFT,
            EXPENSE_STATUS_PENDING_ADVISOR,
            EXPENSE_STATUS_ADVISOR_APPROVED,
            EXPENSE_STATUS_PENDING_COLLEGE,
            EXPENSE_STATUS_COLLEGE_APPROVED,
            EXPENSE_STATUS_PENDING_FINANCE,
        ])).with_entities(
            func.count(ProjExpense.id)
        ).scalar() or 0
        return ExpenseSummary(
            total_count=total_count,
            total_amount=total_amount,
            approved_amount=approved_amount,
            pending_count=pending_count,
        )

    @staticmethod
    def create(db: Session, data: ExpenseCreate, applicant_id: int, applicant_name: str) -> ProjExpense:
        project = db.query(ProjProject).filter(
            ProjProject.id == data.project_id, ProjProject.is_deleted == 0
        ).first()
        if not project:
            raise BizException("项目不存在")
        expense_no = f"EXP{datetime.now().strftime('%Y%m%d%H%M%S')}{applicant_id % 100:02d}"
        exp = ProjExpense(
            expense_no=expense_no,
            project_id=data.project_id,
            applicant_id=applicant_id,
            applicant_name=applicant_name,
            expense_amount=data.expense_amount,
            expense_desc=data.expense_desc,
            invoice_no=data.invoice_no,
            budget_item_id=data.budget_item_id,
            status=EXPENSE_STATUS_PENDING_ADVISOR,
            submit_time=datetime.now(),
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        return exp

    @staticmethod
    def review(db: Session, expense_id: int, approved: bool, opinion: Optional[str] = None) -> ProjExpense:
        """审批报销：approved=True 推进下一阶段，False 驳回"""
        exp = db.query(ProjExpense).filter(ProjExpense.id == expense_id, ProjExpense.is_deleted == 0).first()
        if not exp:
            raise BizException("报销记录不存在")

        if exp.status in (EXPENSE_STATUS_COMPLETED, EXPENSE_STATUS_REJECTED):
            raise BizException("该报销记录已终审，不可再次审批")

        if not approved:
            # 驳回
            exp.status = EXPENSE_STATUS_REJECTED
            if opinion:
                exp.reject_reason = opinion
            exp.approval_time = datetime.now()
        else:
            # 通过 → 推进到下一阶段
            next_status = _NEXT_STATUS.get(exp.status)
            if next_status is None:
                raise BizException(f"当前状态({EXPENSE_STATUS_MAP.get(exp.status, '?')})不可推进")
            exp.status = next_status
            exp.reject_reason = None
            if next_status == EXPENSE_STATUS_COMPLETED:
                exp.approval_time = datetime.now()

        db.commit()
        db.refresh(exp)
        return exp
