# ====================================================================
# 数据库会话管理模块（app/database/session.py）
# --------------------------------------------------------------------
# 解决什么问题：
#   集中创建 SQLAlchemy 同步引擎与 Session 工厂，给 FastAPI 提供
#   “每请求一个会话、请求结束自动关闭”的依赖。
# 被谁使用：
#   api 路由（Depends(get_db)）、core.security（鉴权查用户）、
#   middleware（后台线程独立会话写日志）、seed_demo_data（脚本独立会话）。
# 关键约束：
#   1. MySQL 连接是阻塞 IO，不能在实际并发很高的 async 路由里长时间持有；
#   2. expire_on_commit=False 保证 commit 后仍可读取对象属性，
#      否则响应序列化时会触发额外查询甚至 DetachedInstanceError；
#   3. Base 是所有 ORM 模型的基类，main.py 依赖它 create_all。
# ====================================================================
"""
数据库会话管理模块
基于 SQLAlchemy 2.0 实现同步数据库会话与依赖注入
"""
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from app.core.config import settings

# ========== 数据库引擎与会话工厂 ==========

# 创建SQLAlchemy同步引擎，使用连接池优化
# pool_pre_ping：每次取连接前发送轻量 ping，自动剔除被 MySQL 超时断开的死连接；
# pool_size/max_overflow：常驻 20 + 峰值最多再开 40，合计上限 60，
#                          需小于 MySQL max_connections，且按实际 worker 数评估；
# pool_recycle=3600：连接存活超过 1 小时即回收，规避 MySQL wait_timeout；
# pool_timeout=30：连接池耗尽时最多等待 30 秒，超时抛异常而不是无限挂起；
# echo=DEBUG：开发时打印 SQL 便于排查，生产关闭以免日志爆炸。
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,            # 连接前先ping，防止连接失效
    pool_size=20,                  # 连接池大小
    max_overflow=40,               # 最大溢出连接数
    pool_recycle=3600,             # 连接回收时间(秒)
    pool_timeout=30,               # 获取连接超时时间(秒)
    echo=settings.DEBUG,           # DEBUG模式输出SQL
)

# 会话工厂：
# autoflush=False 避免查询前隐式 flush 造成意外写入；
# autocommit=False 要求业务显式 commit，事务边界清晰；
# expire_on_commit=False 让 commit 后的对象仍可直接序列化返回
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# ORM模型基类：所有 models 继承它，main.py 用 Base.metadata.create_all 建表
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依赖注入函数：获取数据库会话。

    Yields：
        请求级 Session 对象。
    副作用：
        请求处理结束后（无论成功/异常）自动 close，把连接归还连接池。
    注意：
        本函数不自动 commit；业务 service 必须显式提交事务，
        未提交的修改会在会话关闭时回滚。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
