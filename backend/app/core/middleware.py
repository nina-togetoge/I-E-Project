"""
FastAPI中间件模块
实现：操作日志审计中间件、跨域CORS、请求耗时统计等
"""
import asyncio
import time
import json
import logging
from urllib.parse import unquote
from typing import Optional, Callable, Dict, Any
from fastapi import Request, FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.database.session import SessionLocal
from app.models import SysOperationLog

# 日志记录器
logger = logging.getLogger(__name__)

# 后台任务引用集合（避免被GC）
_pending_log_tasks: set = set()


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


# ====================================================================
# [P1-3] 操作日志改为后台线程执行，不阻塞事件循环 & 响应返回
# ====================================================================
def _write_operation_log_sync(log_data: Dict[str, Any]) -> None:
    """独立线程中执行的同步写入函数（避免阻塞事件循环）"""
    db = SessionLocal()
    try:
        log = SysOperationLog(**log_data)
        db.add(log)
        db.commit()
    except Exception as log_exc:
        db.rollback()
        logger.error(f"写入操作日志失败: {log_exc}")
    finally:
        db.close()


async def _write_operation_log_async(log_data: Dict[str, Any]) -> None:
    """将同步的DB写操作 offload 到线程池，确保真·异步"""
    try:
        await asyncio.to_thread(_write_operation_log_sync, log_data)
    except Exception as outer_exc:
        logger.error(f"操作日志后台任务异常: {outer_exc}")


def _collect_log_data(
    request: Request,
    response: Response,
    request_body_bytes: bytes,
    cost_ms: int,
) -> Dict[str, Any]:
    """从请求/响应头抽取 SysOperationLog 字段字典（序列化后跨线程安全）"""
    data: Dict[str, Any] = {}
    # 请求基本信息
    data["request_method"] = request.method
    url = str(request.url.path)
    if request.query_params:
        url += "?" + str(request.query_params)
    data["request_url"] = url
    data["ip_address"] = _extract_ip(request)
    data["user_agent"] = (request.headers.get("User-Agent", "") or "")[:500]
    data["cost_time"] = cost_ms
    data["response_code"] = response.status_code

    # 请求参数：合并 query params + body
    params_dict: Dict[str, Any] = {}
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
            data["request_params"] = json.dumps(params_dict, ensure_ascii=False)[:5000]
        except Exception:
            data["request_params"] = "[UNSERIALIZABLE_PARAMS]"

    # 模块名 / 操作类型：根据URL路径推断
    path_parts = [p for p in request.url.path.split("/") if p]
    if len(path_parts) >= 3:
        data["module_name"] = path_parts[2]  # /api/{module}/...
    else:
        data["module_name"] = "unknown"
    method_map = {"GET": "query", "POST": "create", "PUT": "update",
                  "DELETE": "delete", "PATCH": "patch"}
    data["operation_type"] = method_map.get(request.method, request.method.lower())

    # 操作人信息：从response自定义header中取（由路由层写入）
    user_id_raw = response.headers.get("X-Log-User-Id", 0) or 0
    try:
        uid = int(user_id_raw)
        data["user_id"] = uid or None
    except (TypeError, ValueError):
        data["user_id"] = None
    data["username"] = (response.headers.get("X-Log-Username", "") or "")[:64] or None
    data["real_name"] = unquote(response.headers.get("X-Log-RealName", "") or "")[:64] or None
    role_str = response.headers.get("X-Log-Role")
    if role_str:
        try:
            data["user_role"] = int(role_str)
        except (TypeError, ValueError):
            data["user_role"] = None
    data["operation_desc"] = unquote(response.headers.get("X-Log-Desc", "") or "")[:500] or None
    return data


class OperationLogMiddleware(BaseHTTPMiddleware):
    """
    操作日志审计中间件
    自动记录所有API请求的操作人、角色、IP、方法、URL、参数、耗时等
    [P1-3] 日志写入改为异步后台任务，绝不阻塞响应返回 / 事件循环
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

        # ========== [P1-3] 日志写异步offload到线程池，调度后立刻往下走 ==========
        try:
            log_data = _collect_log_data(request, response, request_body_bytes, cost_ms)
            task = asyncio.create_task(_write_operation_log_async(log_data))
            # 保留强引用防止被 GC 提前清理
            _pending_log_tasks.add(task)
            task.add_done_callback(_pending_log_tasks.discard)
        except Exception as outer_exc:
            logger.error(f"操作日志收集失败: {outer_exc}")

        # 清除临时响应头（不返回给客户端）
        del_headers = ["X-Log-User-Id", "X-Log-Username", "X-Log-RealName",
                       "X-Log-Role", "X-Log-Desc"]
        for h in del_headers:
            if h in response.headers:
                del response.headers[h]

        return response


def register_middlewares(app: FastAPI) -> None:
    """为FastAPI应用注册所有中间件（在main.py调用）"""

    # 1. [P1-2] CORS 改为配置化的具体域名白名单（不再 allow_origins=["*"]）
    cors_origins = list(settings.CORS_ORIGINS) if settings.CORS_ORIGINS else []
    if not cors_origins and settings.DEBUG:
        # 开发环境如果没显式配置CORS域名，兜底放行本地常用端口（仍非"*"）
        cors_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],  # 允许前端获取下载文件名
    )

    # 2. 操作日志审计中间件（自定义）
    app.add_middleware(OperationLogMiddleware)
