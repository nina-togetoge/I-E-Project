# ====================================================================
# FastAPI 应用入口（backend/main.py）
# --------------------------------------------------------------------
# 解决什么问题：
#   负责“组装”整个后端：创建 FastAPI 实例、注册中间件/异常处理、
#   挂载全部业务路由、执行启动/关闭生命周期动作。
# 被谁使用：
#   uvicorn/gunicorn 以 main:app 方式加载；本地也可 python main.py 直接启动。
# 启动流程（顺序有意义）：
#   1. 修正 sys.path，保证直接运行脚本时能找到 app 包与本地依赖；
#   2. 导入所有 ORM 模型，让 Base.metadata 收集到全部表；
#   3. create_app：注册中间件 -> 异常处理器 -> 上传目录 -> 路由；
#   4. startup：DEBUG 下 create_all 建表、探测 Redis；
#   5. shutdown：打印停止信息（连接池由进程退出回收）。
# 关键约束：
#   - 中间件/异常处理器必须在路由注册前完成，否则新路由不生效；
#   - 不挂载 /static 静态目录，附件必须走带鉴权的下载/预览接口；
#   - 当前入口不启动 APScheduler 调度器，逾期终止等时效规则
#     在读取项目详情时惰性执行，避免多副本重复调度。
# ====================================================================
r"""
校园创新创业项目管理平台 - FastAPI 应用入口
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
架构：分层架构（路由 -> 服务 -> CRUD -> 模型/DB）
运行：
    python -m venv .venv && .venv\Scripts\activate    # Windows
    pip install -r requirements.txt
    修改 .env 中 MySQL / Redis 等配置
    在 MySQL 8.0 中执行 schema.sql 建库建表
    python main.py     # 启动 uvicorn
    打开 http://127.0.0.1:8000/docs 查看接口文档
"""
import os
import sys

# 确保项目根目录在 sys.path 中（方便直接 python main.py 运行）
# 原因：直接执行脚本时 sys.path[0] 是 backend 目录，而 uvicorn 导入 "main:app"
# 时也需要能 import app 包，这里显式插入可同时兼容两种启动方式
_PROJ_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJ_ROOT)
# 本地离线依赖目录（python_packages 中预安装了 fastapi/uvicorn/sqlalchemy 等）
# 注意：该目录内含 Windows 编译的 .pyd 二进制，在 Docker(Linux) 环境下会导致
# ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
# 因此仅在非容器环境（本地 Windows 开发）才把它插入 sys.path 顶部；
# 容器内统一使用镜像构建阶段 pip install -r requirements.txt 安装的 Linux 原生版本。
_PKGS = os.path.join(_PROJ_ROOT, "python_packages")
_IN_CONTAINER = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_RUNNING") == "1"
if not _IN_CONTAINER and os.path.isdir(_PKGS) and _PKGS not in sys.path:
    sys.path.insert(0, _PKGS)

from fastapi import FastAPI

# ---- 平台级能力 ----
# settings：应用元信息、监听地址、上传目录、DEBUG 开关
# register_exception_handlers：把业务异常/校验异常/数据库异常统一转为标准响应
# register_middlewares：CORS + 操作日志审计
# engine/Base：启动时按需自动建表
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middlewares
from app.database.session import engine, Base

# ============== 保证所有 ORM 模型被 Base.metadata 发现 ==============
# 仅导入模块、不直接使用名称：导入动作会执行 models 内的表定义，
# 缺少这一步 create_all 会漏建未被其他模块提前导入的表
from app import models  # noqa: F401

# ============== 路由聚合 ==============
# 每个 router 文件内部按“领域”再拆多个 APIRouter（如认证/用户/学院/日志）
from app.api.routers.user_router import (
    router_auth, router_user, router_college, router_log,
)
from app.api.routers.project_router import (
    router_project, router_achievement, router_stats,
)
from app.api.routers.review_router import (
    router_review, router_midterm, router_change,
)
from app.api.routers.common_router import (
    router_common, router_upload, router_excel, router_health,
)
from app.api.routers.expense_router import router_expense
from app.api.routers.competition_router import router_competition
from app.api.routers.certificate_router import router_certificate
from app.api.routers.announcement_router import router_announcement
from app.api.routers.notification_router import router_notification
from app.api.routers.ai_router import router_ai


