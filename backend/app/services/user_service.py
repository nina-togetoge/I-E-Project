# ============================================================================
# 用户管理模块 业务逻辑层(Service)
# ----------------------------------------------------------------------------
# 业务功能：登录认证（账号/手机/邮箱 + 双 Token）、Token 刷新与吊销、用户增删改查、
#           批量导入、学院维护、操作日志查询，并在各入口落实角色与学院数据权限。
# 核心表：
#   sys_user         用户（账号、密码哈希、角色、学院、状态、登录信息、软删除）
#   sys_college      学院（编码、名称、启用状态）
#   sys_operation_log 操作日志（模块、操作类型、用户、学院、结果）
# 上游路由：app/api/v1/auth.py、user.py、college.py、log.py
# 下游依赖：app.crud.user（数据访问）、app.core.security（密码/Token/角色判断）、
#           app.core.deps（分页与数据范围）、app.utils.redis_cache（Token 黑名单、学院缓存）。
# 关键约束：
#   1) 角色分级：ADMIN(超管) > 学院管理员 > 教师 > 学生/专家；学院管理员仅限本院；
#   2) 非管理员不得查看超管资料；教师/专家跨院访问一律拒绝；
#   3) 学生端用户查询仅允许“学生/教师”白名单且返回脱敏字段，禁止拉取全校 PII；
#   4) 用户删除为软删除；登录/刷新令牌采用 Redis 黑名单，登出与轮换后立即失效；
#   5) 密码只存哈希，任何明文密码字段不得落库或返回。
# ============================================================================
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    verify_password, create_access_token, create_refresh_token,
    decode_token, extract_jti_exp, RoleEnum, ROLE_NAME_MAP, hash_password,
    is_super_admin, is_college_admin,
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
    ImportResultResponse,
)
from app.crud.user import UserCRUD, CollegeCRUD, OperationLogCRUD
from app.models import SysUser, SysCollege
from app.utils.redis_cache import TokenBlacklist, redis_client, CacheKeys


class AuthService:
    """认证相关业务服务：登录、刷新令牌、登出、用户信息组装。"""

    @staticmethod
    def login(db: Session, req: LoginRequest, client_ip: str) -> LoginResponse:
        """用户登录：校验账号密码 -> 生成双 Token -> 更新登录信息。

        参数：
            db: 数据库会话。
            req: 登录请求（username 可填账号/手机号/邮箱，password 明文）。
            client_ip: 客户端 IP，用于记录最近登录来源。
        返回：
            LoginResponse：access_token、refresh_token、有效期（秒）与用户信息。
        异常：
            用户不存在 / 密码错误 / 账号被禁用 → AuthException。
        副作用：
            更新最后登录 IP 与时间后提交，并刷新 ORM 对象。
        注意：
            账号不存在与密码错误返回同一提示，避免账号枚举；密码使用哈希校验。
        """
        # 1. 查找用户（账号 / 手机号 / 邮箱 均可登录）
        user = db.query(SysUser).filter(
            SysUser.is_deleted == 0,
            or_(
                SysUser.username == req.username,
                SysUser.phone == req.username,
                SysUser.email == req.username,
            ),
        ).first()
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
        """使用 RefreshToken 换取新的 AccessToken，并轮换 RefreshToken。

        参数：
            db: 数据库会话。
            req: 包含 refresh_token 的请求。
        返回：
            新的双 Token 与用户信息。
        异常：
            令牌类型错误 / 已被吊销 / 载荷缺失 / 用户不存在或被禁用 → AuthException。
        副作用：
            将旧 RefreshToken 的 jti 加入 Redis 黑名单，剩余有效期过后自动清理。
        注意：
            刷新属于“令牌轮换”：旧 refresh 立即作废，防止泄露后被重放；
            黑名单依赖 Redis，若 Redis 不可用则由底层缓存实现抛出异常（不降级放行）。
        """
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
        # 令牌轮换：旧 Refresh Token 立即吊销，防止被重放（泄露后无法重复刷新）
        old_jti, old_remaining = extract_jti_exp(payload)
        TokenBlacklist.add("refresh", old_jti, old_remaining)
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

        参数：
            current_user: 当前登录用户（仅用于语义标识，黑名单按令牌 jti 处理）。
            access_token_raw: 请求携带的 AccessToken 原文。
            refresh_token_raw: 可选的 RefreshToken 原文，前端主动登出时应一并传入。
        返回：无。
        副作用：向 Redis 写入两条带剩余 TTL 的黑名单记录。
        注意：
            令牌解析失败（如已过期）直接忽略，登出接口保持幂等；
            AccessToken 不落库，只依赖黑名单实现“主动失效”。
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
    def _build_user_info(user: SysUser) -> UserInfo:
        """构建 UserInfo 响应，含角色中文名、学院名与学校名。

        参数：user 用户 ORM 对象。
        返回：UserInfo 模型。
        注意：
            角色名来自 ROLE_NAME_MAP；未知角色保留原始值便于排查；
            学院名通过 ORM 关联对象读取，调用方需保证会话仍打开。
        """
        from app.core.config import settings
        info = UserInfo.model_validate(user, from_attributes=True)
        info.role_name = ROLE_NAME_MAP.get(user.role, f"未知({user.role})")
        info.school_name = settings.SCHOOL_NAME
        # 通过ORM关联对象取学院名
        if user.college:
            info.college_name = user.college.college_name
        return info

    @staticmethod
    def _build_safe_list_item(user: SysUser) -> UserSafeListItem:
        """学生端用户列表：仅返回非敏感字段（用于选团队成员/指导教师）。

        参数：user 用户 ORM 对象。
        返回：UserSafeListItem，隐藏邮箱/手机/状态等 PII。
        注意：学院关系读取失败时静默忽略，保证选人列表不因脏数据报错。
        """
        item = UserSafeListItem.model_validate(user, from_attributes=True)
        item.role_name = ROLE_NAME_MAP.get(user.role, f"未知({user.role})")
        try:
            if user.college:
                item.college_name = user.college.college_name
        except Exception:
            pass
        return item


