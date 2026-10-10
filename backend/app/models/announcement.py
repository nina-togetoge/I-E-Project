"""
公告 ORM 模型
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, BigInteger, SmallInteger, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Announcement(BaseModel):
    """系统公告"""
    __tablename__ = "biz_announcement"

    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="公告标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="公告内容")
    # 公告类型: 1-系统通知 2-申报通知 3-结果公示 4-其他
    announcement_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="公告类型")
    # 状态: 0-草稿 1-已发布 2-已下线
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="发布状态")
    # 优先级: 1-普通 2-重要 3-紧急
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="优先级")
    publish_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="发布时间")
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="到期时间（到期后自动下线）")
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="浏览次数")
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sys_user.id"), nullable=True, comment="创建人ID"
    )

    creator: Mapped[Optional["SysUser"]] = relationship("SysUser", foreign_keys=[created_by])

    __table_args__ = (
        Index("idx_announcement_status", "status"),
        Index("idx_announcement_type", "announcement_type"),
        Index("idx_announcement_priority", "priority"),
    )
