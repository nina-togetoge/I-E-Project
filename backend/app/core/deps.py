"""
通用依赖注入模块
封装路由层中常用的依赖：分页参数、数据权限范围、操作上下文等
"""
from typing import Optional, Dict, Any
from fastapi import Request, Depends, Response
from sqlalchemy.orm import Session

from app.core.security import RoleEnum, get_current_user, ROLE_NAME_MAP
from app.database.session import get_db
from app.models import SysUser


# ====================================================================
# 通用分页参数依赖
# ====================================================================
class PaginationParams:
    """
    分页查询参数依赖
    使用：async def list_xxx(p: PaginationParams = Depends())
    """

    def __init__(self, page: int = 1, page_size: int = 10, order_by: Optional[str] = None, order_dir: str = "desc"):
        self.page = max(1, page)                                    # 最小第1页
        self.page_size = min(max(1, page_size), 500)                # 1~500，防拉爆
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
    操作上下文依赖
    在路由函数中获取并设置操作描述、响应时将用户信息写入响应头
    供操作日志中间件读取（避免重复解析JWT）
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
        """设置操作描述（会被记录到操作日志）"""
        self.desc = desc
        # 实时写入响应头，中间件后续读取
        self.response.headers["X-Log-Desc"] = desc

    def __enter__(self):
        # 将当前用户信息写入响应头（中间件读取用）
        if self.current_user:
            self.response.headers["X-Log-User-Id"] = str(self.current_user.id)
            self.response.headers["X-Log-Username"] = self.current_user.username
            self.response.headers["X-Log-RealName"] = self.current_user.real_name
            self.response.headers["X-Log-Role"] = str(self.current_user.role)
            self.response.headers["X-Log-Desc"] = self.desc
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False  # 不抑制异常


# ====================================================================
# 数据权限范围：基于角色确定用户可以看到哪些学院的数据
# ====================================================================
class DataScope:
    """
    行级数据权限计算依赖
    返回：{ college_ids: [..], leader_user_ids: [..] } 供业务层拼接过滤条件
    规则：
      - 系统管理员(4)：所有数据
      - 学院管理员/院领导（非学生/非专家的本院用户）：仅本院数据
      - 指导教师(2)：仅自己指导的项目 + 本院数据
      - 学生(1)：仅自己负责/参与的项目
      - 评审专家(3)：仅分配给其评审的项目
    """

    def __init__(self, current_user: SysUser = Depends(get_current_user), db: Session = Depends(get_db)):
        self.user = current_user
        self.db = db
        self.role = current_user.role
        self.college_id = current_user.college_id
        self.user_id = current_user.id

        # 计算权限范围（业务层按需要求）
        self.scope: Dict[str, Any] = self._compute_scope()

    def _compute_scope(self) -> Dict[str, Any]:
        if self.role == RoleEnum.ADMIN:
            # 全部数据
            return {"all": True, "college_ids": None, "owner_user_ids": None}

        if self.role == RoleEnum.STUDENT:
            # 仅自己是负责人或团队成员的数据
            return {
                "all": False,
                "owner_user_ids": [self.user_id],  # 仅负责人过滤，团队成员需业务层自行JOIN team表
                "college_ids": None,
                "is_student": True,
            }

        if self.role == RoleEnum.TEACHER:
            # 指导教师：看自己指导的项目 + 本院项目列表（可配置）
            return {
                "all": False,
                "college_ids": [self.college_id] if self.college_id else None,
                "teacher_user_ids": [self.user_id],
                "owner_user_ids": None,
            }

        if self.role == RoleEnum.EXPERT:
            # 专家：需要通过 proj_review 表反查（由业务层处理）
            return {
                "all": False,
                "expert_user_id": self.user_id,
                "college_ids": None,
            }

        # 兜底：仅本人
        return {"all": False, "owner_user_ids": [self.user_id], "college_ids": None}

    def check_college(self, data_college_id: Optional[int]) -> bool:
        """便捷方法：判断当前用户是否有权访问某学院的数据"""
        if self.scope.get("all"):
            return True
        allowed_colleges = self.scope.get("college_ids") or []
        if allowed_colleges and data_college_id and data_college_id in allowed_colleges:
            return True
        return False
