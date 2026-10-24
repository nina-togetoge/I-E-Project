# ====================================================================
# 赛事域 ORM 模型（biz_competition）
# --------------------------------------------------------------------
# 业务用途：承载大创、学科竞赛等比赛主数据，包括报名期、赛程日期、
# 以及驱动项目流程锁定的各阶段审核日（截止日到了即锁定变更）。
# 与被谁关联：ProjProject.competition_id 多对一引用；ProjCertificate.competition_id 同样引用。
# 数据生命周期：比赛为长期主数据，软删除（is_deleted）后历史项目与证书仍可回显名称。
# ====================================================================
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
    """
    创新创业大赛表（biz_competition）

    业务含义：比赛主数据，既是项目申报时的"参赛选择"，也是赛程与流程截止日的配置源。
    关键约束：无唯一业务键；同一赛事不同届次用 session 区分。
    注意：level 的 1校级/2省级/3国家级 与 ProjProject.project_level 的
          1院级/2校级/3省级/4国家级 含义不同，禁止直接比较。
    """
    __tablename__ = "biz_competition"

    # 比赛名称：列表主标题
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="比赛名称")
    # 届次（如 2026届）：同名前缀赛事靠它区分年度场次
    session: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="届次(如 2026届)")
    # 比赛类型: 1-创新训练类 2-创业实践类 3-学科竞赛类 4-综合类
    competition_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="比赛类型")
    # 级别: 1-校级 2-省级 3-国家级
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="比赛级别")
    # 主办/承办方：证书落款与详情展示
    organizer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="主办方")
    co_organizer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="承办方")
    # 详情富文本字段：简介/参赛要求/奖项设置
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="比赛简介")
    requirements: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="参赛要求")
    rewards: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="奖项设置")
    # 报名与比赛起止日期：用于展示倒计时与自动切换状态
    registration_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="报名开始日期")
    registration_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="报名截止日期")
    competition_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="比赛开始日期")
    competition_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="比赛结束日期")
    # ---- 项目流程时间表（截止日驱动锁定，未设置则不锁） ----
    # 学院初审日兼教师确认截止日：超过此日不允许再变更/延期
    college_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="学院初审审核日（兼指导教师确认截止日）")
    # 校级复审日：控制校级阶段的时间窗口
    university_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="校级复审审核日")
    # 专家评审日：控制专家打分截止时间
    expert_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="专家评审审核日")
    # 中期报告 / 结题报告提交截止日：到期后提交入口关闭
    midterm_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="中期报告提交截止日")
    final_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="结题报告提交截止日")
    # 展示信息：地点/联系方式/封面/官网
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="比赛地点")
    contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="联系方式")
    cover_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="封面图URL")
    official_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="官方链接")
    # 状态: 0-草稿 1-报名中 2-进行中 3-已结束 4-已取消
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="比赛状态")
    # 浏览次数：热度排序
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="浏览次数")
    # 创建人：管理员发布比赛时记录，用于追责
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sys_user.id"), nullable=True, comment="创建人ID"
    )

    # 创建人（多对一，只读展示）：foreign_keys 显式指定，避免与其他 user 关联歧义
    creator: Mapped[Optional["SysUser"]] = relationship("SysUser", foreign_keys=[created_by])

    # 状态/级别/类型索引支撑列表筛选与分类统计
    __table_args__ = (
        Index("idx_competition_status", "status"),
        Index("idx_competition_level", "level"),
        Index("idx_competition_type", "competition_type"),
    )
