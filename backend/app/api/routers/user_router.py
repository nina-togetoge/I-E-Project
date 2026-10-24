"""
用户管理模块 API 路由层
包含认证、用户CRUD、学院管理、操作日志查询、文件上传基础接口
"""
# ====================================================================
# 用户与认证路由
# ----------------------------------------------------------------------------
# 对外接口分组：
#   /api/auth      POST /login 登录、POST /refresh 刷新令牌、GET /me 当前用户、
#                  POST /logout 登出（令牌加入 Redis 黑名单）
#   /api/users     GET "" 用户列表、GET/{id} 详情、POST "" 创建、
#                  PUT/{id} 更新、PATCH/me/profile 个人资料与改密、
#                  DELETE/{id} 软删、PATCH/batch/status 批量启停、
#                  POST/batch/import-result Excel 导入结果入库
#   /api/colleges  GET "" 学院列表（公开）、POST "" 新增、PUT/{id} 修改
#   /api/logs      GET "" 操作日志分页查询
# 前端对应：登录页、系统管理端「用户管理/学院管理/操作日志」、个人资料页。
# 依赖 Service：AuthService（登录/刷新/登出/用户信息组装）、UserService（用户 CRUD
#               与行级数据权限）、CollegeService、OperationLogService。
# 权限约束：
#   - 角色：1 学生 / 2 教师 / 3 专家 / 4 管理员；超管=role4 且 college_id 为空，
#     学院管理员=role4 且有 college_id；
#   - 用户列表由 DataScope 自动注入行级范围：超管全校、学院管理员本院、
#     教师本院、学生仅本人/团队成员、专家无列表权限；
#   - 创建用户允许管理员与教师，服务层按角色分级限制可创建的角色与学院；
#   - 删除、批量启停、操作日志查询要求管理员（服务层再区分超管/学院范围）。
# 特殊规则：
#   - 登录成功后在响应头写 X-Log-*，由审计中间件落登录日志；
#   - 登出把 access/refresh token 加入黑名单，立刻失效；
#   - 删除为软删除；新建用户默认 force_change_pwd=1，首次登录强制改密。
# ====================================================================
from typing import Any, Optional, Union

from fastapi import APIRouter, Depends, Request, Query, Response
from sqlalchemy.orm import Session
from urllib.parse import quote

from app.core.deps import PaginationParams, DataScope, OperationContext
from app.core.security import (
    get_current_user, RequireRole, RoleEnum, require_admin, require_login,
)
from app.core.response import ResponseModel, success, PageResult
from app.core.exceptions import BizException
from app.database.session import get_db
from app.models import SysUser
from app.schemas.user import (
    LoginRequest, LoginResponse, RefreshTokenRequest, LogoutRequest,
    UserCreate, UserUpdate, UserProfileUpdate, UserInfo, UserListItem, UserSafeListItem,
    UserQueryParams, UserBatchStatusRequest, UserBatchDeleteRequest,
    UserBatchCreateRequest, ImportResultResponse, CollegeCreate, CollegeUpdate, CollegeResponse,
    OperationLogQueryParams, OperationLogItem,
)
from app.services.user_service import AuthService, UserService, CollegeService, OperationLogService

# 子路由前缀：/api/auth + /api/users + /api/colleges + /api/logs
router_auth = APIRouter(prefix="/auth", tags=["认证接口"])
router_user = APIRouter(prefix="/users", tags=["用户管理"])
router_college = APIRouter(prefix="/colleges", tags=["学院管理"])
router_log = APIRouter(prefix="/logs", tags=["操作日志"])


# ====================================================================
# 认证接口
# ====================================================================

# --- 接口说明 ---
# POST /api/auth/login：账号密码登录。
# 谁可以调用：未登录用户（公开接口）。
# 入参：username 支持账号/手机号/邮箱，password 明文（服务端哈希校验）。
# 返回：LoginResponse（access_token、refresh_token、token_type、expires_in、user_info）。
# 异常：账号或密码错误、账号被禁用 → 认证异常；不存在与密码错误使用同一提示防枚举。
# 副作用：更新最后登录 IP/时间；通过响应头 X-Log-* 交给审计中间件写登录日志。
@router_auth.post("/login", response_model=ResponseModel[LoginResponse], summary="用户登录")
def api_login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """账号密码登录，返回访问令牌+刷新令牌+用户信息"""
    # 获取真实客户端IP
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or \
                (request.client.host if request.client else "")
    result = AuthService.login(db, req, client_ip)
    # 登录成功后写入操作日志所需的响应头（此时用户已通过认证）
    user_info = result.user_info
    response.headers["X-Log-User-Id"] = str(user_info.id)
    response.headers["X-Log-Username"] = user_info.username
    response.headers["X-Log-RealName"] = quote(str(user_info.real_name))
    response.headers["X-Log-Role"] = str(user_info.role)
    response.headers["X-Log-Desc"] = quote(f"用户[{user_info.username}]登录")
    return success(data=result, message="登录成功")


