# ====================================================================
# FastAPI 中间件模块（app/core/middleware.py）
# --------------------------------------------------------------------
# 解决什么问题：
#   在请求进入路由/离开应用之间插入横切逻辑：审计日志、跨域、耗时统计。
#   这些逻辑与具体业务无关，放在中间件可避免每个路由重复写。
# 被谁使用：
#   仅由 main.py 的 register_middlewares(app) 调用一次。
# 关键设计：
#   1. 操作日志只记录“写操作/登录/导出”，普通 GET 不入库，防止轮询刷爆日志表。
#   2. 日志写库通过 asyncio.to_thread 放到线程池，响应不被数据库 IO 阻塞。
#   3. 请求体流只能读一次：中间件读取后必须用新的 receive 重新包装，
#      且只截断日志副本，不能截断转发给路由的 body，否则大文件上传会损坏。
#   4. 中间件顺序：后 add 的在外层。当前 CORS 先注册（内层），
#      操作日志后注册（外层），因此日志能记录到 CORS 处理后的最终响应状态码。
#   5. 全局异常捕获不在这里，而是在 exceptions.register_exception_handlers
#      中通过 app.exception_handler 注册，保证异常也走统一响应体。
# ====================================================================
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

# 后台任务引用集合（避免被GC）：
# asyncio.create_task 返回的任务若没有强引用，可能在完成前被垃圾回收，
# 这里持有引用并在 done 回调中移除
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
    """
    判断该请求是否需要写入操作日志。

    参数：
        method：HTTP 方法。
        path：请求路径（不含域名）。
    返回：
        True 表示需要记录。
    规则：
        先排除健康检查/文档/静态资源，再只保留写方法（POST/PUT/DELETE/PATCH）
        与包含 /export 的下载请求；GET 查询即使命中 /api/ 也不记录。
    """
    if not _path_should_log(path):
        return False
    return method.upper() in MUTATING_METHODS or "/export" in path


def _infer_module_name(path: str) -> str:
    """
    按 /api/{module}/... 的模块段映射为可读模块名。

    参数：
        path：请求路径。
    返回：
        中文模块名；未知模块返回原始段名，非 /api 路径返回“系统管理”。
    用途：
        操作日志页面的“模块”筛选项依赖该值，需与前端枚举保持一致。
    """
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "api":
        raw = parts[1]
        return MODULE_NAME_MAP.get(raw, raw)
    return "系统管理"


