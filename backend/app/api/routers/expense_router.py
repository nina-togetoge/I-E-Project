"""
经费报销模块 API 路由
"""
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, DataScope, OperationContext
from app.core.security import RequireRole, RoleEnum, require_login, is_super_admin
from app.core.response import ResponseModel, success, PageResult
from app.core.exceptions import BizException, PermissionDeniedException, ParamValidateException
from app.database.session import get_db
from app.models import SysUser, ProjProject, ProjExpense
from app.schemas.project import (
    ExpenseCreate, ExpenseListItem, ExpenseReviewRequest, ExpenseSummary,
    ExpenseQueryRequest,
    EXPENSE_STATUS_PENDING_ADVISOR,
    EXPENSE_STATUS_ADVISOR_APPROVED,
    EXPENSE_STATUS_PENDING_COLLEGE,
    EXPENSE_STATUS_COLLEGE_APPROVED,
    EXPENSE_STATUS_PENDING_FINANCE,
)
from app.services.expense_service import ExpenseService

router_expense = APIRouter(prefix="/expenses", tags=["经费报销"])


@router_expense.post("/list", response_model=ResponseModel, summary="报销列表(分页)")
def api_expense_list(
    data: ExpenseQueryRequest,
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    """POST方式列表查询，支持筛选"""
    applicant_id = data.applicant_id
    status = data.status
    keyword = data.keyword

    # 角色 → 数据范围（修复学院管理员越权看全校经费的Bug）
    scope = data_scope.scope
    college_ids: Optional[list] = None
    if not scope.get("all"):
        if current_user.role not in (RoleEnum.ADMIN, RoleEnum.TEACHER):
            # 学生只看自己的
            applicant_id = current_user.id
        else:
            # 学院管理员 / 教师 → 学院范围过滤
            college_ids = scope.get("college_ids")

    items, total = ExpenseService.paginate(
        db, pager.offset, pager.limit,
        applicant_id=applicant_id,
        status=status,
        keyword=keyword,
        college_ids=college_ids,
    )
    item_list = ExpenseService.to_list_items(db, items)
    summary = ExpenseService.get_summary(db, applicant_id, college_ids=college_ids)
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
    ctx: OperationContext = Depends(),
):
    with ctx:
        exp = ExpenseService.create(db, data, current_user.id, current_user.real_name or current_user.username)
        ctx.set_desc(f"提交报销申请#{exp.expense_no}，金额{exp.expense_amount}元")
        item = ExpenseService.to_list_item(db, exp)
        return success(data=item, message="报销申请已提交")


# 各级审批可处理的状态范围
REVIEWABLE_BY_ADVISOR = (EXPENSE_STATUS_PENDING_ADVISOR, EXPENSE_STATUS_ADVISOR_APPROVED)
REVIEWABLE_BY_COLLEGE = (EXPENSE_STATUS_PENDING_COLLEGE, EXPENSE_STATUS_COLLEGE_APPROVED)
REVIEWABLE_BY_FINANCE = (EXPENSE_STATUS_PENDING_FINANCE,)


@router_expense.patch("/{expense_id}/review", response_model=ResponseModel[ExpenseListItem], summary="审批报销")
def api_expense_review(
    expense_id: int,
    req: ExpenseReviewRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.ADMIN, RoleEnum.TEACHER)),
    ctx: OperationContext = Depends(),
):
    """按报销状态分级校验审批权限（修复学院管理员越权审批全校经费的Bug）"""
    with ctx:
        exp_obj = db.query(ProjExpense).filter(
            ProjExpense.id == expense_id, ProjExpense.is_deleted == 0
        ).first()
        if not exp_obj:
            raise BizException("报销记录不存在")
        project = db.query(ProjProject).filter(ProjProject.id == exp_obj.project_id).first()
        if not project:
            raise BizException("报销关联项目不存在")

        st = exp_obj.status

        if st in REVIEWABLE_BY_ADVISOR:
            if is_super_admin(current_user):
                pass
            elif st == EXPENSE_STATUS_PENDING_ADVISOR:
                # 待导师审批阶段：仅项目指导教师本人；学院管理员禁止代审（保证流程严谨）
                if current_user.id != project.teacher_id:
                    raise PermissionDeniedException(message="待导师审批阶段需由项目指导教师本人审批")
            else:
                # 导师审批通过(状态2)：本院教师/学院管理员可推进到下一阶段（待学院）
                if not (current_user.college_id
                        and current_user.college_id == project.college_id
                        and current_user.role in (RoleEnum.TEACHER, RoleEnum.ADMIN)):
                    raise PermissionDeniedException(message="仅本院教师或学院管理员可推进到学院审批阶段")

        elif st in REVIEWABLE_BY_COLLEGE:
            # 学院级审批：仅本院学院管理员 / 本院教师 / 超级管理员
            if not is_super_admin(current_user):
                if not (current_user.college_id
                        and current_user.college_id == project.college_id
                        and current_user.role in (RoleEnum.TEACHER, RoleEnum.ADMIN)):
                    raise PermissionDeniedException(message="仅系统管理员或本院人员可执行学院级审批")

        elif st in REVIEWABLE_BY_FINANCE:
            # 财务终审：仅真超级管理员，学院管理员禁止
            if not is_super_admin(current_user):
                raise PermissionDeniedException(message="仅系统管理员可执行财务终审")

        else:
            raise ParamValidateException(message="当前报销状态不可审批")

        result = ExpenseService.review(db, expense_id, req.approved, req.opinion)
        item = ExpenseService.to_list_item(db, result)
        ctx.set_desc(f"审批报销#{expense_id}，{'通过' if req.approved else '驳回'}")
        return success(data=item, message="审批完成")
