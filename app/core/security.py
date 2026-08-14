"""
JWT 认证与权限控制核心模块
实现：密码哈希校验、AccessToken/RefreshToken生成解析、当前用户获取依赖、角色权限校验依赖
"""
from typing import Optional, List, Set, Dict, Any
from datetime import datetime, timedelta, timezone
from enum import IntEnum

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthException, PermissionDeniedException
from app.database.session import get_db
from app.models import SysUser


# ====================================================================
# 角色枚举
# ====================================================================
class RoleEnum(IntEnum):
    """用户角色枚举，与sys_user.role字段对应"""
    STUDENT = 1           # 学生
    TEACHER = 2           # 指导教师
    EXPERT = 3            # 评审专家
    ADMIN = 4             # 系统管理员


# 角色显示名称映射
ROLE_NAME_MAP: Dict[int, str] = {
    RoleEnum.STUDENT: "学生",
    RoleEnum.TEACHER: "指导教师",
    RoleEnum.EXPERT: "评审专家",
    RoleEnum.ADMIN: "系统管理员",
}


# ====================================================================
# 密码哈希上下文 (bcrypt)
# ====================================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """明文密码 -> bcrypt哈希"""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验明文密码与哈希是否匹配"""
    # bcrypt 限制密码最大 72 字节，超出部分截断处理
    if len(plain_password.encode('utf-8')) > 72:
        plain_password = plain_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
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
    """创建JWT令牌的通用函数"""
    to_encode = {
        "sub": subject,                    # 主体：存储username
        "type": token_type,                # 令牌类型：access / refresh
        "iat": datetime.now(timezone.utc),  # 签发时间
    }
    if extra:
        to_encode.update(extra)
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_access_token(user: SysUser, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌（AccessToken），附带用户基本信息"""
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
    """创建刷新令牌（RefreshToken），仅保留最小信息"""
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    extra = {"uid": user.id}
    return _create_token(subject=user.username, token_type="refresh", expires_delta=expires_delta, extra=extra)


def decode_token(token: str) -> Dict[str, Any]:
    """
    解析并验证JWT令牌
    :raises AuthException: token无效、过期、格式错误等
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
    FastAPI 依赖函数：获取当前登录用户
    优先从 Header 获取 token，验证通过后从数据库加载用户并校验状态
    """
    # 允许从 query 参数也携带 token（用于文件下载等场景）
    if not token:
        token = request.query_params.get("token") or request.cookies.get("access_token")
    if not token:
        raise AuthException(message="未登录或登录已过期，请先登录")

    payload = decode_token(token)

    # 校验 token 类型
    if payload.get("type") != "access":
        raise AuthException(message="无效的令牌类型，请使用访问令牌")

    user_id: Optional[int] = payload.get("uid")
    username: Optional[str] = payload.get("sub")
    if not user_id or not username:
        raise AuthException(message="令牌中缺少必要的用户信息")

    # 从数据库加载用户（确保用户状态未变更、未删除）
    user = db.query(SysUser).filter(SysUser.id == user_id, SysUser.username == username).first()
    if not user:
        raise AuthException(message="用户不存在或已被删除")
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
    角色权限校验依赖类（可组合使用）
    用法示例：
        # 仅管理员
        Depends(RequireRole(RoleEnum.ADMIN))
        # 管理员或教师
        Depends(RequireRole(RoleEnum.ADMIN, RoleEnum.TEACHER))
    """

    def __init__(self, *allowed_roles: int):
        self.allowed_roles: Set[int] = set(allowed_roles)

    def __call__(self, current_user: SysUser = Depends(get_current_user)) -> SysUser:
        # 系统管理员拥有所有接口权限
        if RoleEnum.ADMIN in self.allowed_roles or current_user.role == RoleEnum.ADMIN:
            if current_user.role in self.allowed_roles or current_user.role == RoleEnum.ADMIN:
                return current_user
        if current_user.role not in self.allowed_roles:
            allowed_names = [ROLE_NAME_MAP.get(r, str(r)) for r in self.allowed_roles]
            raise PermissionDeniedException(
                message=f"无权限访问，仅以下角色可操作：{' / '.join(allowed_names)}"
            )
        return current_user


# 常用权限依赖快捷变量
require_admin = Depends(RequireRole(RoleEnum.ADMIN))
require_teacher_or_admin = Depends(RequireRole(RoleEnum.TEACHER, RoleEnum.ADMIN))
require_expert_or_admin = Depends(RequireRole(RoleEnum.EXPERT, RoleEnum.ADMIN))
require_student = Depends(RequireRole(RoleEnum.STUDENT))
require_login = Depends(get_current_user)