# --- 接口说明 ---
# POST /api/auth/refresh：刷新访问令牌（令牌轮换）。
# 谁可以调用：持有有效 RefreshToken 的用户（无需 AccessToken）。
# 入参：refresh_token。
# 返回：新的 access_token + 新的 refresh_token + 用户信息。
# 异常：类型错误 / 已进黑名单 / 用户被禁用 → 认证异常。
# 副作用：旧 RefreshToken 的 jti 写入 Redis 黑名单，剩余有效期后自动清理，
#         防止令牌泄露后被重放。
@router_auth.post("/refresh", response_model=ResponseModel[LoginResponse], summary="刷新令牌")
def api_refresh(req: RefreshTokenRequest, db: Session = Depends(get_db)):
    """使用刷新令牌换取新的访问令牌"""
    result = AuthService.refresh_token(db, req)
    return success(data=result, message="令牌刷新成功")


# --- 接口说明 ---
# GET /api/auth/me：获取当前登录用户信息。
# 谁可以调用：任意已登录用户。
# 入参：无（从 Authorization Bearer Token 解析用户）。
# 返回：UserInfo（角色名、学院名、脱敏后的个人资料）。
# 异常：令牌无效/过期 → 401。
# 副作用：只读；用于前端刷新页面时恢复登录态与菜单权限。
@router_auth.get("/me", response_model=ResponseModel[UserInfo], summary="获取当前登录用户信息")
def api_me(current_user: SysUser = require_login, db: Session = Depends(get_db)):
    """返回当前Token对应的用户信息"""
    from app.services.user_service import AuthService
    return success(data=AuthService._build_user_info(current_user))


