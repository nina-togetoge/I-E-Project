"""
站内通知 ORM 模型

用于审核结果、成果认定等业务动作的站内消息推送。
通知按用户存储，读取后标记已读。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SysNotification(BaseModel):
    """站内通知"""
    __tablename__ = "sys_notification"

    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="接收人ID"
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False, comment="通知标题")
    content: Mapped[str] = mapped_column(String(1000), nullable=False, comment="通知内容")
    # 级别：1-普通 2-警告 3-成功
    level: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, comment="通知级别"
    )
    biz_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="关联业务类型: project/midterm/achievement/final"
    )
    biz_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="关联业务ID"
    )
    link: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="前端跳转路径"
    )
    is_read: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, comment="是否已读: 0-未读 1-已读"
    )
    read_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="阅读时间"
    )

    __table_args__ = (
        Index("idx_notification_user", "user_id"),
        Index("idx_notification_read", "user_id", "is_read"),
    )
