# ====================================================================
# 用户/学院模块 Schema
# --------------------------------------------------------------------
# 分组说明：
#   1. 学院：CollegeBase / CollegeCreate / CollegeUpdate / CollegeResponse；
#   2. 认证：LoginRequest / LoginResponse / RefreshTokenRequest / LogoutRequest；
#   3. 用户：UserBase / UserCreate / UserUpdate / UserProfileUpdate，
#      响应 UserInfo / UserListItem / UserSafeListItem（学生端脱敏）；
#   4. 查询与批量：UserQueryParams / UserBatch* / ImportResultResponse；
#   5. 审计：OperationLogQueryParams / OperationLogItem。
# 角色约定：role 1学生/2教师/3专家/4管理员；超管=role4 且 college_id 空，
#           学院管理员=role4 且 college_id 有值。
# ====================================================================
"""
用户管理模块 Pydantic v2 数据校验模型
分为请求模型（Create/Update/Query）和响应模型（Response/List）

==== 全链路统一校验规则（毕设级严谨，前后端 regex 一字不差）====
  密码  : r"^\\d{6}$"            —— 严格6位纯数字，不多不少不含字母/符号
  手机号: r"^1[3-9]\\d{9}$"      —— 中国大陆11位手机号（首1、第二位3-9）
  邮箱  : EMAIL_PATTERN + max_length=128 —— 与前端 validators.ts 保持一字不差
"""
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.core.security import RoleEnum


# ====================================================================
# 统一正则常量（便于字段引用和跨端对齐）
# ====================================================================
# 密码：严格 6 位纯数字（历史初始化规则，登录接口不做此限制）
PASSWORD_PATTERN = r"^\d{6}$"
# 手机号：中国大陆 11 位，首位 1、次位 3-9
PHONE_PATTERN = r"^1[3-9]\d{9}$"
# 与 frontend/src/utils/validators.ts 的 EMAIL_REGEX 保持一致，避免"前端过、后端422"
EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,16}$"


# ====================================================================
# 学院相关模型
# ====================================================================
class CollegeBase(BaseModel):
    """学院公共字段：编码/名称必填，状态仅 0停用/1启用"""
    # 学院编码：与教务编码一致
    college_code: str = Field(..., max_length=32, description="学院编码")
    # 学院名称
    college_name: str = Field(..., max_length=128, description="学院名称")
    # 院长用户ID：展示用，不参与权限
    dean_id: Optional[int] = Field(default=None, description="院长ID")
    # 排序序号：非负，越小越靠前
    sort_order: int = Field(default=0, ge=0, description="排序序号")
    # 状态 0-停用 1-启用
    status: int = Field(default=1, ge=0, le=1, description="状态 0-停用 1-启用")


class CollegeCreate(CollegeBase):
    """新增学院请求模型：字段全部继承 Base"""
    pass


class CollegeUpdate(BaseModel):
    """更新学院请求模型（全部可选，支持部分更新）"""
    college_code: Optional[str] = Field(default=None, max_length=32)
    college_name: Optional[str] = Field(default=None, max_length=128)
    dean_id: Optional[int] = None
    sort_order: Optional[int] = None
    status: Optional[int] = Field(default=None, ge=0, le=1)


class CollegeResponse(CollegeBase):
    """学院响应模型：由 ORM 对象转换，附带主键与创建时间"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ====================================================================
# 登录与认证相关模型
# ====================================================================
class LoginRequest(BaseModel):
    """用户登录请求 — 登录不限制密码格式（兼容历史用户密码如 admin123），由认证逻辑校验正确性"""
    # 账号支持用户名/学号/工号/手机号/邮箱，长度 2~64
    username: str = Field(..., min_length=2, max_length=64, description="登录账号（用户名/学号/手机号/邮箱均可）")
    # 密码仅校验非空与长度，避免历史密码因格式规则被 422 拦截
    password: str = Field(..., min_length=1, max_length=128, description="登录密码")


class LoginResponse(BaseModel):
    """登录响应：双 Token + 用户基本信息（access 短期、refresh 长期，登出时一并吊销）"""
    access_token: str = Field(..., description="访问令牌(短期)")
    refresh_token: str = Field(..., description="刷新令牌(长期)")
    token_type: str = Field(default="bearer")
    # 过期秒数：前端据此提前刷新
    expires_in: int = Field(..., description="访问令牌过期秒数")
    # 用户信息中不含密码等敏感字段
    user_info: "UserInfo"


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求：用长期令牌换取新的短期访问令牌"""
    refresh_token: str = Field(..., description="刷新令牌")


class LogoutRequest(BaseModel):
    """[P1-8] 登出请求：前端本地缓存的 refresh_token 一起吊销（可空）
    - refresh_token 可为空：仅从 Authorization 头中提取的 access_token 也能单独加入黑名单，
      避免前端忘记带 refresh_token 或本地已清理时，登出接口直接 422 报错失效。"""
    refresh_token: Optional[str] = Field(default=None, description="刷新令牌(可选，若提供则一并吊销)")


