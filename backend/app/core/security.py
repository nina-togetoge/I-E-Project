# ====================================================================
# JWT 认证与权限控制核心模块（app/core/security.py）
# --------------------------------------------------------------------
# 解决什么问题：
#   为全平台提供统一的“你是谁”（认证）与“你能做什么”（路由级授权）能力，
#   业务路由只需依赖 get_current_user / RequireRole 即可拿到可信用户对象。
# 被谁使用：
#   app/core/deps.py（数据权限范围）、所有 api/routers、操作日志中间件
#   （中间件自行解析 token 仅用于记录操作人，不参与鉴权）。
# 关键设计：
#   1. AccessToken 携带 uid/role/name/college_id，便于日志与前端菜单快速判断；
#      但真正鉴权仍以数据库中的用户状态为准，避免令牌签发后被禁用仍可访问。
#   2. RefreshToken 只携带 uid，且 type 不同，不能直接访问业务接口。
#   3. 每个令牌都有 jti，登出/强制下线时写入 Redis 黑名单实现即时吊销。
#   4. 管理员分两级：超管（role=4 且 college_id 为空）与学院管理员
#      （role=4 且 college_id 非空），路由级 RequireRole 对两者都放行，
#      院级边界统一在 service 层用 is_super_admin/is_college_admin 收窄。
# ====================================================================
"""
JWT 认证与权限控制核心模块
实现：密码哈希校验、AccessToken/RefreshToken生成解析、当前用户获取依赖、角色权限校验依赖
"""
from typing import Optional, List, Set, Dict, Any
from datetime import datetime, timedelta, timezone
from enum import IntEnum
import uuid

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthException, PermissionDeniedException
from app.database.session import get_db
from app.models import SysUser
from app.utils.redis_cache import TokenBlacklist


# ====================================================================
# Token 来源 URL 白名单
# ====================================================================
# 仅以下路由前缀允许从 ?token= URL 查询参数 / Cookie 兜底携带 access token
# 其他接口必须严格从 Authorization: Bearer <token> 头中携带，避免Referer/日志泄露
URL_TOKEN_WHITELIST_PREFIXES: tuple = (
    "/api/files/download/",   # 文件下载（<a>直链场景无header能力）
    "/api/files/preview/",    # 文件预览（<img>/<iframe>直链场景）
    "/api/projects/export",   # 项目导出（浏览器新标签页下载）
)


# ====================================================================
# 角色枚举
# ====================================================================
class RoleEnum(IntEnum):
    """用户角色枚举，与sys_user.role字段对应（数据库存整型，避免字符串拼写不一致）"""
    STUDENT = 1           # 学生：可申报项目、提交中期/结项、报销
    TEACHER = 2           # 指导教师：确认申报、审核中期/结项、查看本院项目
    EXPERT = 3            # 评审专家：仅能看到被分配的项目，评审时脱敏
    ADMIN = 4             # 系统管理员：需结合 college_id 再分超管/学院管理员


# 角色显示名称映射：用于错误提示与导出文件，前端展示名称以此为准
ROLE_NAME_MAP: Dict[int, str] = {
    RoleEnum.STUDENT: "学生",
    RoleEnum.TEACHER: "指导教师",
    RoleEnum.EXPERT: "评审专家",
    RoleEnum.ADMIN: "系统管理员",
}


# ====================================================================
# 管理员权限分级辅助函数（修复"学院管理员实为系统管理员"Bug）
#   - 真·超级管理员：role=4（ADMIN）且 college_id 为空 → 全校范围 all=True
#   - 学院管理员：  role=4（ADMIN）且 college_id 非空 → 仅本院范围
# 所有 ADMIN-only 独占权限（分配专家 / 校级复审 / 创建系统管理员账号等）
# 必须通过 is_super_admin() 判断，不能用 operator.role == ADMIN 的简单判断，
# 否则绑定学院的「学院管理员」会越权执行校级操作、查看全校数据。
# ====================================================================
def is_super_admin(user) -> bool:
    """
    真·超级系统管理员（全校权限）：role=ADMIN 且 未绑定学院。

    参数：
        user：SysUser 实例或 None。
    返回：
        True 表示可跨学院查看/操作全部数据。
    说明：
        用 getattr 做防御式读取，兼容依赖对象（如 DataScope）与 ORM 实例传入；
        college_id 为 0/None/空字符串均视为“未绑定学院”。
    """
    if not user:
        return False
    role = getattr(user, "role", None)
    college_id = getattr(user, "college_id", None)
    return role == RoleEnum.ADMIN and not bool(college_id)


