"""
用户管理模块 Pydantic v2 数据校验模型
分为请求模型（Create/Update/Query）和响应模型（Response/List）
"""
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator

from app.core.security import RoleEnum


# ====================================================================
# 学院相关模型
# ====================================================================
class CollegeBase(BaseModel):
    college_code: str = Field(..., max_length=32, description="学院编码")
    college_name: str = Field(..., max_length=128, description="学院名称")
    dean_id: Optional[int] = Field(default=None, description="院长ID")
    sort_order: int = Field(default=0, ge=0, description="排序序号")
    status: int = Field(default=1, ge=0, le=1, description="状态 0-停用 1-启用")


class CollegeCreate(CollegeBase):
    """新增学院请求模型"""
    pass


class CollegeUpdate(BaseModel):
    """更新学院请求模型（全部可选，支持部分更新）"""
    college_code: Optional[str] = Field(default=None, max_length=32)
    college_name: Optional[str] = Field(default=None, max_length=128)
    dean_id: Optional[int] = None
    sort_order: Optional[int] = None
    status: Optional[int] = Field(default=None, ge=0, le=1)


class CollegeResponse(CollegeBase):
    """学院响应模型"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ====================================================================
# 登录与认证相关模型
# ====================================================================
class LoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(..., min_length=2, max_length=64, description="登录账号")
    password: str = Field(..., min_length=4, max_length=128, description="登录密码")


class LoginResponse(BaseModel):
    """登录响应：双Token + 用户基本信息"""
    access_token: str = Field(..., description="访问令牌(短期)")
    refresh_token: str = Field(..., description="刷新令牌(长期)")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(..., description="访问令牌过期秒数")
    user_info: "UserInfo"


class RefreshTokenRequest(BaseModel):
    """刷新Token请求"""
    refresh_token: str = Field(..., description="刷新令牌")


# ====================================================================
# 用户核心模型
# ====================================================================
class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=64, description="登录账号/学号/工号")
    real_name: str = Field(..., min_length=1, max_length=64, description="真实姓名")
    email: Optional[EmailStr] = Field(default=None, max_length=128, description="邮箱")
    phone: Optional[str] = Field(default=None, pattern=r"^1[3-9]\d{9}$", description="手机号")
    role: int = Field(..., ge=1, le=4, description="角色: 1-学生 2-教师 3-专家 4-管理员")
    college_id: Optional[int] = Field(default=None, description="所属学院ID")
    avatar: Optional[str] = Field(default=None, max_length=255, description="头像URL")
    status: int = Field(default=1, ge=0, le=1, description="状态 0-禁用 1-启用")


class UserCreate(UserBase):
    """创建用户请求"""
    password: str = Field(..., min_length=6, max_length=128, description="初始密码")


class UserRegister(BaseModel):
    """学生自助注册请求"""
    username: str = Field(..., min_length=2, max_length=64, description="学号")
    password: str = Field(..., min_length=6, max_length=128)
    real_name: str = Field(..., max_length=64)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    college_id: int = Field(..., description="所属学院")


class UserUpdate(BaseModel):
    """管理员更新用户信息"""
    real_name: Optional[str] = Field(default=None, max_length=64)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[int] = Field(default=None, ge=1, le=4)
    college_id: Optional[int] = None
    avatar: Optional[str] = None
    status: Optional[int] = Field(default=None, ge=0, le=1)
    password: Optional[str] = Field(default=None, min_length=6, max_length=128, description="非空则重置密码")


class UserProfileUpdate(BaseModel):
    """用户自助更新个人信息"""
    real_name: Optional[str] = Field(default=None, max_length=64)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    old_password: Optional[str] = Field(default=None, min_length=4, description="修改密码时需提供原密码")
    new_password: Optional[str] = Field(default=None, min_length=6, max_length=128, description="新密码")

    @field_validator("new_password")
    @classmethod
    def _check_old_password(cls, v, values):
        if v and not values.data.get("old_password"):
            raise ValueError("修改密码必须提供原密码(old_password)")
        return v


class UserInfo(BaseModel):
    """用户基本信息响应（登录后返回，不含敏感字段）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: str
    email: Optional[str]
    phone: Optional[str]
    role: int
    role_name: str = ""  # 由业务层赋值
    college_id: Optional[int]
    college_name: Optional[str] = None  # 关联查询后赋值
    avatar: Optional[str]
    status: int
    last_login_at: Optional[datetime]
    created_at: datetime


class UserListItem(UserInfo):
    """用户列表项响应"""
    updated_at: datetime


# ====================================================================
# 查询 / 批量操作模型
# ====================================================================
class UserQueryParams(BaseModel):
    """用户列表查询参数"""
    keyword: Optional[str] = Field(default=None, max_length=64, description="关键词(账号/姓名/邮箱)")
    role: Optional[int] = Field(default=None, ge=1, le=4, description="角色过滤")
    college_id: Optional[int] = Field(default=None, description="学院过滤")
    status: Optional[int] = Field(default=None, ge=0, le=1)


class UserBatchCreateRequest(BaseModel):
    """批量创建用户（Excel导入后调用）"""
    users: List[UserCreate] = Field(..., max_length=500, description="用户列表")


class UserBatchDeleteRequest(BaseModel):
    """批量删除用户"""
    user_ids: List[int] = Field(..., min_length=1, max_length=500)


class UserBatchStatusRequest(BaseModel):
    """批量启/禁用用户"""
    user_ids: List[int] = Field(..., min_length=1, max_length=500)
    status: int = Field(..., ge=0, le=1)


class ImportResultResponse(BaseModel):
    """Excel批量导入结果"""
    total: int
    success: int
    failed: int
    errors: List[str] = Field(default_factory=list)


# ====================================================================
# 操作日志响应模型
# ====================================================================
class OperationLogQueryParams(BaseModel):
    keyword: Optional[str] = None
    module_name: Optional[str] = None
    operation_type: Optional[str] = None
    user_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class OperationLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int]
    username: Optional[str]
    real_name: Optional[str]
    user_role: Optional[int]
    operation_type: str
    module_name: str
    operation_desc: Optional[str]
    request_method: Optional[str]
    request_url: Optional[str]
    response_code: Optional[int]
    ip_address: Optional[str]
    cost_time: Optional[int]
    operation_time: datetime


# 让LoginResponse.user_info引用生效
LoginResponse.model_rebuild()