# ====================================================================
# 用户核心模型
# ====================================================================
class UserBase(BaseModel):
    """用户公共字段：账号/姓名/角色必填；邮箱手机号按统一正则校验"""
    # 登录账号：2~64 位，学号/工号
    username: str = Field(..., min_length=2, max_length=64, description="登录账号/学号/工号")
    # 真实姓名
    real_name: str = Field(..., min_length=1, max_length=64, description="真实姓名")
    # 邮箱：正则与前端一致；留空串由 _blank_to_none 归一为 None
    email: Optional[str] = Field(default=None, max_length=128, pattern=EMAIL_PATTERN, description="邮箱")
    # 手机号：11 位中国大陆格式
    phone: Optional[str] = Field(default=None, pattern=PHONE_PATTERN, min_length=11, max_length=11, description="手机号(11位)")
    # 角色: 1-学生 2-教师 3-专家 4-管理员
    role: int = Field(..., ge=1, le=4, description="角色: 1-学生 2-教师 3-专家 4-管理员")
    # 所属学院：管理员为空即超管，有值即学院管理员
    college_id: Optional[int] = Field(default=None, description="所属学院ID")
    # 头像：URL 或 base64
    avatar: Optional[str] = Field(default=None, description="头像URL或base64")
    # 状态 0-禁用 1-启用
    status: int = Field(default=1, ge=0, le=1, description="状态 0-禁用 1-启用")

    @field_validator("email", "phone", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        """前端表单留空时传空串，需归一为 None，否则会触发格式校验 422"""
        return None if isinstance(v, str) and v.strip() == "" else v


class UserCreate(UserBase):
    """创建用户请求 — 初始密码强制6位纯数字"""
    # 初始密码：6 位纯数字，由管理员设置，首次登录会要求改密
    password: str = Field(..., pattern=PASSWORD_PATTERN, min_length=6, max_length=6, description="初始密码（6位纯数字）")


class UserUpdate(BaseModel):
    """管理员更新用户信息
    - password 非空则重置，必须6位纯数字
    - phone 非空必须符合11位中国大陆格式"""
    # 以下字段均为可选：传 null 表示不修改
    real_name: Optional[str] = Field(default=None, max_length=64)
    email: Optional[str] = Field(default=None, max_length=128, pattern=EMAIL_PATTERN)
    phone: Optional[str] = Field(default=None, pattern=PHONE_PATTERN, min_length=11, max_length=11)
    # 角色/学院变更会影响数据权限，需管理员操作
    role: Optional[int] = Field(default=None, ge=1, le=4)
    college_id: Optional[int] = None
    avatar: Optional[str] = Field(default=None, description="头像URL或base64")
    # 状态 0-禁用 1-启用
    status: Optional[int] = Field(default=None, ge=0, le=1)
    # 重置密码：非空才生效，重置后 force_change_pwd 置 1
    password: Optional[str] = Field(default=None, pattern=PASSWORD_PATTERN, min_length=6, max_length=6, description="非空则重置密码（6位纯数字）")

    @field_validator("email", "phone", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return None if isinstance(v, str) and v.strip() == "" else v


class UserProfileUpdate(BaseModel):
    """用户自助更新个人信息
    - 修改密码：必须同时提供 old_password + new_password，new_password 6位纯数字
    - 手机号、邮箱严格格式"""
    # 可自助修改的资料字段（角色/学院不在此列，避免越权）
    real_name: Optional[str] = Field(default=None, max_length=64)
    email: Optional[str] = Field(default=None, max_length=128, pattern=EMAIL_PATTERN)
    phone: Optional[str] = Field(default=None, pattern=PHONE_PATTERN, min_length=11, max_length=11)
    avatar: Optional[str] = Field(default=None, description="头像URL或base64")
    # 改密必须成对提交，仅传 new_password 会被校验器拦截
    old_password: Optional[str] = Field(default=None, pattern=PASSWORD_PATTERN, min_length=6, max_length=6, description="修改密码时需提供原密码（6位纯数字）")
    new_password: Optional[str] = Field(default=None, pattern=PASSWORD_PATTERN, min_length=6, max_length=6, description="新密码（6位纯数字）")

    @field_validator("email", "phone", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return None if isinstance(v, str) and v.strip() == "" else v

    @field_validator("new_password")
    @classmethod
    def _check_old_password(cls, v, values):
        if v and not values.data.get("old_password"):
            raise ValueError("修改密码必须同时提供原密码(old_password)")
        return v


class UserInfo(BaseModel):
    """用户基本信息响应（登录后返回，不含敏感字段；role_name/college_name 由业务层赋值）"""
    model_config = ConfigDict(from_attributes=True)

    # 主键与账号基本信息
    id: int
    username: str
    real_name: str
    email: Optional[str]
    phone: Optional[str]
    # 角色与文案：role_name 用于前端菜单/按钮渲染
    role: int
    role_name: str = ""  # 由业务层赋值
    # 学院信息：college_name 需 Service 关联查询后回填
    college_id: Optional[int]
    college_name: Optional[str] = None  # 关联查询后赋值
    # 学生专属展示字段
    grade: Optional[str] = None  # 年级（仅学生有值，如 2023）
    major: Optional[str] = None  # 专业（仅学生有值）
    # 学校名称：系统管理员无学院时用该字段展示归属
    school_name: str = ""  # 学校名称（系统管理员无学院时显示）
    avatar: Optional[str]
    # 状态与安全标志：force_change_pwd=1 时前端强制跳改密页
    status: int
    force_change_pwd: int = 0  # 首次登录强制改密标志
    last_login_at: Optional[datetime]
    created_at: datetime


class UserListItem(UserInfo):
    """用户列表项响应（管理员/教师使用，包含完整PII字段）"""
    # 更新时间：列表展示与增量同步
    updated_at: datetime


class UserSafeListItem(BaseModel):
    """
    脱敏的用户列表项响应（学生端调用用户查询接口时返回）
    仅保留用于"选人"的必要字段，隐藏邮箱/手机/状态/登录信息等PII
    """
    model_config = ConfigDict(from_attributes=True)

    # 选人所需最小集合：id/账号/姓名/角色/学院/年级/专业/头像
    id: int
    username: str
    real_name: str
    role: int
    role_name: str = ""
    college_id: Optional[int]
    college_name: Optional[str] = None
    grade: Optional[str] = None  # 年级（选团队成员时用于自动填充）
    major: Optional[str] = None  # 专业（选团队成员时用于自动填充）
    avatar: Optional[str]


# ====================================================================
# 查询 / 批量操作模型
# ====================================================================
class UserQueryParams(BaseModel):
    """用户列表查询参数：全部可选，学院管理员由 Service 强制追加本院过滤"""
    # 关键词：账号/姓名/邮箱模糊匹配
    keyword: Optional[str] = Field(default=None, max_length=64, description="关键词(账号/姓名/邮箱)")
    # 角色 1-4 / 学院 / 状态
    role: Optional[int] = Field(default=None, ge=1, le=4, description="角色过滤")
    college_id: Optional[int] = Field(default=None, description="学院过滤")
    status: Optional[int] = Field(default=None, ge=0, le=1)


class UserBatchCreateRequest(BaseModel):
    """批量创建用户（Excel导入后调用）"""
    # 一次最多 500 条，防止大事务拖垮数据库
    users: List[UserCreate] = Field(..., max_length=500, description="用户列表")


class UserBatchDeleteRequest(BaseModel):
    """批量删除用户：上限 500，至少 1 条"""
    user_ids: List[int] = Field(..., min_length=1, max_length=500)


class UserBatchStatusRequest(BaseModel):
    """批量启/禁用用户：status 0-禁用 1-启用"""
    user_ids: List[int] = Field(..., min_length=1, max_length=500)
    status: int = Field(..., ge=0, le=1)


class ImportResultResponse(BaseModel):
    """Excel批量导入结果：逐行错误信息回显，便于用户修正后重传"""
    # 总行数 / 成功数 / 失败数
    total: int
    success: int
    failed: int
    # 错误明细：如 "第3行：手机号格式不正确"
    errors: List[str] = Field(default_factory=list)


# ====================================================================
# 操作日志响应模型
# ====================================================================
class OperationLogQueryParams(BaseModel):
    """操作日志查询参数：既支持单值筛选，也支持前端多选（逗号分隔）批量筛选"""
    # 关键词：操作描述/账号/姓名模糊匹配
    keyword: Optional[str] = None
    # 单值筛选
    module_name: Optional[str] = None
    operation_type: Optional[str] = None
    user_id: Optional[int] = None
    # 时间区间：按 operation_time 过滤
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    # 高级筛选（前端多选，逗号分隔）
    modules: Optional[str] = Field(default=None, description="模块名多选，逗号分隔")
    operation_types: Optional[str] = Field(default=None, description="操作类型多选，逗号分隔")
    user_roles: Optional[str] = Field(default=None, description="操作人角色多选，逗号分隔")
    statuses: Optional[str] = Field(default=None, description="结果多选(success/fail)，逗号分隔")


class OperationLogItem(BaseModel):
    """操作日志列表项响应：只读字段，不允许前端回写"""
    model_config = ConfigDict(from_attributes=True)

    # 日志主键与操作人快照
    id: int
    user_id: Optional[int]
    username: Optional[str]
    real_name: Optional[str]
    user_role: Optional[int]
    # 操作分类与描述
    operation_type: str
    module_name: str
    operation_desc: Optional[str]
    # 请求上下文
    request_method: Optional[str]
    request_url: Optional[str]
    response_code: Optional[int]
    # 客户端与耗时
    ip_address: Optional[str]
    cost_time: Optional[int]
    operation_time: datetime


# 让LoginResponse.user_info引用生效
LoginResponse.model_rebuild()