def _infer_operation_type(method: str, path: str) -> str:
    """
    推断操作类型（统一大写枚举）。

    参数：
        method：HTTP 方法。
        path：请求路径。
    返回：
        LOGIN（登录/登出/刷新）、EXPORT（导出）、
        QUERY/CREATE/UPDATE/DELETE，未知方法原样返回。
    说明：
        登录与导出优先于 HTTP 方法判断，否则会被记成 CREATE/QUERY，影响审计筛选。
    """
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
    """
    递归脱敏请求参数中的密码、令牌等敏感字段。

    参数：
        value：任意可 JSON 化的请求参数（dict/list/标量）。
    返回：
        同结构副本，敏感键的值替换为 "***"。
    说明：
        键名统一转小写比较，兼容 Password / new_password 等写法；
        只做展示层脱敏，原始请求体不会被修改。
    """
    if isinstance(value, dict):
        return {
            k: "***" if str(k).lower() in SENSITIVE_LOG_KEYS else _mask_sensitive(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask_sensitive(v) for v in value]
    return value


def _extract_token_payload(request: Request) -> Dict[str, Any]:
    """
    从 Authorization / 下载类 token 中解析操作人信息（仅用于日志，不校验黑名单）。

    参数：
        request：当前请求。
    返回：
        合法的 access token 声明字典；无令牌、解析失败或类型不符返回空字典。
    注意：
        这里只验签不查库/黑名单，避免日志路径产生额外数据库开销；
        真正的鉴权仍由 get_current_user 完成。
    """
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
    """
    从请求中获取真实客户端 IP（考虑反向代理场景）。

    参数：
        request：当前请求。
    返回：
        X-Forwarded-For 首个地址 > X-Real-IP > 直连 client.host，均缺失返回空串。
    注意：
        这两个头可被客户端伪造，仅用于审计展示，不能作为安全校验依据。
    """
    # 常见反向代理头
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else ""


def _path_should_log(path: str) -> bool:
    """
    判断请求路径是否属于“需要审计”的 API 范围。

    参数：
        path：请求路径。
    返回：
        True 表示以 /api/ 开头且不在 SKIP_LOG_PATHS 中。
    说明：
        先判断跳过项再判断前缀，保证 /api/health 这类高频探针不会被记录。
    """
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
    """
    在线程池中执行的同步写库函数。

    参数：
        log_data：已序列化、可直接展开为 SysOperationLog 字段的字典。
    副作用：
        新建独立数据库会话并提交一条审计记录。
    注意：
        1. 必须使用独立的 SessionLocal，不能复用请求级 get_db 会话，
           因为请求结束时该会话已关闭，后台线程继续使用会报错；
        2. 写日志失败只记录错误，绝不能反向影响业务请求（审计不能阻断交易）。
    """
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
    """
    异步包装：把同步数据库写操作 offload 到线程池。

    参数：
        log_data：审计日志字段字典。
    说明：
        PyMySQL 是同步驱动，直接在事件循环里 commit 会阻塞其他请求；
        asyncio.to_thread 让阻塞 IO 在默认线程池执行，保证 API 吞吐。
    """
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
    """
    从请求/响应中抽取 SysOperationLog 字段字典（序列化后跨线程安全）。

    参数：
        request：原始请求对象。
        response：下游路由返回的响应（可能携带 X-Log-* 临时头）。
        request_body_bytes：已截断到 MAX_LOG_BODY_SIZE 的请求体副本。
        cost_ms：请求处理耗时（毫秒）。
    返回：
        可直接 SysOperationLog(**data) 的字典。
    注意：
        返回的字典只含基本类型（str/int/dict），不能含 ORM 对象或流对象，
        否则跨线程写库时会因会话/连接绑定报错。
    """
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
    # 1. 查询参数直接取字典；2. JSON body 解析后并入；
    # 3. 表单/文件上传只标记 [FORM_DATA]，避免把二进制或大字段写入日志表
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
        # 4. 统一脱敏后再序列化，并截断到 5000 字符，防止超长参数撑爆日志字段
        params_dict = _mask_sensitive(params_dict)
        try:
            data["request_params"] = json.dumps(params_dict, ensure_ascii=False)[:5000]
        except Exception:
            data["request_params"] = "[UNSERIALIZABLE_PARAMS]"

    # 模块名 / 操作类型：根据URL路径推断
    data["module_name"] = _infer_module_name(request.url.path)
    data["operation_type"] = _infer_operation_type(request.method, request.url.path)

    # 操作人信息：优先取路由层写入的响应头，缺失时从请求 token 中解析
    # 路由层通过 OperationContext 把用户信息放进 X-Log-* 头，可避免中间件重复查库；
    # header 值为空时用 0 兜底，再 int() 转换，转换失败则置 None
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
    操作日志审计中间件。

    记录写操作 / 登录 / 导出的操作人、角色、IP、方法、URL、参数、耗时等；
    普通 GET 查询不入库，避免列表刷新与轮询淹没真实操作。
    [P1-3] 日志写入改为异步后台任务，绝不阻塞响应返回 / 事件循环。
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        请求拦截与日志采集主流程。

        参数：
            request：进入中间件的请求。
            call_next：调用下游（后续中间件/路由）的回调。
        返回：
            下游响应；日志写入异步执行，不改变响应内容与状态码。
        """
        # 1. 快速分流：不需要审计的请求直接透传，避免读取 body 与额外开销
        if not _should_log_request(request.method, request.url.path):
            return await call_next(request)

        start_time = time.time()
        # ========== 读取请求体（注意：body流只能读一次，需要重新包装）==========
        # 请求体只截断“日志记录”用的副本，转发给下游的必须是完整内容，
        # 否则 >100KB 的上传/大 JSON 会被清空，导致 422 / 文件丢失。
        body = b""
        try:
            body = await request.body()
        except Exception:
            pass
        request_body_bytes = body[:MAX_LOG_BODY_SIZE]

        # 重新构造Request，让后续路由仍可读取完整body
        # （body 已被上面的 await request.body() 消费，必须用闭包把完整字节喂回去）
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        new_request = Request(request.scope, receive=receive)

        # 2. 执行下游请求并计算耗时；异常会继续向上抛给全局异常处理器，
        #    因此这里不 try/except，避免吞掉业务异常
        response = await call_next(new_request)
        cost_ms = int((time.time() - start_time) * 1000)

        # ========== [P1-3] 日志写异步offload到线程池，调度后立刻往下走 ==========
        # 3. 采集字段 -> create_task 异步写库；即使采集/调度失败也只记错误，
        #    不能因为审计问题让已经成功的业务响应变成 500
        try:
            log_data = _collect_log_data(request, response, request_body_bytes, cost_ms)
            task = asyncio.create_task(_write_operation_log_async(log_data))
            # 保留强引用防止被 GC 提前清理
            _pending_log_tasks.add(task)
            task.add_done_callback(_pending_log_tasks.discard)
        except Exception as outer_exc:
            logger.error(f"操作日志收集失败: {outer_exc}")

        # 清除临时响应头（不返回给客户端）
        # X-Log-* 只用于路由 -> 中间件传递信息，必须删除，避免泄露内部用户ID/描述
        del_headers = ["X-Log-User-Id", "X-Log-Username", "X-Log-RealName",
                       "X-Log-Role", "X-Log-Desc"]
        for h in del_headers:
            if h in response.headers:
                del response.headers[h]

        return response


def register_middlewares(app: FastAPI) -> None:
    """
    为 FastAPI 应用注册所有中间件（在 main.py 调用）。

    参数：
        app：FastAPI 实例。
    说明：
        Starlette 的 add_middleware 会把新中间件插到最外层，
        因此“后注册 = 先执行”。当前实际执行顺序为：
            OperationLogMiddleware（外层，先计时）
              -> CORSMiddleware（内层，处理跨域/preflight）
                -> 路由
        该顺序不能随意互换：
        - 操作日志必须在外层，才能记录到包含跨域处理在内的完整耗时；
        - CORS 必须在内层，保证异常响应/业务响应都经过跨域头注入；
        - preflight OPTIONS 不是写操作，会被日志中间件直接跳过。
    """

    # 1. [P1-2] CORS 改为配置化的具体域名白名单（不再 allow_origins=["*"]）
    # allow_credentials=True 与 "*" 不兼容，且白名单能降低 CSRF/数据被跨站读取的风险
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
    # 最后注册 => 位于最外层，先于 CORS 执行，负责耗时统计与审计入库
    app.add_middleware(OperationLogMiddleware)
