# ====================================================================
# 公告域 ORM 模型（biz_announcement）
# --------------------------------------------------------------------
# 业务用途：向全校或指定范围发布系统通知、申报通知、结果公示等文本公告。
# 与被谁关联：created_by 指向 sys_user（管理员发布者），无反向关系。
# 数据生命周期：软删除；status=已发布且 expire_time 到期后由业务层视为下线，
#              历史公告保留以支撑审计与追溯。
# ====================================================================
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
    """
    系统公告表（biz_announcement）

    业务含义：管理端发布的公告，学生/教师端按发布状态与到期时间读取。
    关键约束：无唯一业务键；仅 status=1 且未过期（或 expire_time 为空）对用户可见。
    """
    __tablename__ = "biz_announcement"

    # 公告标题：列表展示与检索
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="公告标题")
    # 公告正文：富文本/纯文本，详情页展示
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="公告内容")
    # 公告类型: 1-系统通知 2-申报通知 3-结果公示 4-其他
    announcement_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="公告类型")
    # 状态: 0-草稿 1-已发布 2-已下线（草稿仅发布者可见）
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="发布状态")
    # 优先级: 1-普通 2-重要 3-紧急（前端用不同颜色标识）
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="优先级")
    # 发布时间：发布动作发生时写入，用于排序
    publish_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="发布时间")
    # 到期时间：到期后自动视为下线，为空表示永久有效
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="到期时间（到期后自动下线）")
    # 浏览次数：详情打开时自增
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="浏览次数")
    # 创建人：发布者，用于审计
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sys_user.id"), nullable=True, comment="创建人ID"
    )

    # 创建人（多对一，只读）：foreign_keys 显式指定，避免与 sys_user 的其他关系歧义
    creator: Mapped[Optional["SysUser"]] = relationship("SysUser", foreign_keys=[created_by])

    # 状态/类型/优先级索引支撑前台公告列表的多条件筛选
    __table_args__ = (
        Index("idx_announcement_status", "status"),
        Index("idx_announcement_type", "announcement_type"),
        Index("idx_announcement_priority", "priority"),
    )
