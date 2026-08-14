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
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,            # 连接前先ping，防止连接失效
    pool_size=20,                  # 连接池大小
    max_overflow=40,               # 最大溢出连接数
    pool_recycle=3600,             # 连接回收时间(秒)
    pool_timeout=30,               # 获取连接超时时间(秒)
    echo=settings.DEBUG,           # DEBUG模式输出SQL
)

# 会话工厂
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# ORM模型基类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依赖注入函数：获取数据库会话
    使用yield实现请求结束后自动关闭会话
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
