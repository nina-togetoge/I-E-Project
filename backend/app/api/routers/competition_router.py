"""
创新创业大赛 API 路由
"""
# ====================================================================
# 创新创业大赛路由
# ----------------------------------------------------------------------------
# 对外接口分组（前缀 /api/competitions）：
#   公开组（登录即可）：GET "" 比赛列表分页、GET /{comp_id} 比赛详情
#   管理组（管理员）：  POST "" 创建、PUT /{comp_id} 更新、DELETE /{comp_id} 删除、
#                       PATCH /{comp_id}/status 状态流转、
#                       POST /{comp_id}/generate-awards 生成校级获奖名单
# 前端对应：比赛信息页、管理端「赛事管理」；获奖名单用于成果与证书签发。
# 依赖 Service：CompetitionService。
# 权限约束：
#   - 列表/详情仅需登录；非管理员只能看已发布比赛（草稿/取消不可见）；
#   - 管理接口要求 role=4，且服务层二次校验为「真超级管理员」，
#     学院管理员不能维护全校赛事；
#   - 获奖名单生成额外要求真超级管理员。
# 特殊业务规则：
#   - 比赛状态：0 草稿 / 1 报名中 / 2 进行中 / 3 已结束 / 4 已取消；
#     项目只有比赛处于报名中/进行中时才能提交（项目提交时校验）；
#   - 比赛级别：1 校级 / 2 省级 / 3 国家级；仅校级(level=1)支持自动生成获奖名单；
#   - 自动生成会先软删上一轮自动生成的获奖成果/证书再按专家平均分重建，
#     可重复触发刷新，手工登记的获奖数据不受影响；
#   - 删除为软删除，保留历史项目与成果关联；
#   - 详情读取会增加浏览量。
# ====================================================================
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

# --- 接口说明 ---
# GET /api/competitions：比赛分页列表。
# 谁可以调用：任意已登录用户；非管理员仅能看到已发布比赛。
# 入参：keyword 匹配名称/主办方；competition_type 1~4 比赛类型；
#       level 1校级/2省级/3国家级；status 0草稿/1报名中/2进行中/3已结束/4已取消；
#       page/page_size 分页。
# 返回：PageResult[CompetitionListItem]，含状态名、级别名、时间表与报名信息。
# 副作用：只读查询。
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
    # 1. role != 4 只返回已发布比赛，防止草稿/已取消赛事被学生看到
    only_published = current_user.role != 4
    # 2. 按名称、类型、级别、状态组合筛选并分页
    items, total = CompetitionService.paginate(
        db, pager.page, pager.page_size,
        keyword=keyword, competition_type=competition_type,
        level=level, status=status, only_published=only_published,
    )
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


# --- 接口说明 ---
# GET /api/competitions/{comp_id}：比赛详情。
# 谁可以调用：任意已登录用户；非管理员不可查看未发布比赛。
# 入参：comp_id 比赛主键。
# 返回：CompetitionDetail（简介、时间表、报名要求、状态/级别名称等）。
# 异常：不存在或不可见 → 404/403。
# 副作用：浏览量 +1。
@router_competition.get("/{comp_id}", response_model=ResponseModel[CompetitionDetail], summary="比赛详情")
def api_competition_detail(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # increment_view=True 累加热度；only_published 控制非管理员的可见范围
    comp = CompetitionService.get_detail(
        db, comp_id, increment_view=True, only_published=current_user.role != 4
    )
    return success(data=comp)


# ====================================================================
# 管理接口：仅超级管理员
# ====================================================================

# --- 接口说明 ---
# POST /api/competitions：创建比赛。
# 谁可以调用：管理员路由 + 服务层真超管校验。
# 入参：名称、类型、级别、主办方、时间表、报名要求等。
# 返回：创建后的 CompetitionDetail。
# 副作用：写比赛表并记录创建人，写审计日志。
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


# --- 接口说明 ---
# PUT /api/competitions/{comp_id}：更新比赛信息（整体覆盖）。
# 谁可以调用：真超级管理员。
# 入参：comp_id 比赛主键；请求体为完整比赛表单。
# 返回：更新后的 CompetitionDetail。
# 异常：比赛不存在 → 404；非超管 → 业务异常。
# 副作用：覆盖字段并提交；写审计日志。
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


# --- 接口说明 ---
# DELETE /api/competitions/{comp_id}：删除比赛（软删除）。
# 谁可以调用：真超级管理员。
# 入参：comp_id 比赛主键。
# 返回：通用成功响应。
# 副作用：is_deleted=1，保留已关联项目与成果数据；写审计日志。
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


# --- 接口说明 ---
# PATCH /api/competitions/{comp_id}/status：修改比赛状态。
# 谁可以调用：真超级管理员。
# 入参：status 0草稿 / 1报名中 / 2进行中 / 3已结束 / 4已取消。
# 返回：更新后的 CompetitionDetail。
# 异常：状态越界由 Query 校验；枚举外取值服务层拒绝。
# 副作用：切换状态影响学生能否继续报名/提交项目；写审计日志。
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


# --- 接口说明 ---
# POST /api/competitions/{comp_id}/generate-awards：生成校级比赛获奖名单。
# 谁可以调用：真超级管理员（服务层强校验）。
# 入参：comp_id 比赛主键，必须 level=1（校级）；省级/国家级不支持自动分配。
# 返回：AwardGenerateResult（按学院分组的获奖项目、平均分、名次、奖项）。
# 异常：非超管 / 非校级比赛 → 业务异常。
# 副作用：软删上一轮自动生成的获奖成果与证书，重建成果(类型=竞赛获奖)、
#         签发团队/个人证书、推送站内通知；可重复调用刷新名次。
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
        # 1. 服务层完成排名池筛选、专家均分结算、成果与证书签发
        data = CompetitionService.generate_awards(db, comp_id, current_user)
    return success(data=data, message=f"已生成获奖名单，共 {data['total_awarded']} 项")
