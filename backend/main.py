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
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middlewares
from app.database.session import engine, Base

# ============== 保证所有 ORM 模型被 Base.metadata 发现 ==============
from app import models  # noqa: F401

# ============== 路由聚合 ==============
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
    router_common, router_upload, router_search, router_excel, router_health,
)
from app.api.routers.expense_router import router_expense


def create_app() -> FastAPI:
    """应用工厂函数"""
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
            "- Excel：openpyxl\n"
            "- 全文检索：Whoosh + Jieba(自动降级 LIKE 查询)\n\n"
            "> 安全提示：初始用户密码由系统初始化脚本生成，首次登录后请立即修改。\n"
            "> 接口默认使用 Bearer Token 认证，详细权限请参考各路由说明。"
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        debug=settings.DEBUG,
        terms_of_service=None,
        contact={"name": "软件工程毕业设计", "email": "contact@university.edu.cn"},
        license_info={"name": "MIT License"},
    )

    # ---- 1. 注册中间件（CORS / 操作日志审计）----
    register_middlewares(app)

    # ---- 2. 注册全局异常处理器 ----
    register_exception_handlers(app)

    # ---- 3. 静态资源（上传文件）----
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.WHOOSH_INDEX_DIR, exist_ok=True)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # ---- 4. 挂载业务路由 ----
    api_prefix = "/api"

    # 认证与用户
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

    # 通用工具 / 文件 / 搜索 / Excel / 健康检查
    app.include_router(router_common, prefix=api_prefix)
    app.include_router(router_upload, prefix=api_prefix)
    app.include_router(router_search, prefix=api_prefix)
    app.include_router(router_excel, prefix=api_prefix)
    app.include_router(router_health)

    # ---- 5. 启动/关闭生命周期事件 ----
    @app.on_event("startup")
    async def on_startup():
        """应用启动时执行：自动创建表（或验证）、预热索引/缓存"""
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
                print(f"[WARN] 自动建表失败，请手动执行 schema.sql ({e})")

        # 全文检索：首次自动尝试重建索引（可选）
        try:
            from app.utils.search_engine import search_engine
            print("[INFO] 全文检索引擎已加载（首次运行可调用 /api/search/rebuild-index 重建索引）")
        except Exception as e:
            print(f"[WARN] 全文检索初始化提示: {e}")

        # Redis 连通性（已在内部自行打印）
        try:
            from app.utils.redis_cache import redis_client
            _ = redis_client
        except Exception:
            pass

    @app.on_event("shutdown")
    async def on_shutdown():
        print(f"\n[INFO] {settings.APP_NAME} 服务已停止")

    return app


# 全局 app 实例（供 uvicorn main:app 调用）
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1,
        log_level="info",
    )
