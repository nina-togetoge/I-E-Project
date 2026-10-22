"""
站内通知 API 路由
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams
from app.core.response import PageResult, ResponseModel, success
from app.core.security import require_login
from app.database.session import get_db
from app.models import SysUser
from app.schemas.notification import NotificationItem, NotificationUnreadCount
from app.services.notification_service import NotificationService

router_notification = APIRouter(prefix="/notifications", tags=["站内通知"])


@router_notification.get("", response_model=ResponseModel[PageResult[NotificationItem]],
                          summary="我的通知(分页)")
def api_notification_list(
    is_read: Optional[int] = Query(default=None, ge=0, le=1, description="是否已读"),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    items, total = NotificationService.paginate(
        db, current_user.id, pager.page, pager.page_size, is_read=is_read
    )
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


@router_notification.get("/unread-count", response_model=ResponseModel[NotificationUnreadCount],
                         summary="未读通知数量")
def api_notification_unread_count(
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    count = NotificationService.unread_count(db, current_user.id)
    return success(data=NotificationUnreadCount(count=count))


@router_notification.post("/{pk}/read", response_model=ResponseModel, summary="标记通知已读")
def api_notification_read(
    pk: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    NotificationService.mark_read(db, current_user.id, pk)
    return success(message="已标记为已读")


@router_notification.post("/read-all", response_model=ResponseModel, summary="全部标记已读")
def api_notification_read_all(
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    count = NotificationService.mark_all_read(db, current_user.id)
    return success(data={"count": count}, message="已全部标记为已读")