def is_college_admin(user) -> bool:
    """
    学院管理员（本院权限）：role=ADMIN 且 已绑定具体学院。

    参数：
        user：SysUser 实例或 None。
    返回：
        True 表示只能在所属学院范围内操作。
    """
    if not user:
        return False
    role = getattr(user, "role", None)
    college_id = getattr(user, "college_id", None)
    return role == RoleEnum.ADMIN and bool(college_id)


# ====================================================================
# 密码哈希上下文 (bcrypt)
# ====================================================================
# bcrypt 自带随机盐，同一明文每次哈希结果不同；deprecated="auto" 允许旧算法
# 哈希在校验成功后自动升级，避免历史数据无法登录
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _truncate_bcrypt_password(plain_password: str) -> str:
    """bcrypt 仅使用前 72 字节；哈希与校验必须采用完全一致的截断方式。

    直接 decode 会在多字节字符被截半时丢字节，导致“注册时能登录、校验时却失败”。
    这里按字节截断后再以替换方式解码，保证两次调用得到同一字符串。
    """
    raw = plain_password.encode("utf-8")
    if len(raw) <= 72:
        return plain_password
    return raw[:72].decode("utf-8", errors="replace")


def hash_password(plain_password: str) -> str:
    """
    明文密码 -> bcrypt 哈希。

    参数：
        plain_password：用户输入的原始密码。
    返回：
        bcrypt 哈希串（含算法、cost 与盐），可直接入库。
    注意：
        必须先做与校验一致的 72 字节截断，否则长密码注册后无法登录。
    """
    return pwd_context.hash(_truncate_bcrypt_password(plain_password))


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    校验明文密码与数据库中的哈希是否匹配。

    参数：
        plain_password：登录时输入的明文密码。
        password_hash：数据库中保存的 bcrypt 哈希。
    返回：
        True 匹配，False 不匹配（不区分“用户不存在”与“密码错误”由上层统一提示）。
    异常：
        正常情况下不抛出；部分 bcrypt 版本对非法哈希抛 ValueError，
        此时回退到 bcrypt 底层 checkpw，仍失败则视为不匹配/哈希损坏。
    """
    plain_password = _truncate_bcrypt_password(plain_password)
    try:
        return pwd_context.verify(plain_password, password_hash)
    except ValueError:
        # 处理某些 bcrypt 版本的兼容性问题
        # 直接使用 bcrypt 底层库进行验证
        import bcrypt as _bcrypt
        return _bcrypt.checkpw(
            plain_password.encode('utf-8'),
            password_hash.encode('utf-8') if isinstance(password_hash, str) else password_hash
        )


# ====================================================================
# JWT Token 生成与解析
# ====================================================================

# OAuth2 方案：从 Authorization: Bearer <token> 头中提取
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False  # 关闭自动抛错，由我们自定义 AuthException
)


def _create_token(subject: str, token_type: str, expires_delta: timedelta, extra: Optional[Dict[str, Any]] = None) -> str:
    """
    创建 JWT 令牌的通用实现（access/refresh 共用）。

    参数：
        subject：令牌主体，本项目存 username。
        token_type：access 或 refresh，解码时会校验，防止刷新令牌被当访问令牌用。
        expires_delta：有效期时长，由调用方按配置换算。
        extra：附加声明（uid/role/name/college_id 等）。
    返回：
        使用 HS256 与全局密钥签名后的 JWT 字符串。
    注意：
        时间戳统一用 UTC，避免服务器时区差异导致令牌提前/延后过期。
    """
    now = datetime.now(timezone.utc)
    to_encode = {
        "jti": uuid.uuid4().hex,      # 令牌唯一ID（用于黑名单吊销）
        "sub": subject,               # 主体：存储username
        "type": token_type,           # 令牌类型：access / refresh
        "iat": int(now.timestamp()),  # 签发时间
    }
    if extra:
        to_encode.update(extra)
    expire = now + expires_delta
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def extract_jti_exp(payload: Dict[str, Any]) -> tuple[Optional[str], int]:
    """
    从已解析 payload 中抽取 (jti, 剩余秒数)。

    参数：
        payload：decode_token 返回的声明字典。
    返回：
        (jti, 剩余有效秒数)；exp 缺失或已过期时剩余秒数为 0。
    用途：
        登出时把 jti 写入 Redis 黑名单，TTL 设为剩余秒数，
        令牌自然过期后黑名单键自动消失，避免无限增长。
    """
    jti = payload.get("jti")
    exp = payload.get("exp")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    remaining = max(0, int(exp) - now_ts) if exp else 0
    return jti, remaining


def create_access_token(user: SysUser, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建访问令牌（AccessToken）。

    参数：
        user：已通过密码校验的用户 ORM 对象。
        expires_delta：自定义有效期，默认取 ACCESS_TOKEN_EXPIRE_MINUTES（120 分钟）。
    返回：
        JWT 字符串，前端放在 Authorization: Bearer <token>。
    说明：
        附带 uid/role/name/college_id 只是“快照”，用户被禁用/改角色后
        仍以 get_current_user 查库结果为准，因此无需强制令牌立即失效。
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    extra = {
        "uid": user.id,
        "role": user.role,
        "name": user.real_name,
        "college_id": user.college_id,
    }
    return _create_token(subject=user.username, token_type="access", expires_delta=expires_delta, extra=extra)


def create_refresh_token(user: SysUser, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建刷新令牌（RefreshToken）。

    参数：
        user：用户 ORM 对象。
        expires_delta：自定义有效期，默认取 REFRESH_TOKEN_EXPIRE_DAYS（7 天）。
    返回：
        JWT 字符串，仅用于 /api/auth/refresh 换取新的访问令牌。
    说明：
        只放 uid 不放角色信息，减小泄露影响面；刷新时重新查库获取最新角色。
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    extra = {"uid": user.id}
    return _create_token(subject=user.username, token_type="refresh", expires_delta=expires_delta, extra=extra)


def decode_token(token: str) -> Dict[str, Any]:
    """
    解析并验证 JWT 令牌（签名、算法、过期时间、必要声明）。

    参数：
        token：前端传来的原始 JWT 字符串。
    返回：
        解码后的声明字典（含 jti/sub/type/uid/exp 等）。
    异常：
        AuthException：过期、声明非法、签名不匹配或格式错误，
        统一转换为 401 业务异常，避免把 jose 的底层异常暴露给调用方。
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthException(message="登录已过期，请重新登录")
    except jwt.JWTClaimsError:
        raise AuthException(message="令牌声明无效，请重新登录")
    except JWTError:
        raise AuthException(message="无效的访问令牌，请重新登录")


