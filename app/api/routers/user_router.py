"""
用户管理模块 API 路由层
包含认证、用户CRUD、学院管理、操作日志查询、文件上传基础接口
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, DataScope, OperationContext
from app.core.security import (
    get_current_user, RequireRole, RoleEnum, require_admin, require_login,
)
from app.core.response import ResponseModel, success, PageResult
from app.core.exceptions import BizException
from app.database.session import get_db
from app.models import SysUser
from app.schemas.user import (
    LoginRequest, LoginResponse, RefreshTokenRequest, UserRegister,
    UserCreate, UserUpdate, UserProfileUpdate, UserInfo, UserListItem,
    UserQueryParams, UserBatchStatusRequest, UserBatchDeleteRequest,
    ImportResultResponse, CollegeCreate, CollegeUpdate, CollegeResponse,
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

@router_auth.post("/login", response_model=ResponseModel[LoginResponse], summary="用户登录")
def api_login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """账号密码登录，返回访问令牌+刷新令牌+用户信息"""
    # 获取真实客户端IP
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or \
                (request.client.host if request.client else "")
    result = AuthService.login(db, req, client_ip)
    return success(data=result, message="登录成功")


@router_auth.post("/refresh", response_model=ResponseModel[LoginResponse], summary="刷新令牌")
def api_refresh(req: RefreshTokenRequest, db: Session = Depends(get_db)):
    """使用刷新令牌换取新的访问令牌"""
    result = AuthService.refresh_token(db, req)
    return success(data=result, message="令牌刷新成功")


@router_auth.post("/register", response_model=ResponseModel[UserInfo], summary="学生自助注册")
def api_register(req: UserRegister, db: Session = Depends(get_db)):
    """学生自助注册账号，角色固定为学生"""
    user = AuthService.register_student(db, req)
    return success(data=user, message="注册成功")


@router_auth.get("/me", response_model=ResponseModel[UserInfo], summary="获取当前登录用户信息")
def api_me(current_user: SysUser = require_login, db: Session = Depends(get_db)):
    """返回当前Token对应的用户信息"""
    from app.services.user_service import AuthService
    return success(data=AuthService._build_user_info(current_user))


# ====================================================================
# 用户管理接口
# ====================================================================

@router_user.get("", response_model=ResponseModel[PageResult[UserListItem]], summary="用户列表(分页)")
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


@router_user.get("/{user_id}", response_model=ResponseModel[UserInfo], summary="用户详情")
def api_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    data = UserService.get_detail(db, user_id, current_user)
    return success(data=data)


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


@router_user.post("/batch/import-result", response_model=ResponseModel[ImportResultResponse],
                  summary="批量创建用户(导入结果入库)")
def api_batch_import(
    users_data: list[dict],
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    """供Excel工具层导入后调用：批量创建用户并返回导入统计"""
    with ctx:
        ctx.set_desc(f"批量导入{len(users_data)}条用户数据")
        result = UserService.batch_create(db, users_data, current_user)
    return success(data=result)


# ====================================================================
# 学院管理接口
# ====================================================================

@router_college.get("", response_model=ResponseModel[list[CollegeResponse]], summary="学院列表")
def api_college_list(
    include_disabled: bool = Query(default=False, description="是否包含已停用学院"),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    return success(data=CollegeService.list_all(db, include_disabled=include_disabled))


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

@router_log.get("", response_model=ResponseModel[PageResult[OperationLogItem]], summary="操作日志分页查询")
def api_log_list(
    params: OperationLogQueryParams = Depends(),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
):
    items, total = OperationLogService.paginate(db, pager, params, current_user)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))
