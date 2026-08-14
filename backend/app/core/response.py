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
    统一API响应模型
    格式：{ code, message, data, timestamp }
    """
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S")})

    code: int = Field(default=200, description="响应状态码: 200-成功 4xx-客户端错误 5xx-服务端错误")
    message: str = Field(default="success", description="响应消息描述")
    data: Optional[T] = Field(default=None, description="响应数据载体")
    timestamp: datetime = Field(default_factory=datetime.now, description="服务器响应时间戳")


class PageResult(BaseModel, Generic[T]):
    """
    分页查询结果模型
    用于封装列表接口的分页数据
    """
    items: List[T] = Field(default_factory=list, description="当前页数据列表")
    total: int = Field(default=0, description="总记录数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=10, description="每页大小")
    total_pages: int = Field(default=0, description="总页数")

    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int) -> "PageResult[T]":
        """工厂方法：快速创建分页结果"""
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )


# ========== 便捷响应函数 ==========

def success(data: Any = None, message: str = "操作成功") -> ResponseModel:
    """成功响应快捷方法"""
    return ResponseModel(code=200, message=message, data=data)


def created(data: Any = None, message: str = "创建成功") -> ResponseModel:
    """资源创建成功响应"""
    return ResponseModel(code=201, message=message, data=data)


def bad_request(message: str = "请求参数错误", data: Any = None) -> ResponseModel:
    """客户端请求错误响应"""
    return ResponseModel(code=400, message=message, data=data)


def unauthorized(message: str = "未授权，请先登录", data: Any = None) -> ResponseModel:
    """未授权响应"""
    return ResponseModel(code=401, message=message, data=data)


def forbidden(message: str = "无权限访问该资源", data: Any = None) -> ResponseModel:
    """禁止访问响应"""
    return ResponseModel(code=403, message=message, data=data)


def not_found(message: str = "资源不存在", data: Any = None) -> ResponseModel:
    """资源不存在响应"""
    return ResponseModel(code=404, message=message, data=data)


def server_error(message: str = "服务器内部错误", data: Any = None) -> ResponseModel:
    """服务端错误响应"""
    return ResponseModel(code=500, message=message, data=data)
