"""
站内通知 Pydantic 数据模型
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationItem(BaseModel):
    """通知列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    content: str
    level: int = 1
    biz_type: Optional[str] = None
    biz_id: Optional[int] = None
    link: Optional[str] = None
    is_read: int = 0
    read_time: Optional[datetime] = None
    created_at: datetime


class NotificationUnreadCount(BaseModel):
    """未读通知数量"""
    count: int = Field(default=0, description="未读通知数")