def create_app() -> FastAPI:
    """
    应用工厂函数：创建并配置 FastAPI 实例。

    返回：
        完成中间件、异常处理器、路由挂载的 FastAPI 对象。
    说明：
        采用工厂模式而非模块级直接 new，便于测试时构造独立实例；
        当前全局仍保留 app = create_app() 供 uvicorn 使用。
    """
    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "## 校园创新创业项目管理平台 - 后端 API\n"
            "本科软件工程专业毕业设计项目\n\n"
            "### 技术栈\n"
            "- 核心框架：FastAPI + Python 3.10+\n"
            "- ORM：SQLAlchemy 2.0 + MySQL 8.0\n"
            "- 参数校验：Pydantic v2\n"
            "- 认证：JWT(AccessToken + RefreshToken) + bcrypt\n"
            "- 缓存：Redis(自动降级内存缓存)\n"
            "- Excel：openpyxl\n\n"
            "> 安全提示：初始用户密码由系统初始化脚本生成，首次登录后请立即修改。\n"
            "> 接口默认使用 Bearer Token 认证，详细权限请参考各路由说明。"
        ),
        version=settings.APP_VERSION,
        # 文档与 OpenAPI 路径固定为 /docs、/redoc、/openapi.json，
        # 前端“接口文档”入口与操作日志的 SKIP_LOG_PATHS 均依赖这三个路径
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        # debug 透传给 Starlette，影响错误页是否展示堆栈
        debug=settings.DEBUG,
        terms_of_service=None,
        contact={"name": "软件工程毕业设计", "email": "contact@university.edu.cn"},
        license_info={"name": "MIT License"},
    )

    # ---- 1. 注册中间件（CORS / 操作日志审计）----
    # 先把请求处理管线搭好，再挂业务路由，保证所有路由都在同一套中间件下运行；
    # 注意 add_middleware 必须在应用启动前调用，运行期不可动态追加
    register_middlewares(app)

    # ---- 2. 注册全局异常处理器 ----
    # 保证业务异常也返回统一 {code,message,data}，前端可无差别解析
    register_exception_handlers(app)

    # ---- 3. 上传/索引目录 ----
    # 注意：不再挂载 /static 静态目录，避免上传文件被未鉴权直接访问；
    # 所有附件统一通过 /api/files/download|preview 接口（带登录校验与归属校验）访问。
    # 这里只保证目录存在，实际文件写入由上传服务完成
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # ---- 4. 挂载业务路由 ----
    # 统一前缀 /api，便于 Nginx 按前缀转发、与前端代理规则一致；
    # 注册顺序主要影响 OpenAPI 文档分组，接口匹配按声明顺序进行
    api_prefix = "/api"

    # 认证与用户（登录/刷新/用户管理/学院/操作日志）
    app.include_router(router_auth, prefix=api_prefix)
    app.include_router(router_user, prefix=api_prefix)
    app.include_router(router_college, prefix=api_prefix)
    app.include_router(router_log, prefix=api_prefix)

    # 项目申报 / 成果 / 统计
    app.include_router(router_project, prefix=api_prefix)
    app.include_router(router_achievement, prefix=api_prefix)
    app.include_router(router_stats, prefix=api_prefix)

    # 审核 / 中期 / 变更
    app.include_router(router_review, prefix=api_prefix)
    app.include_router(router_midterm, prefix=api_prefix)
    app.include_router(router_change, prefix=api_prefix)

    # 经费报销
    app.include_router(router_expense, prefix=api_prefix)

    # 创新创业大赛
    app.include_router(router_competition, prefix=api_prefix)

    # 获奖证书
    app.include_router(router_certificate, prefix=api_prefix)

    # 系统公告
    app.include_router(router_announcement, prefix=api_prefix)

    # 站内通知
    app.include_router(router_notification, prefix=api_prefix)

    # AI 助手
    app.include_router(router_ai, prefix=api_prefix)

    # 通用工具 / 文件 / 搜索 / Excel / 健康检查
    # 注意：router_health 的路径已自带 /api/health，不能再加 /api 前缀，
    # 否则会变成 /api/api/health，导致探针与监控访问 404
    app.include_router(router_common, prefix=api_prefix)
    app.include_router(router_upload, prefix=api_prefix)
    app.include_router(router_excel, prefix=api_prefix)
    app.include_router(router_health)

    # ---- 5. 启动/关闭生命周期事件 ----
    # 说明：使用 FastAPI 旧式 on_event 钩子（当前依赖版本仍支持）；
    # 启动阶段只做“幂等”动作，失败也不应阻止服务提供只读能力
    @app.on_event("startup")
    async def on_startup():
        """
        应用启动时执行：打印入口信息、按需自动建表、探测 Redis。

        副作用：
            - DEBUG=True 时执行 Base.metadata.create_all（只建缺失表，不改已有表）；
            - 导入 redis_client 触发连接探测，失败由内部降级处理。
        注意：
            生产环境推荐用 schema.sql 或 alembic 管理表结构，
            create_all 不会做字段变更/迁移，不能替代迁移工具。
        """
        print("=" * 60)
        print(f"  {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
        print(f"  文档地址:  http://{settings.HOST}:{settings.PORT}/docs")
        print("=" * 60)

        # DEBUG 模式下自动尝试建表（生产环境推荐 alembic 迁移）
        if settings.DEBUG:
            try:
                # 仅创建不存在的表，不会覆盖
                Base.metadata.create_all(bind=engine)
                print("[OK] 数据库表结构已同步（create_all 跳过已存在）")
            except Exception as e:
                # 建表失败只告警：可能数据库尚未就绪，服务仍可启动并暴露健康检查
                print(f"[WARN] 自动建表失败，请手动执行 schema.sql ({e})")

        # Redis 连通性（已在内部自行打印）
        # 主动触发 redis_client 初始化，确保首个请求不必承担连接超时；
        # Redis 不可用时 TokenBlacklist/缓存会自动退回进程内实现
        try:
            from app.utils.redis_cache import redis_client
            _ = redis_client
        except Exception:
            pass

    @app.on_event("shutdown")
    async def on_shutdown():
        """
        应用关闭时执行：打印停止信息。

        说明：
            数据库连接池由进程退出时自动释放；如有后台任务/调度器，
            应在此处显式 stop/join，当前入口没有此类资源。
        """
        print(f"\n[INFO] {settings.APP_NAME} 服务已停止")

    return app


# 全局 app 实例（供 uvicorn main:app 调用）
# 模块导入时即完成应用组装，因此配置/模型导入错误会在启动阶段直接暴露
app = create_app()


if __name__ == "__main__":
    # 本地开发启动方式：reload=DEBUG 开启热重载，生产应关闭以免重复加载；
    # workers=1 保持单进程语义（内存缓存、本地附件目录、黑名单降级实现），
    # 多进程部署时需确保 Redis 可用，否则登出黑名单等状态无法跨进程共享
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1,
        log_level="info",
    )
