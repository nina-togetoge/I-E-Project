"""
用户管理模块 业务逻辑层(Service)
封装用户CRUD业务规则、认证逻辑、数据权限判断，调用CRUD层完成数据库操作
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    verify_password, create_access_token, create_refresh_token,
    decode_token, extract_jti_exp, RoleEnum, ROLE_NAME_MAP, hash_password,
)
from app.core.exceptions import (
    AuthException, ParamValidateException, ResourceNotFoundException,
    DataConflictException, PermissionDeniedException,
)
from app.core.deps import PaginationParams, DataScope
from app.schemas.user import (
    LoginRequest, LoginResponse, UserCreate, UserUpdate, UserProfileUpdate,
    UserInfo, UserListItem, UserSafeListItem, UserQueryParams, CollegeCreate, CollegeUpdate,
    CollegeResponse, OperationLogQueryParams, RefreshTokenRequest,
    UserRegister, ImportResultResponse,
)
from app.crud.user import UserCRUD, CollegeCRUD, OperationLogCRUD
from app.models import SysUser, SysCollege
from app.utils.redis_cache import TokenBlacklist


class AuthService:
    """认证相关业务服务"""

    @staticmethod
    def login(db: Session, req: LoginRequest, client_ip: str) -> LoginResponse:
        """用户登录：校验账号密码 -> 生成双Token -> 更新登录信息"""
        # 1. 查找用户
        user = UserCRUD.get_by_username(db, req.username)
        if not user:
            raise AuthException(message="账号或密码错误")
        if user.status != 1:
            raise AuthException(message="账号已被禁用，请联系管理员")

        # 2. 校验密码
        if not verify_password(req.password, user.password_hash):
            raise AuthException(message="账号或密码错误")

        # 3. 更新登录信息（IP/时间）
        UserCRUD.update_login_info(db, user, client_ip)
        db.commit()
        db.refresh(user)

        # 4. 生成 Token
        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_info=AuthService._build_user_info(user),
        )

    @staticmethod
    def refresh_token(db: Session, req: RefreshTokenRequest) -> LoginResponse:
        """使用RefreshToken换取新的AccessToken"""
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise AuthException(message="刷新令牌类型错误")
        # [P1-8] Refresh Token 黑名单校验（用户登出时已吊销）
        jti = payload.get("jti")
        if TokenBlacklist.is_blacklisted("refresh", jti):
            raise AuthException(message="刷新令牌已失效，请重新登录")
        user_id = payload.get("uid")
        username = payload.get("sub")
        if not user_id or not username:
            raise AuthException(message="刷新令牌无效")
        user = UserCRUD.get_by_username(db, username)
        if not user or user.id != user_id or user.status != 1:
            raise AuthException(message="用户不存在或已失效")
        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_info=AuthService._build_user_info(user),
        )

    @staticmethod
    def logout(current_user: SysUser, access_token_raw: str, refresh_token_raw: Optional[str] = None) -> None:
        """
        [P1-8] 登出：将当前 access & refresh token 加入 Redis 黑名单
        """
        # 1. Access Token 吊销
        try:
            payload = decode_token(access_token_raw)
            jti, remaining = extract_jti_exp(payload)
            TokenBlacklist.add("access", jti, remaining)
        except Exception:
            # 前端给的access可能快过期了，decode失败忽略
            pass
        # 2. Refresh Token 吊销（若提供）
        if refresh_token_raw:
            try:
                payload = decode_token(refresh_token_raw)
                if payload.get("type") == "refresh":
                    jti, remaining = extract_jti_exp(payload)
                    TokenBlacklist.add("refresh", jti, remaining)
            except Exception:
                pass

    @staticmethod
    def register_student(db: Session, req: UserRegister) -> UserInfo:
        """学生自助注册：只允许学生角色，检查账号唯一性"""
        # 账号唯一校验
        if UserCRUD.get_by_username(db, req.username):
            raise DataConflictException(message=f"账号 {req.username} 已存在")
        # 学院存在性校验
        if req.college_id and not CollegeCRUD.get_by_id(db, req.college_id):
            raise ParamValidateException(message="所选学院不存在")

        data = req.model_dump()
        data["role"] = RoleEnum.STUDENT
        data["status"] = 1
        data["force_change_pwd"] = 1  # 自助注册后首次登录必须改密
        user = UserCRUD.create(db, data)
        db.commit()
        db.refresh(user)
        return AuthService._build_user_info(user)

    @staticmethod
    def _build_user_info(user: SysUser) -> UserInfo:
        """构建UserInfo响应，含角色名、学院名（通过关联对象）"""
        info = UserInfo.model_validate(user, from_attributes=True)
        info.role_name = ROLE_NAME_MAP.get(user.role, f"未知({user.role})")
        # 通过ORM关联对象取学院名
        if user.college:
            info.college_name = user.college.college_name
        return info

    @staticmethod
    def _build_safe_list_item(user: SysUser) -> UserSafeListItem:
        """学生端用户列表：仅返回非敏感字段（用于选人，隐藏邮箱/手机/状态等）"""
        item = UserSafeListItem.model_validate(user, from_attributes=True)
        item.role_name = ROLE_NAME_MAP.get(user.role, f"未知({user.role})")
        try:
            if user.college:
                item.college_name = user.college.college_name
        except Exception:
            pass
        return item


class UserService:
    """用户管理业务服务"""

    # ====================================================================
    # 管理员 CRUD
    # ====================================================================
    @staticmethod
    def get_detail(db: Session, user_id: int, operator: SysUser) -> UserInfo:
        """查询单个用户详情，含行级权限校验"""
        user = UserCRUD.get_by_id(db, user_id)
        if not user:
            raise ResourceNotFoundException(message="用户不存在")
        # 行级权限：管理员看全部；本院角色看本院；学生只看自己
        if operator.role != RoleEnum.ADMIN:
            if operator.role == RoleEnum.STUDENT and operator.id != user_id:
                raise PermissionDeniedException(message="无权查看其他用户信息")
            if operator.college_id and user.college_id and operator.college_id != user.college_id:
                raise PermissionDeniedException(message="无权查看其他学院用户信息")
        return AuthService._build_user_info(user)

    @staticmethod
    def paginate(db: Session, pager: PaginationParams, params: UserQueryParams,
                 data_scope: DataScope) -> Tuple[List, int]:
        """分页查询用户列表，自动按角色注入数据权限 & 学生端脱敏返回"""
        is_student_caller = (data_scope.role == RoleEnum.STUDENT)

        # ----------------------------------------------------------------
        # [安全补丁 P0-4] 学生角色只能查"选人"场景下的白名单角色：
        #   role=1(STUDENT) —— 选团队成员（同学院）
        #   role=2(TEACHER) —— 选指导教师（同学院）
        # 禁止学生查 role=3(EXPERT)、role=4(ADMIN)，更不允许 role=None 查全部！
        # ----------------------------------------------------------------
        if is_student_caller:
            if params.role not in (RoleEnum.STUDENT, RoleEnum.TEACHER):
                raise PermissionDeniedException(
                    message="学生端用户查询仅支持按角色筛选：学生(1)或指导教师(2)"
                )
            # 学生端强制只能看本院数据 + 脱敏返回
            effective_scope = DataScope.__new__(DataScope)
            effective_scope.user = data_scope.user
            effective_scope.db = data_scope.db
            effective_scope.role = data_scope.role
            effective_scope.college_id = data_scope.college_id
            effective_scope.user_id = data_scope.user_id
            effective_scope.scope = {
                "all": False,
                "college_ids": [data_scope.college_id] if data_scope.college_id else None,
                "owner_user_ids": None,
                "is_student_whitelist": True,
                "role_whitelist": [params.role],
            }
        else:
            effective_scope = data_scope

        users, total = UserCRUD.paginate(
            db,
            offset=pager.offset,
            limit=pager.limit,
            keyword=params.keyword,
            role=params.role,
            college_id=params.college_id,
            status=params.status,
            data_scope=effective_scope,
            order_by=pager.order_by or "created_at",
            order_dir=pager.order_dir,
        )
        items: List = []
        for u in users:
            info = AuthService._build_user_info(u)
            if is_student_caller:
                # 学生端返回脱敏版（无邮箱/手机/状态等PII）
                items.append(AuthService._build_safe_list_item(u))
            else:
                item = UserListItem.model_validate(u, from_attributes=True)
                item.role_name = info.role_name
                item.college_name = info.college_name
                items.append(item)
        return items, total

    @staticmethod
    def create(db: Session, req: UserCreate, operator: SysUser) -> UserInfo:
        """创建用户：管理员/学院管理员"""
        # 权限：普通教师/学生不能创建用户；非管理员只能创建本院且角色不能是管理员
        if operator.role not in (RoleEnum.ADMIN,):
            if operator.role != RoleEnum.TEACHER:
                raise PermissionDeniedException(message="无权限创建用户")
        if operator.role != RoleEnum.ADMIN:
            if req.role == RoleEnum.ADMIN:
                raise PermissionDeniedException(message="无权限创建管理员账号")
            if req.college_id and operator.college_id and req.college_id != operator.college_id:
                raise PermissionDeniedException(message="只能创建本院用户")
            if not req.college_id:
                req.college_id = operator.college_id

        if UserCRUD.get_by_username(db, req.username):
            raise DataConflictException(message=f"账号 {req.username} 已存在")
        if req.college_id and not CollegeCRUD.get_by_id(db, req.college_id):
            raise ParamValidateException(message="所属学院不存在")

        data = req.model_dump()
        data.setdefault("force_change_pwd", 1)  # 新建用户首次登录强制改密
        user = UserCRUD.create(db, data)
        db.commit()
        db.refresh(user)
        return AuthService._build_user_info(user)

    @staticmethod
    def batch_create(db: Session, users: List[Dict[str, Any]], operator: SysUser) -> ImportResultResponse:
        """批量创建用户（Excel导入调用）"""
        total = len(users)
        success = 0
        errors: List[str] = []
        for idx, u in enumerate(users, 1):
            try:
                # 基本字段校验
                for f in ("username", "password", "real_name", "role"):
                    if f not in u or not u[f]:
                        raise ValueError(f"缺少必填字段: {f}")
                req = UserCreate.model_validate(u)
                UserService.create(db, req, operator)
                success += 1
            except Exception as e:
                errors.append(f"第{idx}行: {str(e)}")
        if success > 0:
            db.commit()
        else:
            db.rollback()
        return ImportResultResponse(total=total, success=success, failed=total - success, errors=errors)

    @staticmethod
    def update(db: Session, user_id: int, req: UserUpdate, operator: SysUser) -> UserInfo:
        user = UserCRUD.get_by_id(db, user_id)
        if not user:
            raise ResourceNotFoundException(message="用户不存在")
        # 权限校验
        if operator.role != RoleEnum.ADMIN:
            if operator.id != user_id:
                raise PermissionDeniedException(message="只能修改本人信息，管理员除外")
            # 本人修改禁止改role/status
            if req.role is not None or req.status is not None:
                raise PermissionDeniedException(message="无权修改角色或状态字段")
        update_data = req.model_dump(exclude_unset=True)
        user = UserCRUD.update(db, user, update_data)
        db.commit()
        db.refresh(user)
        return AuthService._build_user_info(user)

    @staticmethod
    def update_profile(db: Session, current_user: SysUser, req: UserProfileUpdate) -> UserInfo:
        """用户自助修改个人资料（含密码修改）"""
        update_data = req.model_dump(exclude_unset=True, exclude={"old_password", "new_password"})
        # 处理密码修改
        if req.new_password:
            if not verify_password(req.old_password or "", current_user.password_hash):
                raise ParamValidateException(message="原密码不正确")
            update_data["password_hash"] = hash_password(req.new_password)
            # 改密成功则清除"首次登录强制改密"标记
            update_data["force_change_pwd"] = 0
        user = UserCRUD.update(db, current_user, update_data)
        db.commit()
        db.refresh(user)
        return AuthService._build_user_info(user)

    @staticmethod
    def delete(db: Session, user_id: int, operator: SysUser) -> None:
        """软删除用户"""
        if operator.role != RoleEnum.ADMIN:
            raise PermissionDeniedException(message="仅管理员可删除用户")
        if operator.id == user_id:
            raise ParamValidateException(message="不能删除自己的账号")
        rows = UserCRUD.soft_delete(db, user_id)
        if rows == 0:
            raise ResourceNotFoundException(message="用户不存在")
        db.commit()

    @staticmethod
    def batch_update_status(db: Session, user_ids: List[int], status: int, operator: SysUser) -> int:
        if operator.role != RoleEnum.ADMIN:
            raise PermissionDeniedException(message="仅管理员可批量修改用户状态")
        rows = UserCRUD.batch_update_status(db, user_ids, status)
        db.commit()
        return rows


class CollegeService:
    """学院管理业务服务"""

    @staticmethod
    def list_all(db: Session, include_disabled: bool = False) -> List[CollegeResponse]:
        colleges = CollegeCRUD.list_all(db, include_disabled=include_disabled)
        return [CollegeResponse.model_validate(c) for c in colleges]

    @staticmethod
    def create(db: Session, req: CollegeCreate, operator: SysUser) -> CollegeResponse:
        if operator.role != RoleEnum.ADMIN:
            raise PermissionDeniedException(message="仅管理员可新增学院")
        if CollegeCRUD.get_by_code(db, req.college_code):
            raise DataConflictException(message="学院编码已存在")
        college = CollegeCRUD.create(db, req.model_dump())
        db.commit()
        db.refresh(college)
        return CollegeResponse.model_validate(college)

    @staticmethod
    def update(db: Session, college_id: int, req: CollegeUpdate, operator: SysUser) -> CollegeResponse:
        if operator.role != RoleEnum.ADMIN:
            raise PermissionDeniedException(message="仅管理员可修改学院")
        obj = CollegeCRUD.get_by_id(db, college_id)
        if not obj:
            raise ResourceNotFoundException(message="学院不存在")
        obj = CollegeCRUD.update(db, obj, req.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(obj)
        return CollegeResponse.model_validate(obj)


class OperationLogService:
    """操作日志业务服务"""

    @staticmethod
    def paginate(db: Session, pager: PaginationParams, params: OperationLogQueryParams,
                 operator: SysUser):
        if operator.role != RoleEnum.ADMIN:
            raise PermissionDeniedException(message="仅管理员可查看操作日志")
        items, total = OperationLogCRUD.paginate(
            db,
            offset=pager.offset,
            limit=pager.limit,
            keyword=params.keyword,
            module_name=params.module_name,
            operation_type=params.operation_type,
            user_id=params.user_id,
            start_time=params.start_time,
            end_time=params.end_time,
            order_dir=pager.order_dir,
        )
        return items, total
