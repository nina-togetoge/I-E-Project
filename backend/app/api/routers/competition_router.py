"""
创新创业大赛 API 路由
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, OperationContext
from app.core.security import require_login, require_admin
from app.core.response import ResponseModel, success, PageResult
from app.database.session import get_db
from app.models import SysUser
from app.schemas.competition import (
    CompetitionCreate, CompetitionUpdate,
    CompetitionListItem, CompetitionDetail, AwardGenerateResult,
)
from app.services.competition_service import CompetitionService

router_competition = APIRouter(prefix="/competitions", tags=["创新创业大赛"])


# ====================================================================
# 公开接口：所有登录用户可查看
# ====================================================================

@router_competition.get("", response_model=ResponseModel[PageResult[CompetitionListItem]], summary="比赛列表(分页)")
def api_competition_list(
    keyword: Optional[str] = Query(None, description="关键词(名称/主办方)"),
    competition_type: Optional[int] = Query(None, ge=1, le=4, description="比赛类型"),
    level: Optional[int] = Query(None, ge=1, le=3, description="级别:1校级2省级3国家级"),
    status: Optional[int] = Query(None, ge=0, le=4, description="状态"),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 非管理员只看已发布的
    only_published = current_user.role != 4
    items, total = CompetitionService.paginate(
        db, pager.page, pager.page_size,
        keyword=keyword, competition_type=competition_type,
        level=level, status=status, only_published=only_published,
    )
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


@router_competition.get("/{comp_id}", response_model=ResponseModel[CompetitionDetail], summary="比赛详情")
def api_competition_detail(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    comp = CompetitionService.get_detail(
        db, comp_id, increment_view=True, only_published=current_user.role != 4
    )
    return success(data=comp)


# ====================================================================
# 管理接口：仅超级管理员
# ====================================================================

@router_competition.post("", response_model=ResponseModel[CompetitionDetail], summary="创建比赛")
def api_competition_create(
    req: CompetitionCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"创建比赛[{req.title}]")
        data = CompetitionService.create(db, req, current_user)
    return success(data=data, message="创建成功")


@router_competition.put("/{comp_id}", response_model=ResponseModel[CompetitionDetail], summary="更新比赛")
def api_competition_update(
    comp_id: int,
    req: CompetitionUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"更新比赛[ID:{comp_id}]")
        data = CompetitionService.update(db, comp_id, req, current_user)
    return success(data=data, message="更新成功")


@router_competition.delete("/{comp_id}", response_model=ResponseModel, summary="删除比赛")
def api_competition_delete(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"删除比赛[ID:{comp_id}]")
        CompetitionService.delete(db, comp_id, current_user)
    return success(message="删除成功")


@router_competition.patch("/{comp_id}/status", response_model=ResponseModel[CompetitionDetail], summary="修改比赛状态")
def api_competition_status(
    comp_id: int,
    status: int = Query(..., ge=0, le=4, description="状态:0草稿 1报名中 2进行中 3已结束 4已取消"),
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"修改比赛状态[ID:{comp_id}→{status}]")
        data = CompetitionService.update_status(db, comp_id, status, current_user)
    return success(data=data, message="状态更新成功")


@router_competition.post("/{comp_id}/generate-awards", response_model=ResponseModel[AwardGenerateResult],
                         summary="生成获奖名单(仅校级比赛,自动分配)")
def api_competition_generate_awards(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"生成比赛[ID:{comp_id}]获奖名单")
        data = CompetitionService.generate_awards(db, comp_id, current_user)
    return success(data=data, message=f"已生成获奖名单，共 {data['total_awarded']} 项")
