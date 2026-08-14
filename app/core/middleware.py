"""
FastAPI中间件模块
实现：操作日志审计中间件、跨域CORS、请求耗时统计等
"""
import time
import json
import logging
from typing import Optional, Callable
from fastapi import Request, FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.database.session import SessionLocal
from app.models import SysOperationLog

# 日志记录器
logger = logging.getLogger(__name__)


# 需要记录操作日志的URL前缀（只记录API请求，跳过静态资源和文档）
LOG_API_PREFIXES = ("/api/",)
# 不记录日志的路径（如健康检查、文件下载等）
SKIP_LOG_PATHS = {"/api/health", "/docs", "/redoc", "/openapi.json", "/static/"}
# 请求体过大时不记录原始body（防内存溢出）
MAX_LOG_BODY_SIZE = 100 * 1024  # 100KB


def _extract_ip(request: Request) -> str:
    """从请求中获取真实客户端IP（考虑反向代理场景）"""
    # 常见反向代理头
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else ""


def _path_should_log(path: str) -> bool:
    """判断请求路径是否需要记录操作日志"""
    for skip in SKIP_LOG_PATHS:
        if path.startswith(skip):
            return False
    for prefix in LOG_API_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


class OperationLogMiddleware(BaseHTTPMiddleware):
    """
    操作日志审计中间件
    自动记录所有API请求的操作人、角色、IP、方法、URL、参数、耗时等
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过不需要记录的请求
        if not _path_should_log(request.url.path):
            return await call_next(request)

        start_time = time.time()
        # ========== 读取请求体（注意：body流只能读一次，需要重新包装）==========
        request_body_bytes = b""
        try:
            body = await request.body()
            if len(body) <= MAX_LOG_BODY_SIZE:
                request_body_bytes = body
        except Exception:
            pass

        # 重新构造Request，让后续路由仍可读取body
        async def receive():
            return {"type": "http.request", "body": request_body_bytes, "more_body": False}
        new_request = Request(request.scope, receive=receive)

        # 执行请求
        response = await call_next(new_request)
        cost_ms = int((time.time() - start_time) * 1000)

        # ========== 异步写入日志（使用独立DB会话，避免阻塞请求链路）==========
        try:
            db = SessionLocal()
            try:
                log = SysOperationLog()
                # 请求基本信息
                log.request_method = request.method
                log.request_url = str(request.url.path)
                if request.query_params:
                    log.request_url += "?" + str(request.query_params)
                log.ip_address = _extract_ip(request)
                log.user_agent = request.headers.get("User-Agent", "")[:500]
                log.cost_time = cost_ms
                log.response_code = response.status_code

                # 请求参数：合并 query params + body
                params_dict = {}
                if request.query_params:
                    params_dict["query"] = dict(request.query_params)
                if request_body_bytes:
                    content_type = request.headers.get("Content-Type", "")
                    try:
                        if "application/json" in content_type:
                            params_dict["body"] = json.loads(request_body_bytes.decode("utf-8"))
                        elif "form" in content_type or "multipart" in content_type:
                            params_dict["body"] = "[FORM_DATA]"  # 文件上传等不记录具体内容
                        else:
                            text = request_body_bytes.decode("utf-8")[:500]
                            params_dict["body"] = text
                    except Exception:
                        params_dict["body_raw"] = f"[UNPARSED_BODY, len={len(request_body_bytes)}]"
                if params_dict:
                    try:
                        log.request_params = json.dumps(params_dict, ensure_ascii=False)[:5000]
                    except Exception:
                        log.request_params = "[UNSERIALIZABLE_PARAMS]"

                # 模块名 / 操作类型：根据URL路径推断
                path_parts = [p for p in request.url.path.split("/") if p]
                if len(path_parts) >= 3:
                    log.module_name = path_parts[2]  # /api/{module}/...
                else:
                    log.module_name = "unknown"
                method_map = {"GET": "query", "POST": "create", "PUT": "update",
                              "DELETE": "delete", "PATCH": "patch"}
                log.operation_type = method_map.get(request.method, request.method.lower())

                # 操作人信息：从response自定义header中取（由路由层写入）
                # 这样无需在此解析JWT，避免重复验证
                log.user_id = int(response.headers.get("X-Log-User-Id", 0) or 0) or None
                log.username = response.headers.get("X-Log-Username", "")[:64] or None
                log.real_name = response.headers.get("X-Log-RealName", "")[:64] or None
                role_str = response.headers.get("X-Log-Role")
                log.user_role = int(role_str) if role_str else None
                log.operation_desc = (response.headers.get("X-Log-Desc", "")[:500]) or None

                db.add(log)
                db.commit()
            except Exception as log_exc:
                db.rollback()
                logger.error(f"写入操作日志失败: {log_exc}")
            finally:
                db.close()
        except Exception as outer_exc:
            logger.error(f"操作日志中间件异常: {outer_exc}")

        # 清除临时响应头（不返回给客户端）
        del_headers = ["X-Log-User-Id", "X-Log-Username", "X-Log-RealName",
                       "X-Log-Role", "X-Log-Desc"]
        for h in del_headers:
            if h in response.headers:
                del response.headers[h]

        return response


def register_middlewares(app: FastAPI) -> None:
    """为FastAPI应用注册所有中间件（在main.py调用）"""

    # 1. CORS 跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],           # 开发环境放行所有，生产环境配置具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],  # 允许前端获取下载文件名
    )

    # 2. 操作日志审计中间件（自定义）
    app.add_middleware(OperationLogMiddleware)
