# ====================================================================
# 统一响应封装模块（app/core/response.py）
# --------------------------------------------------------------------
# 解决什么问题：
#   约定全平台所有接口（含异常）返回同一结构，前端只需写一套解析逻辑。
# 被谁使用：
#   几乎全部 router 的返回值、services 的返回封装、exceptions 的异常处理。
# 响应结构：
#   { "code": 200, "message": "success", "data": ..., "timestamp": "..." }
# 前端消费方式：
#   axios 响应拦截器先看 HTTP 层是否成功，再看 body.code：
#     - 200/201：直接取 data；
#     - 401：清理 token 并跳登录；
#     - 其他：用 message 弹出错误提示，必要时读取 data 做字段级展示。
# 关键约束：
#   1. code 是业务码，不一定等于 HTTP 状态码（业务异常 HTTP 仍为 200）；
#   2. data 为泛型，既可以是对象/列表，也可以是 None；
#   3. 时间统一序列化为 "YYYY-mm-dd HH:mm:ss"，前端无需再做时区处理。
# ====================================================================
"""
统一响应封装模块
定义所有API的标准化响应格式，保证前端解析一致性
"""
from typing import Generic, TypeVar, Optional, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# 泛型类型变量，用于响应data字段
T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    """
    统一 API 响应模型。

    格式：{ code, message, data, timestamp }
    参数：
        code：业务结果码，默认 200；4xx/5xx 语义与 HTTP 一致但走 body。
        message：给用户看的提示文案，成功时为 success。
        data：响应数据载体，类型由各接口的泛型参数决定。
        timestamp：服务器生成响应的时间，用于排查时序问题。
    """

    # datetime 统一格式化，避免 pydantic 默认输出 ISO 带 T 的格式导致前端显示不一致
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S")})

    code: int = Field(default=200, description="响应状态码: 200-成功 4xx-客户端错误 5xx-服务端错误")
    message: str = Field(default="success", description="响应消息描述")
    data: Optional[T] = Field(default=None, description="响应数据载体")
    timestamp: datetime = Field(default_factory=datetime.now, description="服务器响应时间戳")


class PageResult(BaseModel, Generic[T]):
    """
    分页查询结果模型。

    用于封装列表接口的分页数据，前端表格组件直接绑定 items/total 即可。
    参数：
        items：当前页数据列表。
        total：满足条件的总记录数（不是当前页数量）。
        page：当前页码（从 1 开始）。
        page_size：每页大小，与请求参数一致（已归一化）。
        total_pages：总页数，由 create 计算，供分页器展示。
    """

    items: List[T] = Field(default_factory=list, description="当前页数据列表")
    total: int = Field(default=0, description="总记录数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=10, description="每页大小")
    total_pages: int = Field(default=0, description="总页数")

    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int) -> "PageResult[T]":
        """
        工厂方法：快速创建分页结果。

        参数：
            items：当前页数据。
            total：总记录数。
            page：当前页码。
            page_size：每页大小。
        返回：
            填充好 total_pages 的 PageResult 实例。
        说明：
            total_pages 采用向上取整公式；page_size<=0 时置 0，避免除零异常。
        """
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )


# ========== 便捷响应函数 ==========
# 说明：这些函数只构造 ResponseModel，不负责设置 HTTP 状态码；
# 正常返回时由 FastAPI 默认 200，创建类接口如需 201 由路由显式声明。

def success(data: Any = None, message: str = "操作成功") -> ResponseModel:
    """
    成功响应快捷方法。

    参数：
        data：业务数据，列表/对象/None 均可。
        message：提示文案，默认“操作成功”。
    返回：
        code=200 的 ResponseModel。
    """
    return ResponseModel(code=200, message=message, data=data)


def created(data: Any = None, message: str = "创建成功") -> ResponseModel:
    """资源创建成功响应（code=201），用于新建项目/用户/公告等接口。"""
    return ResponseModel(code=201, message=message, data=data)


def bad_request(message: str = "请求参数错误", data: Any = None) -> ResponseModel:
    """客户端请求错误响应（code=400），用于业务参数不合法但未抛异常的场景。"""
    return ResponseModel(code=400, message=message, data=data)


def unauthorized(message: str = "未授权，请先登录", data: Any = None) -> ResponseModel:
    """未授权响应（code=401），前端收到后应跳转登录页。"""
    return ResponseModel(code=401, message=message, data=data)


def forbidden(message: str = "无权限访问该资源", data: Any = None) -> ResponseModel:
    """禁止访问响应（code=403），用于明确告知用户权限不足。"""
    return ResponseModel(code=403, message=message, data=data)


def not_found(message: str = "资源不存在", data: Any = None) -> ResponseModel:
    """资源不存在响应（code=404）。"""
    return ResponseModel(code=404, message=message, data=data)


def server_error(message: str = "服务器内部错误", data: Any = None) -> ResponseModel:
    """服务端错误响应（code=500），生产环境不应把内部异常细节放入 message。"""
    return ResponseModel(code=500, message=message, data=data)
