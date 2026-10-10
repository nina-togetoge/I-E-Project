"""
经费报销 Service 层
"""
from typing import Optional, Tuple
from decimal import Decimal
from datetime import datetime

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models import ProjExpense, ProjProject, SysAttachment
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
from app.core.exceptions import BizException, PermissionDeniedException
from app.core.security import is_super_admin

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
        college_ids: Optional[list] = None,
    ) -> Tuple[list, int]:
        q = db.query(ProjExpense).filter(ProjExpense.is_deleted == 0)
        if applicant_id:
            q = q.filter(ProjExpense.applicant_id == applicant_id)
        if status is not None:
            q = q.filter(ProjExpense.status == status)
        # [权限] 按学院范围过滤：join Project 取 college_id
        if college_ids is not None:
            if len(college_ids) == 0:
                # 空列表表示无权限（按业务约定），直接返回空
                return [], 0
            q = q.join(ProjProject, ProjExpense.project_id == ProjProject.id).filter(
                ProjProject.college_id.in_(college_ids)
            )
        if keyword:
            kw = f"%{keyword}%"
            # 如果还没 Join Project（上面 college_ids 已 join），这里要补 join
            if college_ids is None:
                q = q.join(ProjProject, ProjExpense.project_id == ProjProject.id)
            q = q.filter(
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
        # 单条场景：保留旧接口但尽量复用批量逻辑
        results = ExpenseService.to_list_items(db, [exp])
        return results[0]

    @staticmethod
    def to_list_items(db: Session, exps: list) -> list:
        """
        [P1-4] 批量把 Expense ORM 对象 → ExpenseListItem
        一次性通过 IN 查询取出所有关联项目，避免 O(N) 次单查（原 N+1 问题）
        """
        if not exps:
            return []
        project_ids = list({e.project_id for e in exps if e.project_id})
        project_by_id: dict = {}
        if project_ids:
            rows = db.query(ProjProject.id, ProjProject.project_name).filter(
                ProjProject.id.in_(project_ids),
                ProjProject.is_deleted == 0,
            ).all()
            project_by_id = {pid: pname for pid, pname in rows}

        out: list = []
        # 批量加载报销附件
        exp_ids = [e.id for e in exps]
        atts_by_exp: dict = {}
        if exp_ids:
            atts = db.query(SysAttachment).filter(
                SysAttachment.biz_type == "expense",
                SysAttachment.biz_id.in_(exp_ids),
                SysAttachment.is_deleted == 0,
            ).order_by(SysAttachment.created_at.asc()).all()
            for a in atts:
                atts_by_exp.setdefault(a.biz_id, []).append({
                    "id": a.id, "file_name": a.file_name, "file_size": a.file_size,
                    "file_type": a.file_type, "uploader_name": a.uploader_name,
                    "download_url": f"/api/files/download/{a.id}",
                    "preview_url": f"/api/files/preview/{a.id}",
                })
        for exp in exps:
            item = ExpenseListItem.model_validate(exp)
            proj_name = project_by_id.get(exp.project_id)
            item.project_name = proj_name
            item.status_text = EXPENSE_STATUS_MAP.get(exp.status, "未知")
            item.attachments = atts_by_exp.get(exp.id, [])
            out.append(item)
        return out

    @staticmethod
    def get_summary(
        db: Session,
        applicant_id: Optional[int] = None,
        college_ids: Optional[list] = None,
    ) -> ExpenseSummary:
        q = db.query(ProjExpense).filter(ProjExpense.is_deleted == 0)
        if applicant_id:
            q = q.filter(ProjExpense.applicant_id == applicant_id)
        if college_ids is not None:
            if len(college_ids) == 0:
                # 无权限范围 → 空汇总
                return ExpenseSummary(
                    total_count=0,
                    total_amount=Decimal("0"),
                    approved_amount=Decimal("0"),
                    pending_count=0,
                )
            q = q.join(ProjProject, ProjExpense.project_id == ProjProject.id).filter(
                ProjProject.college_id.in_(college_ids)
            )
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
    def create(db: Session, data: ExpenseCreate, operator) -> ProjExpense:
        applicant_id = operator.id
        applicant_name = operator.real_name or operator.username
        project = db.query(ProjProject).filter(
            ProjProject.id == data.project_id, ProjProject.is_deleted == 0
        ).first()
        if not project:
            raise BizException("项目不存在")
        # [权限] 仅项目负责人（超级管理员可代操作）可提交该项目的报销申请
        if not is_super_admin(operator) and project.leader_id != operator.id:
            raise PermissionDeniedException(message="仅项目负责人可提交该项目的报销申请")
        # [预算] 报销金额不得超过项目剩余预算；
        # 已提交/审批中的费用视为已占用，已驳回的释放额度
        budget = Decimal(project.budget_amount or 0)
        occupied = db.query(
            func.coalesce(func.sum(ProjExpense.expense_amount), 0)
        ).filter(
            ProjExpense.project_id == project.id,
            ProjExpense.is_deleted == 0,
            ProjExpense.status != EXPENSE_STATUS_REJECTED,
        ).scalar() or Decimal("0")
        amount = Decimal(data.expense_amount or 0)
        remaining = budget - Decimal(occupied)
        if amount > remaining:
            raise BizException(f"报销金额超出剩余预算（剩余 {remaining} 元）")
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
        # 关联上传的临时附件（biz_id=0 → 当前报销单 id）
        if data.attachment_ids:
            db.query(SysAttachment).filter(
                SysAttachment.id.in_(data.attachment_ids),
                SysAttachment.biz_type == "expense",
                SysAttachment.biz_id == 0,
                SysAttachment.is_deleted == 0,
            ).update({SysAttachment.biz_id: exp.id}, synchronize_session=False)
            db.commit()
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
