"""
公告 API 路由
"""
# ====================================================================
# 系统公告路由
# ----------------------------------------------------------------------------
# 对外接口分组（前缀 /api/announcements）：
#   公开组（登录即可）：GET "" 列表分页、GET /{ann_id} 详情
#   管理组（管理员）：  POST "" 创建、PUT /{ann_id} 更新、
#                       DELETE /{ann_id} 删除、PATCH /{ann_id}/status 上下线
# 前端对应：首页公告栏、公告列表/详情页、管理端「公告管理」。
# 依赖 Service：AnnouncementService（分页、详情、增删改、状态流转）。
# 权限约束：
#   - 列表与详情仅登录用户可访问；非管理员（role != 4）只能看到已发布(status=1)公告；
#   - 管理接口要求 role=4，且服务层进一步限定为「真超级管理员」（college_id 为空），
#     学院管理员不可维护校级公告。
# 特殊业务规则：
#   - 公告状态：0 草稿 / 1 已发布 / 2 已下线；首次发布自动记录 publish_time；
#   - 公告类型 announcement_type 取值 1~4，由字典/枚举维护；
#   - 列表查询前会惰性执行到期自动下线，并按「优先级降序 + 创建时间降序」排序；
#   - 详情读取会增加浏览量（increment_view=True）；
#   - 删除为软删除，保留历史便于追溯；所有写操作带 OperationContext 记录审计日志。
# ====================================================================
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

# --- 接口说明 ---
# GET /api/announcements：公告分页列表。
# 谁可以调用：任意已登录用户；管理员可看全部状态，其他角色只能看已发布公告。
# 入参：keyword 模糊匹配标题/正文；announcement_type 1~4 公告类型；
#       status 0 草稿 / 1 已发布 / 2 已下线（仅管理员筛选有意义）；page/page_size 分页。
# 返回：PageResult[AnnouncementListItem]，含类型名、状态名、优先级、浏览量等。
# 副作用：查询前惰性处理到期公告（自动置为已下线）。
@router_announcement.get("", response_model=ResponseModel[PageResult[AnnouncementListItem]], summary="公告列表(分页)")
def api_announcement_list(
    keyword: Optional[str] = Query(None, description="关键词(标题/内容)"),
    announcement_type: Optional[int] = Query(None, ge=1, le=4, description="公告类型"),
    status: Optional[int] = Query(None, ge=0, le=2, description="状态"),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. role != 4 视为普通用户，只允许检索已发布公告，避免草稿/下线内容泄漏
    only_published = current_user.role != 4
    # 2. 按筛选条件分页；服务层负责到期自动下线与优先级排序
    items, total = AnnouncementService.paginate(
        db, pager.page, pager.page_size,
        keyword=keyword, announcement_type=announcement_type,
        status=status, only_published=only_published,
    )
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


# --- 接口说明 ---
# GET /api/announcements/{ann_id}：公告详情。
# 谁可以调用：任意已登录用户；非管理员访问未发布公告会被服务层拒绝。
# 入参：ann_id 公告主键。
# 返回：AnnouncementDetail（正文、类型/状态名称、发布人、浏览量等）。
# 异常：公告不存在或不可见 → 404/403。
# 副作用：浏览量 +1，用于统计公告热度。
@router_announcement.get("/{ann_id}", response_model=ResponseModel[AnnouncementDetail], summary="公告详情")
def api_announcement_detail(
    ann_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. increment_view=True 由服务层原子累加浏览量；only_published 控制非管理员可见范围
    ann = AnnouncementService.get_detail(
        db, ann_id, increment_view=True, only_published=current_user.role != 4
    )
    return success(data=ann)


# ====================================================================
# 管理接口：仅管理员
# ====================================================================

# --- 接口说明 ---
# POST /api/announcements：创建公告。
# 谁可以调用：管理员（require_admin），服务层再校验必须为真超级管理员。
# 入参：标题、正文、类型(1~4)、状态(0草稿/1发布/2下线)、优先级、有效期等。
# 返回：创建后的 AnnouncementDetail。
# 异常：非超管 → 业务异常；状态非法 → 参数异常。
# 副作用：写入公告表；若创建即发布则记录发布时间；OperationContext 写审计日志。
@router_announcement.post("", response_model=ResponseModel[AnnouncementDetail], summary="创建公告")
def api_announcement_create(
    req: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    # with ctx 负责在退出时统一提交/回滚并落操作日志，set_desc 描述本次操作对象
    with ctx:
        ctx.set_desc(f"创建公告[{req.title}]")
        data = AnnouncementService.create(db, req, current_user)
    return success(data=data, message="创建成功")


# --- 接口说明 ---
# PUT /api/announcements/{ann_id}：更新公告（部分字段更新）。
# 谁可以调用：真超级管理员（路由要求 role=4，服务层二次校验）。
# 入参：ann_id 公告主键；请求体只覆盖显式传入的字段。
# 返回：更新后的 AnnouncementDetail。
# 异常：公告不存在 → 404；非超管 → 403/业务异常。
# 副作用：更新公告内容；首次改为已发布时补写发布时间；写审计日志。
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


# --- 接口说明 ---
# DELETE /api/announcements/{ann_id}：删除公告（软删除）。
# 谁可以调用：真超级管理员。
# 入参：ann_id 公告主键。
# 返回：通用成功响应。
# 副作用：is_deleted=1，保留记录供追溯；写审计日志。
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


# --- 接口说明 ---
# PATCH /api/announcements/{ann_id}/status：发布 / 下线 / 退回草稿。
# 谁可以调用：真超级管理员。
# 入参：status 0草稿 / 1已发布 / 2已下线。
# 返回：更新后的 AnnouncementDetail。
# 异常：状态越界由 Query 校验拦截；枚举外取值由服务层拒绝。
# 副作用：首次发布补写发布时间，下线不清空发布时间；写审计日志。
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
