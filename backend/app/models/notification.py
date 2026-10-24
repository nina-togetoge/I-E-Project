# ====================================================================
# 通知域 ORM 模型（sys_notification）
# --------------------------------------------------------------------
# 业务用途：审核结果、成果认定、结题验收等业务动作触发的站内信；
#           按用户逐条投递（一个事件可生成多条），读取后标记已读。
# 与被谁关联：user_id 指向接收人 sys_user，但未建外键以保留离职用户的通知；
#            biz_type + biz_id 逻辑关联业务记录（project/midterm/achievement/final）。
# 数据生命周期：软删除；已读通知长期保留，可按时间归档清理。
# ====================================================================
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
    """
    站内通知表（sys_notification）

    业务含义：站内信主表，每位接收人一行，用于消息中心与未读角标。
    关键约束：无唯一键；同一业务事件对多个接收人会产生多条通知。
    注意：不建 user_id 外键，避免用户被清理时连带删除历史通知。
    """
    __tablename__ = "sys_notification"

    # 接收人：消息中心与未读数都按此字段过滤
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="接收人ID"
    )
    # 标题：列表首行，建议控制在一句话内
    title: Mapped[str] = mapped_column(String(128), nullable=False, comment="通知标题")
    # 内容：正文，长度受限 1000 字符，超长应引导到业务详情页
    content: Mapped[str] = mapped_column(String(1000), nullable=False, comment="通知内容")
    # 级别：1-普通 2-警告 3-成功（与通知标题图标的语义一致）
    level: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, comment="通知级别"
    )
    # 关联业务类型: project/midterm/achievement/final，与 biz_id 组成逻辑外键
    biz_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="关联业务类型: project/midterm/achievement/final"
    )
    # 关联业务记录ID：点击通知时据此定位详情
    biz_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="关联业务ID"
    )
    # 前端跳转路径：由后端生成，避免前端硬编码路由
    link: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="前端跳转路径"
    )
    # 是否已读: 0-未读 1-已读（未读角标统计依据）
    is_read: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, comment="是否已读: 0-未读 1-已读"
    )
    # 阅读时间：首次标记已读时写入，用于行为分析
    read_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="阅读时间"
    )

    # 单列索引支撑"我的全部通知"；(user_id, is_read) 组合索引支撑未读数统计
    __table_args__ = (
        Index("idx_notification_user", "user_id"),
        Index("idx_notification_read", "user_id", "is_read"),
    )
