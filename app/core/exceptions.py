"""
全局自定义异常与异常处理器模块
实现业务异常分层处理 + FastAPI全局异常拦截，统一返回标准响应格式
"""
from typing import Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.core.response import ResponseModel


# ====================================================================
# 自定义业务异常基类
# ====================================================================

class BizException(Exception):
    """业务逻辑异常基类，所有业务异常都应抛出此异常或其子类"""

    def __init__(self, code: int = 400, message: str = "业务异常", data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class AuthException(BizException):
    """认证异常：未登录、Token无效/过期等"""

    def __init__(self, message: str = "认证失败，请重新登录", data: Any = None):
        super().__init__(code=401, message=message, data=data)


class PermissionDeniedException(BizException):
    """权限异常：无权访问/操作资源"""

    def __init__(self, message: str = "无权限执行该操作", data: Any = None):
        super().__init__(code=403, message=message, data=data)


class ResourceNotFoundException(BizException):
    """资源不存在异常"""

    def __init__(self, message: str = "请求的资源不存在", data: Any = None):
        super().__init__(code=404, message=message, data=data)


class ParamValidateException(BizException):
    """参数校验异常（业务层面手动抛出）"""

    def __init__(self, message: str = "参数校验失败", data: Any = None):
        super().__init__(code=400, message=message, data=data)


class DataConflictException(BizException):
    """数据冲突异常：如唯一键冲突、状态不允许等"""

    def __init__(self, message: str = "数据冲突，操作失败", data: Any = None):
        super().__init__(code=409, message=message, data=data)


# ====================================================================
# 全局异常处理器注册辅助函数
# ====================================================================

def register_exception_handlers(app) -> None:
    """
    为FastAPI应用注册所有全局异常处理器
    在main.py中调用： register_exception_handlers(app)
    """

    # ---- 1. 自定义业务异常 ----
    @app.exception_handler(BizException)
    async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
        resp = ResponseModel(code=exc.code, message=exc.message, data=exc.data)
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    # ---- 2. Pydantic 参数校验异常 ----
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 格式化校验错误为易读消息
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(x) for x in err.get("loc", []) if x != "body")
            msg = err.get("msg", "未知错误")
            errors.append(f"{loc}: {msg}" if loc else msg)
        detail = "; ".join(errors) if errors else "参数格式不正确"

        resp = ResponseModel(
            code=422,
            message=f"请求参数校验失败: {detail}",
            data={"raw_errors": exc.errors()}
        )
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    # ---- 3. Starlette HTTP 异常 ----
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code_map = {
            status.HTTP_400_BAD_REQUEST: 400,
            status.HTTP_401_UNAUTHORIZED: 401,
            status.HTTP_403_FORBIDDEN: 403,
            status.HTTP_404_NOT_FOUND: 404,
            status.HTTP_405_METHOD_NOT_ALLOWED: 405,
            status.HTTP_429_TOO_MANY_REQUESTS: 429,
            status.HTTP_500_INTERNAL_SERVER_ERROR: 500,
        }
        code = code_map.get(exc.status_code, exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"

        resp = ResponseModel(code=code, message=message)
        # 404/405 等用真实的HTTP状态码返回更规范
        http_status = exc.status_code if exc.status_code in (404, 405) else 200
        return JSONResponse(status_code=http_status, content=resp.model_dump(mode="json"))

    # ---- 4. 数据库唯一约束冲突 ----
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        msg = "数据操作冲突，可能存在重复记录或违反外键约束"
        err_text = str(exc.orig).lower()
        if "duplicate" in err_text:
            msg = "数据已存在，请检查唯一字段（如用户名、编号等）"
        elif "foreign key" in err_text:
            msg = "关联数据不存在或被引用，无法执行操作"

        resp = ResponseModel(code=409, message=msg, data={"detail": str(exc.orig)})
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    # ---- 5. 数据库通用异常 ----
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        resp = ResponseModel(code=500, message="数据库操作异常，请稍后重试或联系管理员",
                             data={"detail": str(exc)})
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    # ---- 6. 兜底：所有未处理异常 ----
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # DEBUG 模式下可以返回详细堆栈，生产环境应仅返回通用错误
        import traceback
        detail = traceback.format_exc()
        # 同时写入日志（如有日志组件）
        print(f"[UNHANDLED EXCEPTION] {request.method} {request.url}\n{detail}")

        from app.core.config import settings
        if settings.DEBUG:
            resp = ResponseModel(code=500, message=f"服务器异常: {str(exc)}", data={"stack": detail})
        else:
            resp = ResponseModel(code=500, message="服务器内部错误，请稍后重试或联系管理员")
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))
