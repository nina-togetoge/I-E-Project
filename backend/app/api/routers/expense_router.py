"""
经费报销模块 API 路由
"""
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams
from app.core.security import RequireRole, RoleEnum, require_login
from app.core.response import ResponseModel, success, PageResult
from app.core.exceptions import BizException
from app.database.session import get_db
from app.models import SysUser
from app.schemas.project import (
    ExpenseCreate, ExpenseListItem, ExpenseReviewRequest, ExpenseSummary,
)
from app.services.expense_service import ExpenseService

router_expense = APIRouter(prefix="/expenses", tags=["经费报销"])


@router_expense.post("/list", response_model=ResponseModel, summary="报销列表(分页)")
def api_expense_list(
    data: dict = {},
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    """POST方式列表查询，支持筛选"""
    applicant_id = data.get("applicant_id")
    status = data.get("status")
    keyword = data.get("keyword")

    # 管理员/教师可看全部，学生只看自己的
    if current_user.role not in (RoleEnum.ADMIN, RoleEnum.TEACHER):
        applicant_id = current_user.id

    items, total = ExpenseService.paginate(
        db, pager.offset, pager.limit,
        applicant_id=applicant_id,
        status=status,
        keyword=keyword,
    )
    item_list = [ExpenseService.to_list_item(db, i) for i in items]
    summary = ExpenseService.get_summary(db, applicant_id)
    return success(data={
        "items": item_list,
        "total": total,
        "page": pager.page,
        "page_size": pager.page_size,
        "summary": summary.model_dump(),
    })


@router_expense.post("", response_model=ResponseModel[ExpenseListItem], summary="提交报销申请")
def api_expense_create(
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    exp = ExpenseService.create(db, data, current_user.id, current_user.real_name or current_user.username)
    item = ExpenseService.to_list_item(db, exp)
    return success(data=item, message="报销申请已提交")


@router_expense.patch("/{expense_id}/review", response_model=ResponseModel[ExpenseListItem], summary="审批报销")
def api_expense_review(
    expense_id: int,
    req: ExpenseReviewRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.ADMIN, RoleEnum.TEACHER)),
):
    exp = ExpenseService.review(db, expense_id, req.approved, req.opinion)
    item = ExpenseService.to_list_item(db, exp)
    return success(data=item, message="审批完成")
