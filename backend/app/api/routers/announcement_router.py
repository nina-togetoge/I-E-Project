"""
公告 API 路由
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, OperationContext
from app.core.security import require_login, require_admin
from app.core.response import ResponseModel, success, PageResult
from app.database.session import get_db
from app.models import SysUser
from app.schemas.announcement import (
    AnnouncementCreate, AnnouncementUpdate,
    AnnouncementListItem, AnnouncementDetail,
)
from app.services.announcement_service import AnnouncementService

router_announcement = APIRouter(prefix="/announcements", tags=["系统公告"])


# ====================================================================
# 公开接口：所有登录用户可查看已发布公告
# ====================================================================

@router_announcement.get("", response_model=ResponseModel[PageResult[AnnouncementListItem]], summary="公告列表(分页)")
def api_announcement_list(
    keyword: Optional[str] = Query(None, description="关键词(标题/内容)"),
    announcement_type: Optional[int] = Query(None, ge=1, le=4, description="公告类型"),
    status: Optional[int] = Query(None, ge=0, le=2, description="状态"),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 非管理员只看已发布的
    only_published = current_user.role != 4
    items, total = AnnouncementService.paginate(
        db, pager.page, pager.page_size,
        keyword=keyword, announcement_type=announcement_type,
        status=status, only_published=only_published,
    )
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


@router_announcement.get("/{ann_id}", response_model=ResponseModel[AnnouncementDetail], summary="公告详情")
def api_announcement_detail(
    ann_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    ann = AnnouncementService.get_detail(
        db, ann_id, increment_view=True, only_published=current_user.role != 4
    )
    return success(data=ann)


# ====================================================================
# 管理接口：仅管理员
# ====================================================================

@router_announcement.post("", response_model=ResponseModel[AnnouncementDetail], summary="创建公告")
def api_announcement_create(
    req: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"创建公告[{req.title}]")
        data = AnnouncementService.create(db, req, current_user)
    return success(data=data, message="创建成功")


@router_announcement.put("/{ann_id}", response_model=ResponseModel[AnnouncementDetail], summary="更新公告")
def api_announcement_update(
    ann_id: int,
    req: AnnouncementUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"更新公告[ID:{ann_id}]")
        data = AnnouncementService.update(db, ann_id, req, current_user)
    return success(data=data, message="更新成功")


@router_announcement.delete("/{ann_id}", response_model=ResponseModel, summary="删除公告")
def api_announcement_delete(
    ann_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"删除公告[ID:{ann_id}]")
        AnnouncementService.delete(db, ann_id, current_user)
    return success(message="删除成功")


@router_announcement.patch("/{ann_id}/status", response_model=ResponseModel[AnnouncementDetail], summary="修改公告状态")
def api_announcement_status(
    ann_id: int,
    status: int = Query(..., ge=0, le=2, description="状态:0草稿 1已发布 2已下线"),
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"修改公告状态[ID:{ann_id}→{status}]")
        data = AnnouncementService.update_status(db, ann_id, status, current_user)
    return success(data=data, message="状态更新成功")
