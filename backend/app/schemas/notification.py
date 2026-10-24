# ====================================================================
# 通知模块 Schema
# --------------------------------------------------------------------
# 分组说明：
#   1. NotificationItem：通知列表项/详情共用，from_attributes 直接转换 ORM；
#   2. NotificationUnreadCount：未读角标数量。
# 说明：通知的创建由 Service 内部调用，不对外暴露创建 Schema；
#       已读操作仅按 id 批量标记，无需额外入参模型。
# ====================================================================
"""
站内通知 Pydantic 数据模型
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationItem(BaseModel):
    """通知列表项：列表与详情共用；is_read 供前端控制未读样式"""
    model_config = ConfigDict(from_attributes=True)

    # 主键与接收人
    id: int
    user_id: int
    # 标题/正文
    title: str
    content: str
    # 级别：1普通 2警告 3成功，控制图标与颜色
    level: int = 1
    # 关联业务：点击时按 biz_type + biz_id 或 link 跳转
    biz_type: Optional[str] = None
    biz_id: Optional[int] = None
    link: Optional[str] = None
    # 已读状态与阅读时间；0-未读 1-已读
    is_read: int = 0
    read_time: Optional[datetime] = None
    created_at: datetime


class NotificationUnreadCount(BaseModel):
    """未读通知数量：供顶部铃铛角标轮询"""
    count: int = Field(default=0, description="未读通知数")
