# ====================================================================
# 通用依赖注入模块（app/core/deps.py）
# --------------------------------------------------------------------
# 解决什么问题：
#   把多个路由都要用的“分页参数、操作日志上下文、数据权限范围”做成依赖，
#   路由函数只声明参数即可，避免每个接口重复解析与重复鉴权。
# 被谁使用：
#   各业务 router（列表接口用 PaginationParams，写接口用 OperationContext，
#   项目/成果/报销查询用 DataScope 收窄学院与归属）。
# 关键设计：
#   1. DataScope 只定义“行级可见范围”的数据结构，不直接拼 SQL；
#      具体过滤条件由 service 层按返回字段组装，保持权限逻辑集中可审。
#   2. 管理员必须区分超管（college_id 为空）与学院管理员（有 college_id），
#      否则学院管理员会看到全校数据。
#   3. 操作上下文通过响应头把用户信息传给中间件，避免中间件重复解析 JWT/查库。
# ====================================================================
"""
通用依赖注入模块
封装路由层中常用的依赖：分页参数、数据权限范围、操作上下文等
"""
from typing import Optional, Dict, Any
from urllib.parse import quote
from fastapi import Request, Depends, Response
from sqlalchemy.orm import Session

from app.core.security import RoleEnum, get_current_user, ROLE_NAME_MAP, is_super_admin, is_college_admin
from app.database.session import get_db
from app.models import SysUser


# ====================================================================
# 通用分页参数依赖
# ====================================================================
class PaginationParams:
    """
    分页查询参数依赖。

    使用：async def list_xxx(p: PaginationParams = Depends())
    参数：
        page：页码，从 1 开始，小于 1 会被纠正为 1。
        page_size：每页条数，限制在 1~200，防止恶意大分页拖垮数据库。
        order_by：排序字段名，由业务层白名单校验后再拼 SQL。
        order_dir：排序方向，仅 asc/desc，其他值一律按 desc。
    说明：
        这里只做参数归一化，不校验 order_by 是否合法；
        service 层必须把 order_by 映射到固定列，禁止直接拼接用户输入。
    """

    def __init__(self, page: int = 1, page_size: int = 10, order_by: Optional[str] = None, order_dir: str = "desc"):
        self.page = max(1, page)                                    # 最小第1页
        # [P1-7] 上限从 500 收紧到 200，进一步防止恶意大分页拉爆数据库
        self.page_size = min(max(1, page_size), 200)                # 1~200
        # offset/limit 直接供 SQLAlchemy 的 .offset()/.limit() 使用
        self.offset = (self.page - 1) * self.page_size
        self.limit = self.page_size
        self.order_by = order_by
        # 排序方向：只允许 asc/desc，防SQL注入
        self.order_dir = "asc" if order_dir and order_dir.lower() == "asc" else "desc"