class UserService:
    """用户管理业务服务。

    负责用户 CRUD、批量导入与状态变更，所有写方法内部提交事务。
    权限模型分层执行：超管全校、学院管理员本院、教师本院、本人仅自助字段。
    """

    # ====================================================================
    # 管理员 CRUD
    # ====================================================================
    @staticmethod
    def get_detail(db: Session, user_id: int, operator: SysUser) -> UserInfo:
        """查询单个用户详情，含行级权限校验。

        参数：db 会话、目标用户 id、当前操作人。
        返回：UserInfo（含角色/学院中文名）。
        权限：
            管理员可看全部；教师/专家仅可看同院且非超管账号；学生仅可看自己。
        异常：用户不存在 → ResourceNotFoundException；越权 → PermissionDeniedException。
        注意：学院为空时一律拒绝，避免“空学院”被当作同院而泄漏资料。
        """
        user = UserCRUD.get_by_id(db, user_id)
        if not user:
            raise ResourceNotFoundException(message="用户不存在")
        # 行级权限：管理员看全部；本院角色看本院；学生只看自己
        if operator.role != RoleEnum.ADMIN:
            # 非管理员一律不得查看系统管理员账号资料，避免越权获取超管信息
            if user.role == RoleEnum.ADMIN:
                raise PermissionDeniedException(message="无权查看系统管理员信息")
            if operator.id != user_id:
                if operator.role == RoleEnum.STUDENT:
                    raise PermissionDeniedException(message="无权查看其他用户信息")
                # 教师/专家：仅可查看同院用户（学院为空一律拒绝，避免跨院/超管资料泄露）
                if (not operator.college_id or not user.college_id
                        or operator.college_id != user.college_id):
                    raise PermissionDeniedException(message="无权查看其他学院用户信息")
        return AuthService._build_user_info(user)

    @staticmethod
    def paginate(db: Session, pager: PaginationParams, params: UserQueryParams,
                 data_scope: DataScope) -> Tuple[List, int]:
        """分页查询用户列表，自动注入数据权限并按调用方角色脱敏。

        参数：
            db: 数据库会话。
            pager: 分页/排序参数。
            params: 查询条件（关键词、角色、学院、状态）。
            data_scope: 当前用户的数据范围（角色、学院、可见范围）。
        返回：
            (用户列表, 总条数)；学生端返回 UserSafeListItem，其余返回 UserListItem。
        权限：
            学生仅可查学生/教师白名单且跨院可选人；专家一律拒绝；
            未绑定学院的教师拒绝，避免数据范围退化为全校。
        注意：
            学生端构造一个“全开放但带角色白名单”的临时 DataScope，
            只用于控制查询范围，返回字段仍做 PII 脱敏。
        """
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
            # 学生端：选人场景下允许跨学院搜索（组建跨学科团队），仍脱敏返回PII
            effective_scope = DataScope.__new__(DataScope)
            effective_scope.user = data_scope.user
            effective_scope.db = data_scope.db
            effective_scope.role = data_scope.role
            effective_scope.college_id = data_scope.college_id
            effective_scope.user_id = data_scope.user_id
            effective_scope.scope = {
                "all": True,
                "college_ids": None,
                "owner_user_ids": None,
                "is_student_whitelist": True,
                "role_whitelist": [params.role],
            }
        elif data_scope.role == RoleEnum.EXPERT:
            # 专家无查询用户全量名单的合法场景，直接拒绝，避免拉取全校用户PII
            raise PermissionDeniedException(message="专家无权限查询用户列表")
        elif data_scope.role == RoleEnum.TEACHER and not data_scope.college_id:
            # 未绑定学院的教师数据范围为空白，若放行会退化为"全校无过滤"，禁止
            raise PermissionDeniedException(message="未绑定学院的教师无权限查询用户列表")
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
        """创建用户：真超级管理员(全校) / 学院管理员(仅本院非ADMIN) / 教师(本院非ADMIN)"""
        # ---- 修复前 Bug：operator.role == ADMIN 就放行了，绑定学院的学院管理员能创建全校 ADMIN 账号 ----
        # 修复策略：按权限从高到低分流
        #   A. is_super_admin → 无限制（可创建所有角色、所有学院）
        #   B. is_college_admin → 仅本院、不得创建 role=ADMIN
        #   C. role=TEACHER   → 仅本院、不得创建 role=ADMIN
        #   D. 其他角色(学生/专家) → 无权限
        if is_super_admin(operator):
            # 真超级管理员：直接进入后续基础字段校验
            pass
        elif is_college_admin(operator) or operator.role == RoleEnum.TEACHER:
            # 学院管理员 / 普通教师：统一走本院限制
            if req.role == RoleEnum.ADMIN:
                raise PermissionDeniedException(message="无权限创建系统管理员账号，请联系校级管理员")
            if operator.college_id:
                if req.college_id and req.college_id != operator.college_id:
                    raise PermissionDeniedException(message="只能创建本院用户")
                if not req.college_id:
                    req.college_id = operator.college_id
        else:
            # 学生 / 专家：完全禁止创建用户
            raise PermissionDeniedException(message="无权限创建用户")

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
        """批量创建用户（Excel 导入调用），逐行容错。

        参数：db 会话、用户字典列表（已解析的表格行）、当前操作人。
        返回：ImportResultResponse（总数/成功数/失败数/逐行错误信息）。
        权限：每行复用 UserService.create 的分级权限校验，越权行计入失败。
        副作用：成功行各自提交；失败行回滚后继续处理下一行。
        注意：
            数据库异常会使 session 失效，因此每行失败都必须 rollback，
            否则后续行无法继续执行；最终再整体 commit 兜底。
        """
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
                # 数据库级异常会使 session 进入失效状态，必须回滚后才能处理下一行
                db.rollback()
        db.commit()
        return ImportResultResponse(total=total, success=success, failed=total - success, errors=errors)

    @staticmethod
    def update(db: Session, user_id: int, req: UserUpdate, operator: SysUser) -> UserInfo:
        """更新用户资料（按传入字段部分更新，含分级权限）。

        参数：db 会话、目标用户 id、更新表单、当前操作人。
        返回：更新后的 UserInfo。
        权限：
            超管可改任意字段；学院管理员仅可改本院非超管用户，且不得改角色/密码/学院；
            普通用户仅可改本人非敏感资料，密码必须走 update_profile 校验原密码。
        异常：用户不存在 / 越权 → 对应业务异常。
        注意：权限分支通过后统一使用 exclude_unset 更新，未传字段保持不变。
        """
        user = UserCRUD.get_by_id(db, user_id)
        if not user:
            raise ResourceNotFoundException(message="用户不存在")
        # ---- 权限校验（修复 ADMIN 分级 Bug）----
        if is_super_admin(operator):
            # 真超级管理员：可修改任意用户任意字段
            pass
        elif is_college_admin(operator):
            # 学院管理员：仅能修改本院非管理员用户，且不得改角色/密码/学院
            # （严格要求双方学院均存在且一致，避免目标为超管(college_id=NULL)时短路放行）
            if (not operator.college_id or not user.college_id
                    or user.college_id != operator.college_id):
                raise PermissionDeniedException(message="仅可修改本院用户")
            if user.role == RoleEnum.ADMIN:
                raise PermissionDeniedException(message="无权限修改系统管理员账号")
            if req.role is not None:
                raise PermissionDeniedException(message="无权限修改用户角色")
            if req.password is not None:
                raise PermissionDeniedException(message="无权限直接重置用户密码，请联系用户通过个人资料入口修改")
            if req.college_id is not None and req.college_id != operator.college_id:
                raise PermissionDeniedException(message="仅可分配本院学院")
        elif operator.id == user_id:
            # 本人修改：禁止改 role/status/college_id，且不得直接重置密码（改密须走 update_profile 校验原密码）
            if (req.role is not None or req.status is not None
                    or req.college_id is not None or req.password is not None):
                raise PermissionDeniedException(
                    message="无权修改角色、状态、学院或密码字段，修改密码请使用个人资料入口")
        else:
            raise PermissionDeniedException(message="只能修改本人信息，管理员除外")

        update_data = req.model_dump(exclude_unset=True)
        user = UserCRUD.update(db, user, update_data)
        db.commit()
        db.refresh(user)
        return AuthService._build_user_info(user)

    @staticmethod
    def update_profile(db: Session, current_user: SysUser, req: UserProfileUpdate) -> UserInfo:
        """用户自助修改个人资料（含修改密码）。

        参数：db 会话、当前用户、资料表单（可含 old_password/new_password）。
        返回：更新后的 UserInfo。
        异常：原密码错误 → ParamValidateException。
        副作用：
            1) 修改密码时写入新的 password_hash；
            2) 同时把 force_change_pwd 置 0，表示已完成首次强制改密。
        注意：
            密码相关字段从 update_data 中排除，避免把明文/旧密码写入模型；
            不带 new_password 时仅更新普通资料。
        """
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
        """软删除用户。

        参数：db 会话、目标用户 id、当前操作人。
        返回：无。
        权限：超管可删任意用户（不能删自己）；学院管理员仅可删本院非超管用户。
        异常：删除自己 / 越权 / 用户不存在 → 对应业务异常。
        注意：UserCRUD.soft_delete 返回受影响行数，为 0 表示目标不存在。
        """
        if operator.id == user_id:
            raise ParamValidateException(message="不能删除自己的账号")
        # ---- 分级权限 ----
        if is_super_admin(operator):
            # 真超级管理员：除了不能删自己（上面），其他用户可随意删
            pass
        elif is_college_admin(operator):
            # 学院管理员：仅可删除本院非ADMIN用户
            target = UserCRUD.get_by_id(db, user_id)
            if not target:
                raise ResourceNotFoundException(message="用户不存在")
            if target.role == RoleEnum.ADMIN:
                raise PermissionDeniedException(message="无权限删除系统管理员账号")
            # 学院管理员严格限定本院：未绑定学院的用户不归任何学院管理员管辖
            if not operator.college_id or not target.college_id or target.college_id != operator.college_id:
                raise PermissionDeniedException(message="仅可删除本院用户")
        else:
            raise PermissionDeniedException(message="仅管理员可删除用户")
        rows = UserCRUD.soft_delete(db, user_id)
        if rows == 0:
            raise ResourceNotFoundException(message="用户不存在")
        db.commit()

    @staticmethod
    def batch_update_status(db: Session, user_ids: List[int], status: int, operator: SysUser) -> int:
        """批量启用/禁用用户。

        参数：db 会话、目标用户 id 列表、目标状态（1=启用，0=禁用）、当前操作人。
        返回：实际更新的行数。
        权限：超管全校；学院管理员仅限本院且不能包含超管账号。
        注意：
            学院管理员场景先逐条校验，任一目标越权则整批拒绝（事务内不会更新），
            避免部分成功造成权限边界不一致。
        """
        if is_super_admin(operator):
            pass  # 全校无限制
        elif is_college_admin(operator):
            # 学院管理员：仅允许批量修改本院用户的状态，且不能包含 role=ADMIN
            targets = UserCRUD.list_by_ids(db, user_ids) or []
            for t in targets:
                if t.role == RoleEnum.ADMIN:
                    raise PermissionDeniedException(message=f"用户 [{t.username}] 是系统管理员，学院管理员无权修改状态")
                if not operator.college_id or not t.college_id or t.college_id != operator.college_id:
                    raise PermissionDeniedException(message=f"用户 [{t.username}] 不属于本院，学院管理员无权修改状态")
        else:
            raise PermissionDeniedException(message="仅管理员可批量修改用户状态")
        rows = UserCRUD.batch_update_status(db, user_ids, status)
        db.commit()
        return rows


