"""
创新创业大赛 ORM 模型
"""
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Column, String, BigInteger, SmallInteger, DateTime, Text, Date, ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Competition(BaseModel):
    """创新创业大赛"""
    __tablename__ = "biz_competition"

    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="比赛名称")
    session: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="届次(如 2026届)")
    # 比赛类型: 1-创新训练类 2-创业实践类 3-学科竞赛类 4-综合类
    competition_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="比赛类型")
    # 级别: 1-校级 2-省级 3-国家级 4-国际级
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="比赛级别")
    organizer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="主办方")
    co_organizer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="承办方")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="比赛简介")
    requirements: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="参赛要求")
    rewards: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="奖项设置")
    registration_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="报名开始日期")
    registration_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="报名截止日期")
    competition_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="比赛开始日期")
    competition_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="比赛结束日期")
    # ---- 项目流程时间表（截止日驱动锁定，未设置则不锁） ----
    college_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="学院初审审核日（兼指导教师确认截止日）")
    university_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="校级复审审核日")
    expert_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="专家评审审核日")
    midterm_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="中期报告提交截止日")
    final_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="结题报告提交截止日")
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="比赛地点")
    contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="联系方式")
    cover_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="封面图URL")
    official_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="官方链接")
    # 状态: 0-草稿 1-报名中 2-进行中 3-已结束 4-已取消
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="比赛状态")
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="浏览次数")
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sys_user.id"), nullable=True, comment="创建人ID"
    )

    creator: Mapped[Optional["SysUser"]] = relationship("SysUser", foreign_keys=[created_by])

    __table_args__ = (
        Index("idx_competition_status", "status"),
        Index("idx_competition_level", "level"),
        Index("idx_competition_type", "competition_type"),
    )