# ====================================================================
# 操作上下文：用于路由层 -> 中间件传递操作人信息与操作描述
# ====================================================================
class OperationContext:
    """
    操作上下文依赖。

    在路由函数中获取并设置操作描述，同时把用户信息写入响应头，
    供操作日志中间件读取（避免中间件重复解析 JWT 与查询用户）。

    用法：
        def create_xxx(ctx: OperationContext = Depends()):
            with ctx:
                ...
                ctx.set_desc("创建项目：xxx")
    说明：
        支持上下文管理器写法；不设置 desc 时默认记录“方法 + 路径”。
    """

    def __init__(
        self,
        request: Request,
        response: Response,
        current_user: Optional[SysUser] = Depends(get_current_user),
    ):
        self.request = request
        self.response = response
        self.current_user = current_user
        # 默认操作描述 = 请求方法 + 路径
        self.desc = f"{request.method} {request.url.path}"

    def set_desc(self, desc: str) -> None:
        """
        设置人类可读的操作描述（会被记录到操作日志）。

        参数：
            desc：如“审核通过项目 01”这类审计可读文案。
        副作用：
            立即写入响应头 X-Log-Desc；中文需 URL 编码，否则不符合 HTTP 头规范。
        """
        self.desc = desc
        # 实时写入响应头，中间件后续读取（URL编码中文以兼容HTTP头）
        self.response.headers["X-Log-Desc"] = quote(str(desc))

    def __enter__(self):
        """
        进入上下文时把当前用户信息写入临时响应头。

        返回：
            self，便于 with ... as ctx 使用。
        说明：
            只有已登录用户才写；real_name 为中文，同样需要 quote 编码。
        """
        # 将当前用户信息写入响应头（中间件读取用）
        if self.current_user:
            self.response.headers["X-Log-User-Id"] = str(self.current_user.id)
            self.response.headers["X-Log-Username"] = self.current_user.username
            self.response.headers["X-Log-RealName"] = quote(str(self.current_user.real_name))
            self.response.headers["X-Log-Role"] = str(self.current_user.role)
            self.response.headers["X-Log-Desc"] = quote(str(self.desc))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        退出上下文。

        返回：
            False 表示不抑制异常，业务异常继续向上抛给全局异常处理器。
        """
        return False  # 不抑制异常


# ====================================================================
# 数据权限范围：基于角色确定用户可以看到哪些学院的数据
# ====================================================================
class DataScope:
    """
    行级数据权限计算依赖
    返回：{ college_ids: [..], leader_user_ids: [..] } 供业务层拼接过滤条件
    规则（⚠️ ADMIN 分级：修复学院管理员越权看到全校数据的 Bug）：
      - 真·超级管理员(role=4 且 college_id 为空)：所有数据  all=True
      - 学院管理员(role=4 且 college_id 非空)：     仅本院数据
      - 指导教师(2)：                               仅自己指导的项目 + 本院数据
      - 学生(1)：                                   仅自己负责/参与的项目
      - 评审专家(3)：                               仅分配给其评审的项目
    """

    def __init__(self, current_user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
        """
        初始化数据权限范围。

        参数：
            current_user：已登录用户（由 get_current_user 注入）。
            db：请求级会话，预留给需要反查团队/评审表时使用。
        副作用：
            构造时即计算 scope，路由拿到的对象已包含可见范围。
        """
        self.user = current_user
        self.db = db
        self.role = current_user.role
        self.college_id = current_user.college_id
        self.user_id = current_user.id

        # 计算权限范围（业务层按需要求）
        self.scope: Dict[str, Any] = self._compute_scope()

    def _compute_scope(self) -> Dict[str, Any]:
        """
        按角色计算行级可见范围。

        返回：
            字典，可能包含：
              all：True 表示不限学院/归属（仅超管）；
              college_ids：允许访问的学院 ID 列表；
              owner_user_ids：允许访问的项目负责人 ID 列表；
              teacher_user_ids：教师本人 ID（业务层用于“指导的项目”）；
              expert_user_id：专家本人 ID（业务层反查 proj_review）；
              is_student / is_college_admin：角色标记，供业务层做额外限制。
        说明：
            返回的是“可用过滤维度”，不是完整 SQL；service 层必须至少使用
            其中一个维度，否则等于没加权限。
        """
        # ---- ADMIN 分级判断（本次修复核心）----
        # 1. 管理员必须先区分超管/学院管理员，不能一律 all=True
        if self.role == RoleEnum.ADMIN:
            if is_super_admin(self):
                # 真超级管理员（role=4 + 无学院归属）→ 全校所有数据
                return {"all": True, "college_ids": None, "owner_user_ids": None}
            # 学院管理员（role=4 + 绑定具体college_id）→ 仅本院
            return {
                "all": False,
                "college_ids": [self.college_id] if self.college_id else None,
                "owner_user_ids": None,
                "is_college_admin": True,  # 业务层按需使用（如不能创建ADMIN）
            }

        # 2. 学生：只能看自己负责的项目；团队成员身份需业务层 JOIN proj_team_member
        if self.role == RoleEnum.STUDENT:
            # 仅自己是负责人或团队成员的数据
            return {
                "all": False,
                "owner_user_ids": [self.user_id],  # 仅负责人过滤，团队成员需业务层自行JOIN team表
                "college_ids": None,
                "is_student": True,
            }

        # 3. 教师：指导的项目 + 本院项目，两种维度由业务层选择使用
        if self.role == RoleEnum.TEACHER:
            # 指导教师：看自己指导的项目 + 本院项目列表（可配置）
            return {
                "all": False,
                "college_ids": [self.college_id] if self.college_id else None,
                "teacher_user_ids": [self.user_id],
                "owner_user_ids": None,
            }

        # 4. 专家：只允许评审被分配的项目，需通过 proj_review 反查项目ID
        if self.role == RoleEnum.EXPERT:
            # 专家：需要通过 proj_review 表反查（由业务层处理）
            return {
                "all": False,
                "expert_user_id": self.user_id,
                "college_ids": None,
            }

        # 兜底：未知角色一律按“仅本人”处理，遵循最小权限原则
        return {"all": False, "owner_user_ids": [self.user_id], "college_ids": None}

    def check_college(self, data_college_id: Optional[int]) -> bool:
        """
        判断当前用户是否有权访问某学院的数据。

        参数：
            data_college_id：待访问数据所属学院 ID，可为空。
        返回：
            True 可访问，False 不可访问。
        说明：
            超管直接放行；学院管理员/教师需数据学院在自己的 college_ids 内；
            学生/专家通常 college_ids 为 None，调用本方法一般返回 False，
            应改用 owner_user_ids/expert_user_id 判断。
        """
        if self.scope.get("all"):
            return True
        allowed_colleges = self.scope.get("college_ids") or []
        if allowed_colleges and data_college_id and data_college_id in allowed_colleges:
            return True
        return False
