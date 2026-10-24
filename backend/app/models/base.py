# ====================================================================
# ORM 基础层（不映射任何实体表）
# --------------------------------------------------------------------
# 承载所有业务表的公共能力，避免每张表重复声明：
#   - TimestampMixin：created_at / updated_at 由数据库默认值与 ORM onupdate 双保险；
#   - SoftDeleteMixin：is_deleted 逻辑删除，业务查询须显式过滤 is_deleted=0；
#   - BaseModel：独立自增主键 + 上述两混入，业务模型统一继承。
# 生命周期：基础层无数据；具体表由业务模型继承后建表。
# ====================================================================
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
    # 记录落库时间：数据库层面默认取当前时间，应用未显式赋值也不会为空
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间"
    )
    # 最后修改时间：ORM 更新时自动刷新，便于审计"谁在何时改过"
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
    # 逻辑删除标记：0-未删除 1-已删除；不物理删行是为了保留审核链路与报表口径
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

    # 全局唯一自增主键：用 BigInteger 预留大表容量，业务不对外暴露语义
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )
