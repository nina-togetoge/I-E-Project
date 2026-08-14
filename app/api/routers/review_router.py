"""
项目审核模块 API 路由层
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, OperationContext
from app.core.security import (
    RequireRole, RoleEnum, require_login, require_admin,
)
from app.core.response import ResponseModel, success, PageResult
from app.database.session import get_db
from app.models import SysUser
from app.schemas.review import (
    ReviewCreateRequest, ExpertReviewCreateRequest, ExpertAssignRequest,
    ReviewRecordItem, ProjectReviewFlowResponse, ExpertProjectItem,
    MidtermCheckCreate, MidtermCheckResponse, MidtermReviewRequest,
    ChangeRequestCreate, ChangeRequestResponse,
)
from app.services.review_service import ReviewService, MidtermService, ChangeService


router_review = APIRouter(prefix="/reviews", tags=["项目审核流程"])
router_midterm = APIRouter(prefix="/midterm", tags=["中期检查"])
router_change = APIRouter(prefix="/changes", tags=["变更/延期申请"])


# ====================================================================
# 项目审核流程接口
# ====================================================================

@router_review.post("", response_model=ResponseModel[ReviewRecordItem],
                    summary="提交审核结果(学院初审/校级复审/结题验收通用)")
def api_do_review(
    req: ReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(
        RoleEnum.TEACHER, RoleEnum.EXPERT, RoleEnum.ADMIN
    )),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"审核项目#{req.project_id}(阶段{req.review_stage})")
        data = ReviewService.do_review(db, req, current_user)
    return success(data=data, message="审核完成")


@router_review.post("/expert", response_model=ResponseModel[ReviewRecordItem], summary="专家提交评审(含评分)")
def api_expert_review(
    req: ExpertReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.EXPERT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"专家评审项目#{req.project_id}，评分{req.score}")
        data = ReviewService.do_expert_review(db, req, current_user)
    return success(data=data, message="评审提交成功")


@router_review.post("/assign-experts", response_model=ResponseModel, summary="分配专家到项目")
def api_assign_experts(
    req: ExpertAssignRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"为项目#{req.project_id}分配{len(req.expert_ids)}位专家")
        data = ReviewService.assign_experts(db, req, current_user)
    return success(data=data, message="专家分配完成")


@router_review.get("/flow/{project_id}", response_model=ResponseModel[ProjectReviewFlowResponse],
                   summary="查询项目完整审核流程记录")
def api_review_flow(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    return success(data=ReviewService.get_review_flow(db, project_id, current_user))


@router_review.get("/expert-tasks", response_model=ResponseModel[PageResult[ExpertProjectItem]],
                   summary="专家查询待评审项目列表")
def api_expert_tasks(
    keyword: Optional[str] = None,
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.EXPERT, RoleEnum.ADMIN)),
):
    items, total = ReviewService.expert_pending_projects(db, current_user.id, pager, keyword)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


# ====================================================================
# 中期检查接口
# ====================================================================

@router_midterm.get("/by-project/{project_id}", response_model=ResponseModel[Optional[MidtermCheckResponse]],
                    summary="查询项目中期检查")
def api_midterm_get(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    return success(data=MidtermService.get_by_project(db, project_id, current_user))


@router_midterm.post("/draft", response_model=ResponseModel[MidtermCheckResponse], summary="保存中期检查草稿")
def api_midterm_save(
    req: MidtermCheckCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"保存项目#{req.project_id}中期检查草稿")
        data = MidtermService.submit(db, req, current_user, is_draft=True)
    return success(data=data, message="草稿保存成功")


@router_midterm.post("/submit", response_model=ResponseModel[MidtermCheckResponse], summary="提交中期检查")
def api_midterm_submit(
    req: MidtermCheckCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"提交项目#{req.project_id}中期检查")
        data = MidtermService.submit(db, req, current_user, is_draft=False)
    return success(data=data, message="中期检查已提交审核")


@router_midterm.post("/review", response_model=ResponseModel[MidtermCheckResponse], summary="审核中期检查")
def api_midterm_review(
    req: MidtermReviewRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.TEACHER, RoleEnum.ADMIN, RoleEnum.EXPERT)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"审核中期检查#{req.check_id}，结果={req.result}")
        data = MidtermService.review(db, req, current_user)
    return success(data=data, message="中期审核完成")


# ====================================================================
# 变更/延期申请接口
# ====================================================================

@router_change.post("", response_model=ResponseModel[ChangeRequestResponse], summary="提交变更/延期申请")
def api_change_create(
    req: ChangeRequestCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"提交项目#{req.project_id}变更/延期申请(类型{req.change_type})")
        data = ChangeService.create(db, req, current_user)
    return success(data=data, message="申请提交成功")


@router_change.get("", response_model=ResponseModel[PageResult[ChangeRequestResponse]],
                   summary="变更/延期申请列表")
def api_change_list(
    project_id: Optional[int] = None,
    change_type: Optional[int] = None,
    status: Optional[int] = None,
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    items, total = ChangeService.paginate(db, pager, project_id, change_type, status, current_user)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


@router_change.post("/{change_id}/approve", response_model=ResponseModel[ChangeRequestResponse],
                    summary="审批变更申请(通过)")
def api_change_approve(
    change_id: int,
    comment: str = "",
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.TEACHER, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"审批变更申请#{change_id}通过")
        data = ChangeService.approve(db, change_id, approve=True, comment=comment, operator=current_user)
    return success(data=data, message="已通过")


@router_change.post("/{change_id}/reject", response_model=ResponseModel[ChangeRequestResponse],
                    summary="审批变更申请(驳回)")
def api_change_reject(
    change_id: int,
    comment: str = "",
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.TEACHER, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"驳回变更申请#{change_id}")
        data = ChangeService.approve(db, change_id, approve=False, comment=comment, operator=current_user)
    return success(data=data, message="已驳回")
