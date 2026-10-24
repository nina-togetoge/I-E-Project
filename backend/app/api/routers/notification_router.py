"""
站内通知 API 路由
"""
# ====================================================================
# 站内通知路由
# ----------------------------------------------------------------------------
# 对外接口分组（前缀 /api/notifications）：
#   GET  ""                 我的通知分页列表（支持按已读状态过滤）
#   GET  /unread-count      未读数统计（前端顶栏红点）
#   POST /{pk}/read         单条标记已读
#   POST /read-all          全部标记已读
# 前端对应：顶栏消息铃铛、消息中心页面。
# 依赖 Service：NotificationService（通知查询与已读状态维护）。
# 权限约束：全部要求登录；服务层强制用 current_user.id 作为接收人过滤，
#           用户只能看到并修改自己的通知，不能越权读取或标记他人消息。
# 特殊规则：
#   - 通知由项目审批、成果认定、证书签发、报销审批等业务写入，
#     写入方只 add 不 commit，与业务数据保持同一事务；
#   - 已读只是状态位更新，不物理删除；所有查询过滤 is_deleted=0；
#   - 列表按 id 倒序（最新在前），未读数用于前端角标。
# ====================================================================
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


# --- 接口说明 ---
# GET /api/notifications：当前登录用户的站内通知分页列表。
# 谁可以调用：任意已登录用户（学生/教师/专家/管理员）。
# 入参：is_read 可选，0=只看未读、1=只看已读、不传=全部；page/page_size 分页。
# 返回：PageResult[NotificationItem]，含标题、内容、级别、业务跳转链接、已读标记。
# 权限：服务层以 current_user.id 强制过滤接收人，不暴露他人通知。
# 副作用：只读查询，不修改数据。
@router_notification.get("", response_model=ResponseModel[PageResult[NotificationItem]],
                          summary="我的通知(分页)")
def api_notification_list(
    is_read: Optional[int] = Query(default=None, ge=0, le=1, description="是否已读"),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 按当前用户 + 已读条件查询，页码从 1 开始；服务层保证只查未软删的通知
    items, total = NotificationService.paginate(
        db, current_user.id, pager.page, pager.page_size, is_read=is_read
    )
    # 2. 组装分页结果，total 用于前端分页器，items 已按最新在前排序
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


# --- 接口说明 ---
# GET /api/notifications/unread-count：当前用户未读通知条数。
# 入参：无（接收人取自登录态）。
# 返回：{count: int}，前端用于顶栏铃铛红点与轮询刷新。
# 副作用：只读统计，不改动已读状态。
@router_notification.get("/unread-count", response_model=ResponseModel[NotificationUnreadCount],
                         summary="未读通知数量")
def api_notification_unread_count(
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 只统计本人未读且未软删的通知，避免把他人消息计入当前账号
    count = NotificationService.unread_count(db, current_user.id)
    return success(data=NotificationUnreadCount(count=count))


# --- 接口说明 ---
# POST /api/notifications/{pk}/read：把指定通知标记为已读。
# 谁可以调用：通知接收人本人（任意已登录用户）。
# 入参：pk = 通知主键。
# 返回：通用成功响应。
# 异常：通知不存在或不属于当前用户时由服务层抛 404/403，防止通过猜 id 标记他人通知。
# 副作用：更新 sys_notification.is_read=1 并提交事务。
@router_notification.post("/{pk}/read", response_model=ResponseModel, summary="标记通知已读")
def api_notification_read(
    pk: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 服务层校验归属并置为已读；重复标记幂等，不报错
    NotificationService.mark_read(db, current_user.id, pk)
    return success(message="已标记为已读")


# --- 接口说明 ---
# POST /api/notifications/read-all：把当前用户的全部未读通知一次性标记已读。
# 入参：无。
# 返回：{count: 本次实际更新的条数}。
# 副作用：批量更新本人通知的已读状态；不触碰他人数据。
@router_notification.post("/read-all", response_model=ResponseModel, summary="全部标记已读")
def api_notification_read_all(
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 批量更新并返回影响行数，供前端提示“已全部标记”
    count = NotificationService.mark_all_read(db, current_user.id)
    return success(data={"count": count}, message="已全部标记为已读")
