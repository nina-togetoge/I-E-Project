# ====================================================================
# 证书域 ORM 模型（proj_certificate）
# --------------------------------------------------------------------
# 业务用途：竞赛获奖后由平台自动生成证书，
#           每个获奖项目一张团队证书（user_id 为空，按项目成员关系对全员可见），
#           每位成员再各生成一张个人证书（user_id 指向该学生）。
# 与被谁关联：achievement_id -> proj_achievement；project_id -> proj_project；
#            competition_id -> biz_competition；attachment_id -> sys_attachment（PDF）。
# 数据生命周期：软删除；证书编号 cert_no 唯一，撤销后也保留编号不复用。
# ====================================================================
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
    """
    项目获奖证书表（proj_certificate）

    业务含义：获奖项目的电子证书档案，团队证书供全员查看，个人证书归属到人。
    关键约束：cert_no 唯一（数据库 unique）；attachment_id 非空，证书必须挂 PDF。
    可见性规则：cert_type=1 时 user_id 为空，按 ProjTeamMember 关系对团队成员可见；
               cert_type=2 时按 user_id 精确到个人。
    """

    __tablename__ = "proj_certificate"

    # 来源成果：一张竞赛获奖成果可生成多张证书（团队 1 + 个人 N）
    achievement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proj_achievement.id"), nullable=False, comment="成果ID"
    )
    # 所属项目：团队证书的可见性依赖项目成员关系
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID"
    )
    # 关联比赛：可为空（非比赛类成果不生成证书）
    competition_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("biz_competition.id"), nullable=True, comment="比赛ID"
    )
    # 持证人：个人证书填学生用户ID；团队证书为空
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sys_user.id"), nullable=True, comment="持证人用户ID（团队证书为空）"
    )
    # 证书类型: 1-团队 2-个人
    cert_type: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, comment="证书类型: 1-团队 2-个人"
    )
    # 证书编号：对外唯一，生成后不复用
    cert_no: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="证书编号"
    )
    # 持证人姓名 / 团队成员姓名：快照，避免改名后证书失真
    holder_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="持证人/团队成员姓名"
    )
    # 比赛名称 / 项目名称 / 奖项等级 / 主办单位：均为生成时点的快照
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
    # 发证日期：证书正文展示
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, comment="发证日期")
    # 证书 PDF：实体文件在 Docker 卷，这里只存附件元数据 ID
    attachment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_attachment.id"), nullable=False, comment="证书PDF附件ID"
    )

    # 按人、按成果、按比赛三个维度查询证书
    __table_args__ = (
        Index("idx_cert_user", "user_id"),
        Index("idx_cert_achievement", "achievement_id"),
        Index("idx_cert_competition", "competition_id"),
    )
