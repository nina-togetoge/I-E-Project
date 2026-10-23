"""
FastAPI中间件模块
实现：操作日志审计中间件、跨域CORS、请求耗时统计等
"""
import asyncio
import time
import json
import logging
from urllib.parse import unquote
from typing import Callable, Dict, Any
from jose import jwt
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
# 只记录写操作与导出请求：普通 GET 查询（列表刷新、轮询、页面加载）不入库，避免淹没真实操作
MUTATING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

# URL 模块段 → 页面可读模块名（与前端「操作日志」高级筛选保持一致）
MODULE_NAME_MAP = {
    "projects": "项目管理",
    "achievements": "成果管理",
    "reviews": "审核管理",
    "midterm": "审核管理",
    "changes": "审核管理",
    "expenses": "报销管理",
    "users": "用户管理",
    "auth": "认证模块",
    "colleges": "学院管理",
    "logs": "系统管理",
    "statistics": "数据看板",
    "files": "文件管理",
    "excel": "数据导出",
    "announcements": "公告管理",
    "competitions": "大赛管理",
    "notifications": "站内通知",
    "ai": "AI助手",
    "common": "系统管理",
}


def _should_log_request(method: str, path: str) -> bool:
    """写操作、登录/登出、导出才记录；GET 查询请求直接跳过"""
    if not _path_should_log(path):
        return False
    return method.upper() in MUTATING_METHODS or "/export" in path


def _infer_module_name(path: str) -> str:
    """按 /api/{module}/... 的模块段映射为可读模块名"""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "api":
        raw = parts[1]
        return MODULE_NAME_MAP.get(raw, raw)
    return "系统管理"


def _infer_operation_type(method: str, path: str) -> str:
    """操作类型统一为大写枚举，登录/导出单独识别"""
    lower_path = path.lower()
    if lower_path.endswith(("/login", "/logout", "/refresh")):
        return "LOGIN"
    if "/export" in lower_path:
        return "EXPORT"
    return {
        "GET": "QUERY", "POST": "CREATE", "PUT": "UPDATE",
        "DELETE": "DELETE", "PATCH": "UPDATE",
    }.get(method.upper(), method.upper())


# 请求参数中需要脱敏的字段（避免把密码/令牌写入审计日志）
SENSITIVE_LOG_KEYS = {"password", "old_password", "new_password", "refresh_token", "access_token", "token"}


def _mask_sensitive(value: Any) -> Any:
    """递归脱敏请求参数中的密码、令牌等敏感字段"""
    if isinstance(value, dict):
        return {
            k: "***" if str(k).lower() in SENSITIVE_LOG_KEYS else _mask_sensitive(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask_sensitive(v) for v in value]
    return value


def _extract_token_payload(request: Request) -> Dict[str, Any]:
    """从 Authorization / 下载类 token 中解析操作人信息（仅用于日志，不校验黑名单）"""
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        token = request.query_params.get("token") or request.cookies.get("access_token") or ""
    if not token:
        return {}
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except Exception:
        return {}
    return payload if payload.get("type") == "access" else {}


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
        params_dict = _mask_sensitive(params_dict)
        try:
            data["request_params"] = json.dumps(params_dict, ensure_ascii=False)[:5000]
        except Exception:
            data["request_params"] = "[UNSERIALIZABLE_PARAMS]"

    # 模块名 / 操作类型：根据URL路径推断
    data["module_name"] = _infer_module_name(request.url.path)
    data["operation_type"] = _infer_operation_type(request.method, request.url.path)

    # 操作人信息：优先取路由层写入的响应头，缺失时从请求 token 中解析
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
    if not data.get("user_id"):
        payload = _extract_token_payload(request)
        if payload:
            data["user_id"] = payload.get("uid")
            data["username"] = payload.get("sub")
            data["real_name"] = payload.get("name")
            data["user_role"] = payload.get("role")
    data["operation_desc"] = unquote(response.headers.get("X-Log-Desc", "") or "")[:500] or None
    return data


class OperationLogMiddleware(BaseHTTPMiddleware):
    """
    操作日志审计中间件
    记录写操作 / 登录 / 导出的操作人、角色、IP、方法、URL、参数、耗时等；
    普通 GET 查询不入库，避免列表刷新与轮询淹没真实操作。
    [P1-3] 日志写入改为异步后台任务，绝不阻塞响应返回 / 事件循环
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过不需要记录的请求（普通 GET 查询也跳过，只留写操作/登录/导出）
        if not _should_log_request(request.method, request.url.path):
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