# --- 接口说明 ---
# POST /api/auth/logout：用户登出。
# 谁可以调用：任意已登录用户。
# 入参：refresh_token（可选但建议传入，便于一并吊销）。
# 返回：通用成功响应。
# 副作用：AccessToken 与 RefreshToken 的 jti 写入 Redis 黑名单，立刻失效；
#         解析失败的令牌直接忽略，接口保持幂等；写操作审计日志。
@router_auth.post("/logout", response_model=ResponseModel, summary="[P1-8] 用户登出（吊销Access/Refresh Token）")
def api_logout(
    req: LogoutRequest,
    request: Request,
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    """登出：将当前 access_token & refresh_token 加入Redis黑名单，立刻失效"""
    # 从 Authorization: Bearer xxx 头中提取原始 access token 文本
    access_token_raw: str = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        access_token_raw = auth_header[7:].strip()
    with ctx:
        ctx.set_desc(f"用户[{current_user.username}]登出")
        AuthService.logout(current_user, access_token_raw, req.refresh_token)
    return success(message="已安全登出")


# ====================================================================
# 用户管理接口
# ====================================================================

# --- 接口说明 ---
# GET /api/users：用户分页列表（选人 / 管理端用户管理共用）。
# 谁可以调用：已登录用户，但按角色收敛范围（见 DataScope）：
#   超管全校；学院管理员本院；教师本院；学生仅可查学生/教师（跨院选人、字段脱敏）；
#   专家无权限查询用户列表。
# 入参：keyword 姓名/账号/学工号；role、college_id、status 精确筛选；分页参数。
# 返回：学生调用返回脱敏的 UserSafeListItem，其他角色返回 UserListItem。
# 异常：学生按 expert/admin 角色筛选、专家访问、未绑定学院的教师访问 → 403。
# 副作用：只读。
@router_user.get("", response_model=ResponseModel[PageResult[Union[UserListItem, UserSafeListItem]]], summary="用户列表(分页)")
def api_user_list(
    params: UserQueryParams = Depends(),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    """分页查询用户列表，自动按角色注入数据权限"""
    items, total = UserService.paginate(db, pager, params, data_scope)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


# --- 接口说明 ---
# GET /api/users/{user_id}：用户详情。
# 谁可以调用：管理员看全部；教师/专家仅同院且非管理员账号；学生仅看自己。
# 入参：user_id 目标用户主键。
# 返回：UserInfo（含角色名、学院名）。
# 异常：不存在 → 404；非管理员查看管理员账号、跨院查看、学生查看他人 → 403。
# 副作用：只读。
@router_user.get("/{user_id}", response_model=ResponseModel[UserInfo], summary="用户详情")
def api_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    data = UserService.get_detail(db, user_id, current_user)
    return success(data=data)


# --- 接口说明 ---
# POST /api/users：创建用户。
# 谁可以调用：管理员与教师（RequireRole）。
# 入参：账号、密码、姓名、角色(1~4)、学院、联系方式等。
# 返回：创建后的 UserInfo。
# 异常：无权限角色/跨院创建 → 403；账号重复 → 409；学院不存在 → 400。
# 副作用：写用户表并设置首次登录强制改密；写审计日志。
# 权限分级：超管可创建任意角色/学院；学院管理员与教师仅本院、不可创建管理员。
@router_user.post("", response_model=ResponseModel[UserInfo], summary="创建用户")
def api_user_create(
    req: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.ADMIN, RoleEnum.TEACHER)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"创建用户[{req.username} / {req.real_name}]")
        user = UserService.create(db, req, current_user)
    return success(data=user, message="创建用户成功")


# --- 接口说明 ---
# PUT /api/users/{user_id}：更新用户信息（部分字段）。
# 谁可以调用：超管任意；学院管理员仅本院非管理员用户且不可改角色/密码/学院；
#             普通用户仅能改本人非敏感字段。
# 入参：user_id 目标用户；请求体只覆盖显式传入字段。
# 返回：更新后的 UserInfo。
# 异常：越权字段（角色/状态/学院/密码）→ 403。
# 副作用：更新用户资料；写审计日志；密码修改必须走个人资料接口校验原密码。
@router_user.put("/{user_id}", response_model=ResponseModel[UserInfo], summary="更新用户信息")
def api_user_update(
    user_id: int,
    req: UserUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"更新用户#{user_id}信息")
        user = UserService.update(db, user_id, req, current_user)
    return success(data=user, message="更新成功")


# --- 接口说明 ---
# PATCH /api/users/me/profile：修改本人资料 / 修改密码。
# 谁可以调用：任意已登录用户（仅能改自己）。
# 入参：昵称/联系方式等；修改密码需提供 old_password + new_password。
# 返回：更新后的 UserInfo。
# 异常：原密码错误 → 参数异常。
# 副作用：改密后写入新哈希并把 force_change_pwd 置 0；写审计日志。
@router_user.patch("/me/profile", response_model=ResponseModel[UserInfo], summary="修改个人资料")
def api_update_profile(
    req: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc("修改个人资料/密码")
        user = UserService.update_profile(db, current_user, req)
    return success(data=user, message="资料更新成功")


# --- 接口说明 ---
# DELETE /api/users/{user_id}：删除用户（软删除）。
# 谁可以调用：管理员（require_admin），服务层按超管/学院管理员限定范围。
# 入参：user_id 目标用户主键。
# 返回：通用成功响应。
# 异常：越权删除外院/管理员账号 → 403。
# 副作用：is_deleted=1，保留历史业务关联；写审计日志。
@router_user.delete("/{user_id}", response_model=ResponseModel, summary="删除用户(软删除)")
def api_user_delete(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"删除用户#{user_id}")
        UserService.delete(db, user_id, current_user)
    return success(message="删除成功")


# --- 接口说明 ---
# PATCH /api/users/batch/status：批量启用/禁用用户。
# 谁可以调用：管理员。
# 入参：user_ids 目标集合；status 1=启用 / 0=禁用。
# 返回：{updated_count: 实际更新行数}。
# 异常：包含越权用户时服务层按范围跳过或拒绝。
# 副作用：批量更新账号状态，禁用后无法登录；写审计日志。
@router_user.patch("/batch/status", response_model=ResponseModel, summary="批量修改用户状态")
def api_batch_status(
    req: UserBatchStatusRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"批量修改{len(req.user_ids)}个用户状态为{'启用' if req.status == 1 else '禁用'}")
        rows = UserService.batch_update_status(db, req.user_ids, req.status, current_user)
    return success(data={"updated_count": rows}, message=f"成功更新{rows}条记录")


# --- 接口说明 ---
# POST /api/users/batch/import-result：批量创建用户（Excel 导入结果入库）。
# 谁可以调用：管理员。
# 入参：users 数组，由 Excel 解析后的行数据构成，逐行复用创建权限校验。
# 返回：ImportResultResponse（total/success/failed/errors 逐行错误）。
# 副作用：成功行逐条提交；失败行 rollback 后继续，最终整体 commit 兜底；写审计日志。
@router_user.post("/batch/import-result", response_model=ResponseModel[ImportResultResponse],
                  summary="批量创建用户(导入结果入库)")
def api_batch_import(
    req: UserBatchCreateRequest,  # [P1-6] 使用Pydantic schema校验 替代 list[dict]
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    """供Excel工具层导入后调用：批量创建用户并返回导入统计"""
    with ctx:
        ctx.set_desc(f"批量导入{len(req.users)}条用户数据")
        # 转成字典列表，交由服务层逐行容错创建；越权行计入失败明细
        users_data = [u.model_dump() for u in req.users]
        result = UserService.batch_create(db, users_data, current_user)
    return success(data=result)


# ====================================================================
# 学院管理接口
# ====================================================================

# --- 接口说明 ---
# GET /api/colleges：学院列表。
# 谁可以调用：公开接口，无需登录（注册页、登录后下拉选择等场景）。
# 入参：include_disabled=False 默认只返回启用学院；True 时包含已停用学院。
# 返回：CollegeResponse 数组。
# 副作用：只读；该接口另有 /api/common/colleges 缓存版本供高频调用。
@router_college.get("", response_model=ResponseModel[list[CollegeResponse]], summary="学院列表")
def api_college_list(
    include_disabled: bool = Query(default=False, description="是否包含已停用学院"),
    db: Session = Depends(get_db),
):
    """学院列表（公开接口，注册页等场景无需登录即可调用）"""
    return success(data=CollegeService.list_all(db, include_disabled=include_disabled))


# --- 接口说明 ---
# POST /api/colleges：新增学院。
# 谁可以调用：管理员（服务层限定真超管）。
# 入参：学院名称、编码、负责人等。
# 返回：新建的 CollegeResponse。
# 副作用：写学院表；写审计日志；可能影响注册页下拉选项（缓存由 common 路由负责）。
@router_college.post("", response_model=ResponseModel[CollegeResponse], summary="新增学院")
def api_college_create(
    req: CollegeCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"新增学院[{req.college_name}]")
        data = CollegeService.create(db, req, current_user)
    return success(data=data, message="新增学院成功")


# --- 接口说明 ---
# PUT /api/colleges/{college_id}：修改学院。
# 谁可以调用：管理员（服务层限定真超管）。
# 入参：college_id 学院主键；名称/编码/状态等可更新字段。
# 返回：更新后的 CollegeResponse。
# 异常：学院不存在 → 404。
# 副作用：更新学院资料（停用会影响该院用户的数据范围）；写审计日志。
@router_college.put("/{college_id}", response_model=ResponseModel[CollegeResponse], summary="修改学院")
def api_college_update(
    college_id: int,
    req: CollegeUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"修改学院#{college_id}")
        data = CollegeService.update(db, college_id, req, current_user)
    return success(data=data, message="修改成功")


# ====================================================================
# 操作日志接口
# ====================================================================

# --- 接口说明 ---
# GET /api/logs：操作日志分页查询。
# 谁可以调用：管理员（require_admin）。
# 数据权限：真超管可查全校日志；学院管理员仅能查本院用户的日志，防止跨院审计越权。
# 入参：keyword、模块、操作类型、用户、时间范围、多选模块/类型/角色/状态等。
# 返回：PageResult[OperationLogItem]（操作人、角色、模块、动作、IP、结果、时间）。
# 副作用：只读；日志由各写接口的 OperationContext 自动落库。
@router_log.get("", response_model=ResponseModel[PageResult[OperationLogItem]], summary="操作日志分页查询")
def api_log_list(
    params: OperationLogQueryParams = Depends(),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
):
    # 1. 传入 current_user，由服务层按超管/学院管理员计算可见日志范围
    items, total = OperationLogService.paginate(db, pager, params, current_user)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))