# ====================================================================
# 依赖注入：获取当前用户
# ====================================================================

async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> SysUser:
    """
    FastAPI 依赖函数：获取当前登录用户。

    参数：
        request：当前请求，用于判断路径是否在 URL token 白名单内。
        token：OAuth2PasswordBearer 从 Authorization: Bearer 提取的令牌。
        db：请求级数据库会话。
    返回：
        数据库中最新状态的 SysUser（未被删除、status=1）。
    异常：
        AuthException：未携带令牌、类型不是 access、命中黑名单、
        用户不存在/已删除/被禁用。
    说明：
        默认严格从 Authorization: Bearer 头取 token；
        仅在白名单接口允许从 ?token= 查询参数或 Cookie 兜底携带（用于下载/预览/导出场景）。
    """
    path = request.url.path
    allow_url_fallback = any(path.startswith(p) for p in URL_TOKEN_WHITELIST_PREFIXES)

    # [P1-1] URL token 兜底仅对白名单路径开放，其他接口强制使用 Authorization Header
    if not token and allow_url_fallback:
        token = request.query_params.get("token") or request.cookies.get("access_token")
    if not token:
        raise AuthException(message="未登录或登录已过期，请先登录")

    # 1. 验签并解析：过期/篡改会在 decode_token 内转为 AuthException
    payload = decode_token(token)

    # 2. 校验 token 类型，防止把有效期更长的 refresh_token 当访问令牌使用
    if payload.get("type") != "access":
        raise AuthException(message="无效的令牌类型，请使用访问令牌")

    # [P1-8] Redis 黑名单校验（登出/强制下线时吊销）；Redis 不可用时自动降级内存
    jti = payload.get("jti")
    if TokenBlacklist.is_blacklisted("access", jti):
        raise AuthException(message="登录已失效，请重新登录")

    user_id: Optional[int] = payload.get("uid")
    username: Optional[str] = payload.get("sub")
    if not user_id or not username:
        raise AuthException(message="令牌中缺少必要的用户信息")

    # 3. 从数据库加载用户（确保用户状态未变更、未删除）
    #    不直接信任令牌里的 role/college_id：管理员改角色、禁用账号后应立即生效
    user = db.query(SysUser).filter(SysUser.id == user_id, SysUser.username == username).first()
    if not user:
        raise AuthException(message="用户不存在或已被删除")
    # 4. 软删除与禁用状态检查：status=1 为可登录状态
    if user.is_deleted == 1:
        raise AuthException(message="账号已被删除")
    if user.status != 1:
        raise AuthException(message="账号已被禁用，请联系管理员")

    return user


