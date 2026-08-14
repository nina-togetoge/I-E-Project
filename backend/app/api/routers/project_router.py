"""
项目申报模块 API 路由层
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, DataScope, OperationContext
from app.core.security import (
    RequireRole, RoleEnum, require_login, require_admin,
)
from app.core.response import ResponseModel, success, PageResult
from app.database.session import get_db
from app.models import SysUser
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectQueryParams, ProjectListItem,
    ProjectDetailResponse, ProjectSubmitResponse,
    AchievementCreate, AchievementResponse, ProjectStatisticsResponse,
    StatisticsTrendItem,
)
from app.services.project_service import ProjectService, AchievementService

router_project = APIRouter(prefix="/projects", tags=["项目申报"])
router_achievement = APIRouter(prefix="/achievements", tags=["项目成果"])
router_stats = APIRouter(prefix="/statistics", tags=["统计分析"])


# ====================================================================
# 项目申报接口
# ====================================================================

@router_project.get("", response_model=ResponseModel[PageResult[ProjectListItem]], summary="项目列表(分页)")
def api_project_list(
    params: ProjectQueryParams = Depends(),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    items, total = ProjectService.paginate(db, pager, params, data_scope)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


@router_project.get("/{project_id}", response_model=ResponseModel[ProjectDetailResponse], summary="项目详情")
def api_project_detail(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    return success(data=ProjectService.get_detail(db, project_id, current_user))


@router_project.post("", response_model=ResponseModel[ProjectDetailResponse], summary="创建项目(草稿)")
def api_project_create(
    req: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"创建项目草稿[{req.project_name}]")
        data = ProjectService.create(db, req, current_user, as_draft=True)
    return success(data=data, message="草稿保存成功")


@router_project.post("/submit-draft", response_model=ResponseModel[ProjectDetailResponse],
                     summary="创建并直接提交审核")
def api_project_create_and_submit(
    req: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"创建并提交项目[{req.project_name}]")
        data = ProjectService.create(db, req, current_user, as_draft=False)
    return success(data=data, message="创建并提交成功")


@router_project.put("/{project_id}", response_model=ResponseModel[ProjectDetailResponse], summary="修改项目")
def api_project_update(
    project_id: int,
    req: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"修改项目#{project_id}")
        data = ProjectService.update(db, project_id, req, current_user)
    return success(data=data, message="更新成功")


@router_project.post("/{project_id}/submit", response_model=ResponseModel[ProjectSubmitResponse],
                     summary="提交审核(草稿->待初审)")
def api_project_submit(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"提交项目#{project_id}进入审核流程")
        data = ProjectService.submit(db, project_id, current_user)
    return success(data=data, message="提交成功")


@router_project.post("/{project_id}/withdraw", response_model=ResponseModel, summary="撤回项目")
def api_project_withdraw(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"撤回项目#{project_id}")
        ProjectService.withdraw(db, project_id, current_user)
    return success(message="撤回成功，项目已退回草稿状态")


@router_project.delete("/{project_id}", response_model=ResponseModel, summary="删除项目(软删)")
def api_project_delete(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"删除项目#{project_id}")
        ProjectService.delete(db, project_id, current_user)
    return success(message="删除成功")


# ====================================================================
# 项目成果接口
# ====================================================================

@router_achievement.get("/by-project/{project_id}", response_model=ResponseModel[list[AchievementResponse]],
                        summary="查询项目下成果列表")
def api_achievement_list(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    return success(data=AchievementService.list_by_project(db, project_id, current_user))


@router_achievement.post("", response_model=ResponseModel[AchievementResponse], summary="登记项目成果")
def api_achievement_create(
    req: AchievementCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"登记项目#{req.project_id}成果[{req.title}]")
        data = AchievementService.create(db, req, current_user)
    return success(data=data, message="成果登记成功")


@router_achievement.delete("/{pk}", response_model=ResponseModel, summary="删除成果")
def api_achievement_delete(
    pk: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"删除成果#{pk}")
        AchievementService.delete(db, pk, current_user)
    return success(message="删除成功")


# ====================================================================
# 统计分析接口
# ====================================================================

@router_stats.get("/overview", response_model=ResponseModel[ProjectStatisticsResponse],
                  summary="项目总览统计(ECharts适配)")
def api_stats_overview(
    college_id: Optional[int] = Query(default=None, description="学院过滤"),
    project_type: Optional[int] = Query(default=None, ge=1, le=3, description="项目类别过滤"),
    start_year: Optional[int] = Query(default=None, description="立项年份起过滤"),
    end_year: Optional[int] = Query(default=None, description="立项年份止过滤"),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    return success(data=ProjectService.statistics_overview(
        db, data_scope,
        college_id=college_id, project_type=project_type,
        start_year=start_year, end_year=end_year,
    ))


@router_stats.get("/trend", response_model=ResponseModel[list[StatisticsTrendItem]],
                  summary="按月申报趋势统计")
def api_stats_trend(
    start_year: int = 2020,
    end_year: int = 2030,
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    return success(data=ProjectService.trend_by_month(db, start_year, end_year, data_scope))
