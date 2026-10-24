# ====================================================================
# 全局自定义异常与异常处理器模块（app/core/exceptions.py）
# --------------------------------------------------------------------
# 解决什么问题：
#   业务代码通过抛出 BizException 子类表达“可预期的失败”（未登录/无权/
#   资源不存在/状态冲突），由这里统一转换成前端可解析的标准响应体，
#   业务层不需要写 try/except 拼 JSONResponse。
# 被谁使用：
#   core.security 抛 AuthException/PermissionDeniedException，
#   services 抛 ParamValidateException/DataConflictException 等，
#   main.py 调用 register_exception_handlers(app) 完成注册。
# 关键设计：
#   1. 所有业务异常 HTTP 状态码统一返回 200，真正的结果码放在 body.code；
#      前端 axios 拦截器按 code 判断，避免 4xx 触发浏览器控制台报错。
#   2. 只有 404/405 保留真实 HTTP 状态码，便于网关/监控识别无效路由。
#   3. 参数校验错误只回传 loc/msg/type，剔除 ctx/input，防止异常对象无法序列化。
#   4. 兜底异常处理器在 DEBUG 下返回堆栈，生产只返回通用文案。
# ====================================================================
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
    """
    业务逻辑异常基类，所有业务异常都应抛出此异常或其子类。

    参数：
        code：业务结果码（200 成功、4xx 客户端、5xx 服务端），不是 HTTP 状态码。
        message：直接展示给用户的中文提示。
        data：可选的附加数据（如字段错误详情）。
    说明：
        兼容 BizException("提示消息") 的位置参数写法：首参为字符串时视为 message，
        避免 code 被赋成字符串导致响应模型校验失败。
    """

    def __init__(self, code: int = 400, message: str = "业务异常", data: Any = None):
        # 兼容 BizException("提示消息") 的位置参数写法：首参为字符串时视为 message，
        # 避免 code 被赋成字符串导致响应模型校验失败。
        if isinstance(code, str):
            message, code = code, 400
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class AuthException(BizException):
    """
    认证异常：未登录、Token 无效/过期、账号禁用等。

    统一使用 401 结果码，前端拦截器收到后清理本地令牌并跳转登录页。
    """

    def __init__(self, message: str = "认证失败，请重新登录", data: Any = None):
        super().__init__(code=401, message=message, data=data)


class PermissionDeniedException(BizException):
    """
    权限异常：已登录但角色/数据范围不允许访问或操作资源。

    使用 403 结果码；路由级由 RequireRole 抛出，行级由 service 校验后抛出。
    """

    def __init__(self, message: str = "无权限执行该操作", data: Any = None):
        super().__init__(code=403, message=message, data=data)


class ResourceNotFoundException(BizException):
    """资源不存在异常（404）：如项目 ID 被删除或不属于当前用户可见范围。"""

    def __init__(self, message: str = "请求的资源不存在", data: Any = None):
        super().__init__(code=404, message=message, data=data)


class ParamValidateException(BizException):
    """
    参数校验异常（400）：业务层面手动抛出。

    与 Pydantic 的 RequestValidationError 区别：后者是请求结构/类型错误，
    这里是“结构正确但业务上不合法”（如结束日期早于开始日期）。
    """

    def __init__(self, message: str = "参数校验失败", data: Any = None):
        super().__init__(code=400, message=message, data=data)


class DataConflictException(BizException):
    """
    数据冲突异常（409）：如唯一键冲突、项目状态不允许当前操作。

    典型场景：重复提交审核、在错误状态提交中期报告、预算超限等。
    """

    def __init__(self, message: str = "数据冲突，操作失败", data: Any = None):
        super().__init__(code=409, message=message, data=data)


# ====================================================================
# 全局异常处理器注册辅助函数
# ====================================================================

def register_exception_handlers(app) -> None:
    """
    为 FastAPI 应用注册所有全局异常处理器。

    参数：
        app：FastAPI 实例。
    说明：
        在 main.py 中调用： register_exception_handlers(app)
        注册顺序不影响匹配：FastAPI 按异常类型精确/就近匹配，
        子类处理器优先于父类（BizException 处理器不会吞掉下面的具体类型）。
    """

    # ---- 1. 自定义业务异常 ----
    # 业务异常统一 HTTP 200 + body.code，前端 axios 拦截器按 code 分流提示
    @app.exception_handler(BizException)
    async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
        resp = ResponseModel(code=exc.code, message=exc.message, data=exc.data)
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    # ---- 2. Pydantic 参数校验异常 ----
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 1. 把 Pydantic 的 loc/msg 拼成“字段 -> 原因”的可读中文提示
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(x) for x in err.get("loc", []) if x != "body")
            msg = err.get("msg", "未知错误")
            errors.append(f"{loc}: {msg}" if loc else msg)
        detail = "; ".join(errors) if errors else "参数格式不正确"

        # 仅保留可序列化字段（loc/msg/type），剔除 ctx/input 等可能含异常对象的原始值，
        # 否则 model_validator 抛出 ValueError 时 ctx 会携带异常实例导致序列化失败（500）。
        # 2. raw_errors 供前端表单逐字段标红使用
        raw_errors = [
            {
                "loc": [str(x) for x in err.get("loc", [])],
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]

        resp = ResponseModel(
            code=422,
            message=f"请求参数校验失败: {detail}",
            data={"raw_errors": raw_errors}
        )
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    # ---- 3. Starlette HTTP 异常 ----
    # 处理 FastAPI 自身/路由抛出的 HTTPException（如 404、405、429）
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # 1. 映射为统一业务码；未知状态码原样保留
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
    # 把 MySQL 原始英文报错翻译成用户能理解的中文，并返回 409
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        # 1. 按驱动返回的错误文本做粗分类；未命中时给通用冲突提示
        msg = "数据操作冲突，可能存在重复记录或违反外键约束"
        err_text = str(exc.orig).lower()
        if "duplicate" in err_text:
            msg = "数据已存在，请检查唯一字段（如用户名、编号等）"
        elif "foreign key" in err_text:
            msg = "关联数据不存在或被引用，无法执行操作"

        resp = ResponseModel(code=409, message=msg, data={"detail": str(exc.orig)})
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    # ---- 5. 数据库通用异常 ----
    # 连接失败/语法错误等非预期问题是服务端故障，返回 500，不暴露具体 SQL
    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        resp = ResponseModel(code=500, message="数据库操作异常，请稍后重试或联系管理员",
                             data={"detail": str(exc)})
        return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))

    # ---- 6. 兜底：所有未处理异常 ----
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        捕获未被上面任何处理器命中的异常，保证接口永远返回 JSON 而不是 HTML 500。

        参数：
            request：触发异常的请求，用于定位日志。
            exc：原始异常对象。
        返回：
            统一响应体；DEBUG 模式附带堆栈，生产环境隐藏细节。
        副作用：
            向标准输出打印完整堆栈，便于本地排查（生产建议接入结构化日志）。
        """
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