class CollegeService:
    """学院管理业务服务。

    学院属于组织架构基础数据，仅超级管理员可增改；变更后清 Redis 缓存，
    避免公共接口 /api/common/colleges 返回旧数据。
    """

    @staticmethod
    def list_all(db: Session, include_disabled: bool = False) -> List[CollegeResponse]:
        """查询学院列表。

        参数：db 会话、include_disabled 是否包含已禁用学院。
        返回：CollegeResponse 列表，供下拉选择与筛选使用。
        """
        colleges = CollegeCRUD.list_all(db, include_disabled=include_disabled)
        return [CollegeResponse.model_validate(c) for c in colleges]

    @staticmethod
    def create(db: Session, req: CollegeCreate, operator: SysUser) -> CollegeResponse:
        """新增学院。

        参数：db 会话、创建表单、当前操作人。
        返回：新建的学院响应。
        权限：仅超级管理员（学院管理员不得管理组织架构）。
        异常：非超管 → PermissionDeniedException；编码重复 → DataConflictException。
        副作用：提交事务并清除学院列表缓存。
        """
        # 仅真超级管理员可新增学院（学院管理员不得跨院管理组织架构）
        if not is_super_admin(operator):
            raise PermissionDeniedException(message="仅超级管理员可新增学院")
        if CollegeCRUD.get_by_code(db, req.college_code):
            raise DataConflictException(message="学院编码已存在")
        college = CollegeCRUD.create(db, req.model_dump())
        db.commit()
        db.refresh(college)
        CollegeService._clear_cache()
        return CollegeResponse.model_validate(college)

    @staticmethod
    def update(db: Session, college_id: int, req: CollegeUpdate, operator: SysUser) -> CollegeResponse:
        """修改学院信息。

        参数：db 会话、学院 id、更新表单、当前操作人。
        返回：更新后的学院响应。
        权限：仅超级管理员。
        异常：非超管 / 学院不存在 → 对应业务异常。
        副作用：提交事务并清除学院列表缓存。
        """
        # 仅真超级管理员可修改学院；学院管理员不得修改本院/他院组织架构
        if not is_super_admin(operator):
            raise PermissionDeniedException(message="仅超级管理员可修改学院")
        obj = CollegeCRUD.get_by_id(db, college_id)
        if not obj:
            raise ResourceNotFoundException(message="学院不存在")
        obj = CollegeCRUD.update(db, obj, req.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(obj)
        CollegeService._clear_cache()
        return CollegeResponse.model_validate(obj)

    @staticmethod
    def _clear_cache() -> None:
        """学院变动后清除缓存，避免 /api/common/colleges 返回陈旧数据。

        注意：Redis 不可用时静默忽略，组织架构写操作不能因缓存问题失败。
        """
        try:
            redis_client.delete(CacheKeys.COLLEGE_LIST)
        except Exception:
            pass


class OperationLogService:
    """操作日志业务服务。"""

    @staticmethod
    def paginate(db: Session, pager: PaginationParams, params: OperationLogQueryParams,
                 operator: SysUser):
        """分页查询操作日志。

        参数：
            db: 数据库会话。
            pager: 分页与排序参数。
            params: 日志筛选条件（关键词/模块/操作类型/用户/时间/角色/状态）。
            operator: 当前操作人，用于确定数据范围。
        返回：
            (日志列表, 总条数)。
        权限：
            仅管理员可查看；超管看全部，学院管理员仅看本院用户日志。
        注意：
            college_id 为 None 表示不过滤学院（超管）；学院管理员无学院时
            会退化为 None，存在越权风险，故前置已要求其为 ADMIN 角色。
        """
        if operator.role != RoleEnum.ADMIN:
            raise PermissionDeniedException(message="仅管理员可查看操作日志")
        # 数据范围：真超级管理员看全部日志；学院管理员仅看本院用户日志
        college_id = None if is_super_admin(operator) else operator.college_id
        items, total = OperationLogCRUD.paginate(
            db,
            offset=pager.offset,
            limit=pager.limit,
            keyword=params.keyword,
            module_name=params.module_name,
            operation_type=params.operation_type,
            user_id=params.user_id,
            college_id=college_id,
            start_time=params.start_time,
            end_time=params.end_time,
            modules=params.modules,
            operation_types=params.operation_types,
            user_roles=params.user_roles,
            statuses=params.statuses,
            order_dir=pager.order_dir,
        )
        return items, total
