"""
基础模型模块
定义通用基础ORM模型，包含创建时间、更新时间、软删除等公共字段
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, SmallInteger, func
from sqlalchemy.orm import declared_attr, Mapped, mapped_column

from app.database.session import Base


class TimestampMixin:
    """
    时间戳混入类
    为模型自动添加创建时间和更新时间字段
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )


class SoftDeleteMixin:
    """
    软删除混入类
    添加is_deleted字段实现逻辑删除，而非物理删除
    """
    is_deleted: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="软删除标记: 0-未删除 1-已删除"
    )


class BaseModel(TimestampMixin, SoftDeleteMixin, Base):
    """
    基础抽象模型类
    所有业务ORM模型应继承此类，自动获得主键、时间戳、软删除字段
    """
    __abstract__ = True

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )
