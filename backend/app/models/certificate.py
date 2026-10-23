"""
获奖证书ORM模型
校级竞赛获奖后由平台自动生成证书：每个获奖项目一张团队证书 + 每位成员一张个人证书
"""
from datetime import date
from typing import Optional

from sqlalchemy import BigInteger, Date, ForeignKey, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ProjCertificate(BaseModel):
    """项目获奖证书"""

    __tablename__ = "proj_certificate"

    achievement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proj_achievement.id"), nullable=False, comment="成果ID"
    )
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID"
    )
    competition_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("biz_competition.id"), nullable=True, comment="比赛ID"
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sys_user.id"), nullable=True, comment="持证人用户ID（团队证书为空）"
    )
    # 证书类型: 1-团队 2-个人
    cert_type: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, comment="证书类型: 1-团队 2-个人"
    )
    cert_no: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="证书编号"
    )
    holder_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="持证人/团队成员姓名"
    )
    competition_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="比赛名称"
    )
    project_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="项目名称"
    )
    award_level: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="奖项等级"
    )
    organizer: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="主办单位"
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, comment="发证日期")
    attachment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_attachment.id"), nullable=False, comment="证书PDF附件ID"
    )

    __table_args__ = (
        Index("idx_cert_user", "user_id"),
        Index("idx_cert_achievement", "achievement_id"),
        Index("idx_cert_competition", "competition_id"),
    )
