"""
获奖证书 业务逻辑层
校级竞赛获奖后自动生成 PDF 证书：每个获奖项目一张团队证书，每位成员一张个人证书；
证书文件登记为成果附件（biz_type=achievement），并通过站内通知发放给学生。
"""
import logging
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

from fpdf import FPDF
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Competition,
    ProjAchievement,
    ProjCertificate,
    ProjProject,
    ProjTeamMember,
    SysAttachment,
    SysUser,
)
from app.schemas.certificate import CertificateItem
from app.services.notification_service import NotificationService, NOTICE_LEVEL_SUCCESS

logger = logging.getLogger(__name__)

# 证书字体：随代码仓库存放，容器内通过 backend/app -> /app/app 挂载直接可用
FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts", "simhei.ttf"
)

CERT_TYPE_TEAM = 1
CERT_TYPE_PERSONAL = 2

_RED = (169, 32, 32)
_GOLD = (176, 141, 87)
_DARK = (51, 51, 51)
_GRAY = (130, 130, 130)


def _safe_filename(name: str) -> str:
    """去掉文件名中的非法字符，并限制长度"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip()
    return (cleaned or "获奖证书")[:80]


class CertificateService:
    """获奖证书服务"""

    # ------------------------------------------------------------------
    # PDF 渲染
    # ------------------------------------------------------------------
    @staticmethod
    def _render(
        *,
        holder_line: str,
        body_line: str,
        project_name: str,
        competition_name: str,
        award_level: str,
        organizer: str,
        issue_date: date,
        cert_no: str,
    ) -> FPDF:
        if not os.path.exists(FONT_PATH):
            raise RuntimeError(f"证书字体缺失：{FONT_PATH}")

        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.set_auto_page_break(False)
        pdf.add_font("SimHei", "", FONT_PATH)
        pdf.add_page()
        pdf.set_margins(0, 0, 0)

        # 金色双层边框
        pdf.set_draw_color(*_GOLD)
        pdf.set_line_width(1.4)
        pdf.rect(12, 12, 273, 186)
        pdf.set_line_width(0.5)
        pdf.rect(16.5, 16.5, 264, 177)

        # 标题
        pdf.set_font("SimHei", size=32)
        pdf.set_text_color(*_RED)
        pdf.set_xy(30, 30)
        pdf.cell(237, 16, "获 奖 证 书", align="C")
        pdf.set_draw_color(*_GOLD)
        pdf.set_line_width(0.8)
        pdf.line(97, 52, 200, 52)

        # 持证人 / 正文
        pdf.set_text_color(*_DARK)
        pdf.set_font("SimHei", size=15)
        pdf.set_xy(36, 64)
        pdf.multi_cell(225, 9, holder_line, align="L")

        pdf.set_font("SimHei", size=14)
        pdf.set_xy(36, 78)
        pdf.multi_cell(
            225, 10,
            f"　　{body_line}",
            align="L",
        )
        pdf.set_xy(36, max(pdf.get_y() + 2, 108))
        pdf.multi_cell(225, 10, "　　特发此证，以资鼓励。", align="L")

        # 印章（红色圆形 + 单位名称）
        cx, cy, r = 238, 158, 19
        pdf.set_draw_color(*_RED)
        pdf.set_line_width(1.0)
        pdf.ellipse(cx - r, cy - r, r * 2, r * 2, style="D")
        pdf.set_text_color(*_RED)
        pdf.set_font("SimHei", size=10)
        pdf.set_xy(cx - 18, cy - 7)
        pdf.cell(36, 6, _safe_filename(organizer or "创新创业学院"), align="C")
        pdf.set_xy(cx - 18, cy + 1)
        pdf.cell(36, 6, "（盖章）", align="C")

        # 日期 / 编号 / 说明
        pdf.set_text_color(*_DARK)
        pdf.set_font("SimHei", size=11)
        pdf.set_xy(38, 164)
        pdf.cell(80, 8, issue_date.strftime("%Y年%m月%d日"), align="L")
        pdf.set_text_color(*_GRAY)
        pdf.set_font("SimHei", size=9)
        pdf.set_xy(38, 180)
        pdf.cell(150, 6, f"证书编号：{cert_no}", align="L")
        return pdf

    # ------------------------------------------------------------------
    # 文件落盘 + 附件登记
    # ------------------------------------------------------------------
    @staticmethod
    def _store_pdf(
        db: Session, pdf: FPDF, display_name: str, achievement_id: int, operator: SysUser
    ) -> SysAttachment:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        stored = f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex}.pdf"
        # 数据库统一存 POSIX 风格相对路径，避免在 Windows 上生成时写入反斜杠导致容器内找不到文件
        rel_path = f"{Path(settings.UPLOAD_DIR).as_posix()}/{stored}"
        path = os.path.join(settings.UPLOAD_DIR, stored)
        pdf.output(path)
        att = SysAttachment(
            biz_type="achievement",
            biz_id=achievement_id,
            file_name=display_name,
            file_path=rel_path,
            file_size=os.path.getsize(path),
            file_type="application/pdf",
            file_ext="pdf",
            uploader_id=operator.id,
            uploader_name=operator.real_name,
        )
        db.add(att)
        db.flush()
        return att

    # ------------------------------------------------------------------
    # 签发
    # ------------------------------------------------------------------
    @staticmethod
    def issue_for_achievement(
        db: Session,
        achievement: ProjAchievement,
        project: ProjProject,
        comp: Competition,
        award_level: str,
        operator: SysUser,
    ) -> List[ProjCertificate]:
        """为一个竞赛获奖成果生成团队证书 + 每位成员的个人证书（不 commit）"""
        leader = db.query(SysUser).filter(SysUser.id == project.leader_id).first()
        members = db.query(ProjTeamMember).filter(
            ProjTeamMember.project_id == project.id,
            ProjTeamMember.is_deleted == 0,
        ).order_by(ProjTeamMember.id).all()

        people: List[Tuple[int, str]] = []
        if leader:
            people.append((leader.id, leader.real_name))
        for m in members:
            if m.student_id and all(m.student_id != uid for uid, _ in people):
                people.append((m.student_id, m.student_name))
        names = [n for _, n in people]
        if not names:
            return []

        issue_date = achievement.publish_date or date.today()
        organizer = comp.organizer or f"{settings.SCHOOL_NAME}创新创业学院"
        prefix = f"XJ{issue_date.year}-{comp.id:03d}-{achievement.id:05d}"
        created: List[ProjCertificate] = []

        # 1) 团队证书
        team_pdf = CertificateService._render(
            holder_line=f"{'、'.join(names)} 同学（团队）：",
            body_line=(
                f"你们团队完成的《{project.project_name}》在{organizer}主办的"
                f"“{comp.title}”中，荣获{award_level}。"
            ),
            project_name=project.project_name,
            competition_name=comp.title,
            award_level=award_level,
            organizer=organizer,
            issue_date=issue_date,
            cert_no=f"{prefix}T",
        )
        team_att = CertificateService._store_pdf(
            db, team_pdf,
            f"{_safe_filename(project.project_name)}_团队获奖证书.pdf",
            achievement.id, operator,
        )
        team_cert = ProjCertificate(
            achievement_id=achievement.id,
            project_id=project.id,
            competition_id=comp.id,
            user_id=None,
            cert_type=CERT_TYPE_TEAM,
            cert_no=f"{prefix}T",
            holder_name="、".join(names),
            competition_name=comp.title,
            project_name=project.project_name,
            award_level=award_level,
            organizer=organizer,
            issue_date=issue_date,
            attachment_id=team_att.id,
        )
        db.add(team_cert)
        db.flush()
        created.append(team_cert)

        # 2) 每人一张个人证书
        for idx, (uid, name) in enumerate(people, start=1):
            cert_no = f"{prefix}-{idx:02d}"
            pdf = CertificateService._render(
                holder_line=f"{name} 同学：",
                body_line=(
                    f"你参与的《{project.project_name}》在{organizer}主办的"
                    f"“{comp.title}”中，荣获{award_level}。"
                ),
                project_name=project.project_name,
                competition_name=comp.title,
                award_level=award_level,
                organizer=organizer,
                issue_date=issue_date,
                cert_no=cert_no,
            )
            att = CertificateService._store_pdf(
                db, pdf,
                f"{_safe_filename(name)}_{_safe_filename(comp.title)}_获奖证书.pdf",
                achievement.id, operator,
            )
            cert = ProjCertificate(
                achievement_id=achievement.id,
                project_id=project.id,
                competition_id=comp.id,
                user_id=uid,
                cert_type=CERT_TYPE_PERSONAL,
                cert_no=cert_no,
                holder_name=name,
                competition_name=comp.title,
                project_name=project.project_name,
                award_level=award_level,
                organizer=organizer,
                issue_date=issue_date,
                attachment_id=att.id,
            )
            db.add(cert)
            created.append(cert)

        # 3) 站内通知（每人一条，指向「我的证书」）
        NotificationService.push_many(
            db,
            [uid for uid, _ in people],
            title="校级竞赛获奖证书已生成",
            content=(
                f"恭喜！你参与的《{project.project_name}》在{comp.title}中荣获{award_level}，"
                f"团队证书与个人证书均已生成，可前往「我的证书」查看与下载。"
            ),
            level=NOTICE_LEVEL_SUCCESS,
            biz_type="certificate",
            biz_id=team_cert.id,
            link="/my-certificates",
        )
        return created

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @staticmethod
    def paginate_mine(
        db: Session, user_id: int, page: int, page_size: int
    ) -> Tuple[List[CertificateItem], int]:
        """我的证书：本人个人证书 + 本人参与项目的团队证书（按发证日期倒序）"""
        # 本人负责或参与的项目（团队证书 user_id 为空，需要按项目归属发放给全体成员）
        my_project_ids = db.query(ProjProject.id).filter(
            ProjProject.leader_id == user_id,
            ProjProject.is_deleted == 0,
        ).union(
            db.query(ProjTeamMember.project_id).filter(
                ProjTeamMember.student_id == user_id,
                ProjTeamMember.is_deleted == 0,
            )
        )
        q = (
            db.query(ProjCertificate, SysAttachment)
            .join(SysAttachment, SysAttachment.id == ProjCertificate.attachment_id)
            .filter(
                ProjCertificate.is_deleted == 0,
                SysAttachment.is_deleted == 0,
                or_(
                    ProjCertificate.user_id == user_id,
                    and_(
                        ProjCertificate.cert_type == CERT_TYPE_TEAM,
                        ProjCertificate.project_id.in_(my_project_ids),
                    ),
                ),
            )
        )
        total = q.count()
        rows = (
            q.order_by(ProjCertificate.issue_date.desc(), ProjCertificate.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = [
            CertificateItem(
                id=cert.id,
                cert_no=cert.cert_no,
                cert_type=cert.cert_type,
                holder_name=cert.holder_name,
                competition_name=cert.competition_name,
                project_name=cert.project_name,
                award_level=cert.award_level,
                organizer=cert.organizer,
                issue_date=cert.issue_date,
                attachment_id=cert.attachment_id,
                file_name=att.file_name,
                download_count=att.download_count or 0,
                downloaded=(att.download_count or 0) > 0,
            )
            for cert, att in rows
        ]
        return items, total