# ====================================================================
# 依赖注入：角色权限校验
# ====================================================================

class RequireRole:
    """
    角色权限校验依赖类（可组合使用）。

    用法示例：
        # 仅管理员
        Depends(RequireRole(RoleEnum.ADMIN))
        # 管理员或教师
        Depends(RequireRole(RoleEnum.ADMIN, RoleEnum.TEACHER))
    说明：
        这是“路由级”粗粒度守卫，只回答“该角色能否进入这个接口”；
        “能看哪些学院/哪些项目”属于行级权限，由 DataScope + service 层收窄。
    """

    def __init__(self, *allowed_roles: int):
        # 用 set 存储，便于 O(1) 判断且自动去重
        self.allowed_roles: Set[int] = set(allowed_roles)

    def __call__(self, current_user: SysUser = Depends(get_current_user)) -> SysUser:
        """
        校验当前用户角色是否在允许集合内。

        参数：
            current_user：由 get_current_user 注入的已登录用户。
        返回：
            原样返回 current_user，便于路由直接使用。
        异常：
            PermissionDeniedException：角色不在白名单时抛出 403 业务异常，
            错误消息会列出允许的角色中文名，方便前端提示。
        """
        # 系统管理员(ADMIN)是平台超级操作者，路由级守卫对其放行；
        # 各角色的精细权限（如"学院管理员仅限本院"）统一由 service 层校验。
        if current_user.role == RoleEnum.ADMIN or current_user.role in self.allowed_roles:
            return current_user
        allowed_names = [ROLE_NAME_MAP.get(r, str(r)) for r in self.allowed_roles]
        raise PermissionDeniedException(
            message=f"无权限访问，仅以下角色可操作：{' / '.join(allowed_names)}"
        )


# 常用权限依赖快捷变量：
# require_admin 供仅管理员可用的路由直接 Depends(require_admin)；
# require_login 供“只要登录即可”的接口使用，省去重复写 Depends(get_current_user)
require_admin = Depends(RequireRole(RoleEnum.ADMIN))
require_login = Depends(get_current_user)
