# ============================================================================
# 获奖证书 业务逻辑层
# ----------------------------------------------------------------------------
# 业务功能：校级竞赛获奖后自动渲染 PDF 证书：每个获奖项目一张团队证书，
#           每位成员一张个人证书；证书文件登记为成果附件，并通过站内通知发放。
# 核心表：
#   proj_certificate  证书台账（证书编号、类型、持证人、关联成果/项目/比赛、附件）
#   sys_attachment    证书 PDF 文件（biz_type="achievement"，biz_id=成果 id）
#   proj_achievement  获奖成果（证书挂在成果下，便于结题成果统计）
#   proj_project      项目（取项目名称、负责人）
#   proj_team_member  团队成员（个人证书发放范围）
#   sys_notification  站内通知（每人一条，跳转「我的证书」）
# 上游路由：app/api/v1/certificate.py（我的证书列表）；直接调用方为
#           CompetitionService.generate_awards。
# 下游依赖：fpdf2 渲染、app.core.config 上传目录/学校名称、NotificationService。
# 关键约束：
#   1) 证书字体必须随仓库提供（assets/fonts/simhei.ttf），缺失时直接报错，
#      不静默生成乱码 PDF；
#   2) 证书编号全局唯一：XJ+年份-比赛id-成果id，团队证书加 T 后缀，
#      个人证书加两位成员序号；
#   3) 团队证书 user_id 为空，靠项目成员关系发放给全体成员；
#   4) 签发方法只 flush 不 commit，由调用方统一提交，保证获奖名单与证书同事务；
#   5) 单个项目证书生成失败不应阻断整批获奖名单（由调用方 try/except 隔离）。
# ============================================================================
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
# 不能依赖服务器系统字体：容器基础镜像通常不含中文字体，缺失会导致证书文字变方块
FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts", "simhei.ttf"
)

# 证书类型：1=团队证书（发全体成员） 2=个人证书（发单个学生）
CERT_TYPE_TEAM = 1
CERT_TYPE_PERSONAL = 2

# 证书配色：红（标题/印章）、金（边框）、深灰（正文）、浅灰（编号）
_RED = (169, 32, 32)
_GOLD = (176, 141, 87)
_DARK = (51, 51, 51)
_GRAY = (130, 130, 130)


def _safe_filename(name: str) -> str:
    """清洗文件名，兼容 Windows/Linux 文件系统与 ZIP 打包。

    功能：替换路径分隔符、通配符、控制字符为下划线，并截断到 80 字符。
    参数：name 原始展示名（项目名/人名/主办方）。
    返回：可安全落盘的文件名；清洗后为空时回退为“获奖证书”。
    """
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip()
    return (cleaned or "获奖证书")[:80]


class CertificateService:
    """获奖证书服务：PDF 渲染、文件落盘登记、团队/个人证书签发与查询。

    所有方法为静态方法；签发方法只 flush 不 commit，事务边界由调用方控制。
    """

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
        """渲染一张 A4 横向获奖证书 PDF（内存对象，不直接落盘）。

        参数（均为关键字参数，调用处必须写参数名以避免文案错位）：
            holder_line: 抬头行，团队证书为“甲、乙 同学（团队）：”，个人证书为“甲 同学：”。
            body_line: 正文获奖描述。
            project_name / competition_name / award_level / organizer: 证书正文要素。
            issue_date: 发证日期（默认为成果发布日期）。
            cert_no: 证书编号，打印在底部左侧。
        返回：
            已排版的 FPDF 对象，可直接 output 到文件。
        异常：
            字体文件缺失 → RuntimeError；此时不生成 PDF，避免中文变成乱码方块。
        注意：
            A4 横向尺寸为 297x210mm；页面边距置 0，所有坐标按绝对毫米定位，
            因此文字长度超限时会换行/溢出，模板文案需保持简短。
        """
        if not os.path.exists(FONT_PATH):
            raise RuntimeError(f"证书字体缺失：{FONT_PATH}")

        # 版式采用绝对坐标（单位 mm），各区域固定如下：
        #   外边框 12~285 x 12~198；标题区约 y=30；正文区 x=36 起；
        #   日期 y=164；证书编号 y=180；印章圆心 (238,158)。
        # 坐标与 A4 横向页面强绑定，调整纸张方向或尺寸时必须同步修改。
        # 横向 A4 更适合放长项目名与多人姓名；固定版式不允许自动分页，避免内容溢出到第二页
        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.set_auto_page_break(False)
        # 必须在写任何文字前注册中文字体，否则默认字体无法渲染汉字
        pdf.add_font("SimHei", "", FONT_PATH)
        pdf.add_page()
        # 页边距归零后完全由上面的绝对坐标控制版式，避免默认边距叠加导致内容错位
        pdf.set_margins(0, 0, 0)

        # 金色双层边框：外框粗、内框细，形成证书的正式感与层次
        pdf.set_draw_color(*_GOLD)
        pdf.set_line_width(1.4)
        pdf.rect(12, 12, 273, 186)
        pdf.set_line_width(0.5)
        # 内框与外框留 4.5mm 间距，双线结构在打印时不会糊成一条粗边
        pdf.rect(16.5, 16.5, 264, 177)

        # 标题
        # 标题字号最大、红色居中，并用金线分隔，形成视觉焦点
        pdf.set_font("SimHei", size=32)
        pdf.set_text_color(*_RED)
        pdf.set_xy(30, 30)
        pdf.cell(237, 16, "获 奖 证 书", align="C")
        pdf.set_draw_color(*_GOLD)
        pdf.set_line_width(0.8)
        # 金线宽度与标题文字外沿对齐，起到分隔标题与正文的装饰作用
        pdf.line(97, 52, 200, 52)

        # 持证人 / 正文
        # multi_cell 负责长姓名/长项目名换行；正文前留全角缩进，符合中文公文排版习惯
        pdf.set_text_color(*_DARK)
        pdf.set_font("SimHei", size=15)
        pdf.set_xy(36, 64)
        # 抬头区最高优先展示持证人；团队证书会一次性列出全部成员姓名
        pdf.multi_cell(225, 9, holder_line, align="L")

        pdf.set_font("SimHei", size=14)
        pdf.set_xy(36, 78)
        # 正文必须包含项目名、比赛名、奖项、主办方四要素，缺一证书都不具备证明力
        pdf.multi_cell(
            225, 10,
            f"　　{body_line}",
            align="L",
        )
        pdf.set_xy(36, max(pdf.get_y() + 2, 108))
        # “特发此证”固定在正文下方至少 108mm 处，短文案不会与落款区重叠
        pdf.multi_cell(225, 10, "　　特发此证，以资鼓励。", align="L")

        # 印章（红色圆形 + 单位名称）
        # 用红色圆环模拟公章，单位名过长时经 _safe_filename 清洗并限制在 36mm 内
        cx, cy, r = 238, 158, 19
        pdf.set_draw_color(*_RED)
        pdf.set_line_width(1.0)
        # 印章固定右下角，不随正文长度浮动，保证所有证书的落款位置一致
        pdf.ellipse(cx - r, cy - r, r * 2, r * 2, style="D")
        pdf.set_text_color(*_RED)
        pdf.set_font("SimHei", size=10)
        pdf.set_xy(cx - 18, cy - 7)
        pdf.cell(36, 6, _safe_filename(organizer or "创新创业学院"), align="C")
        pdf.set_xy(cx - 18, cy + 1)
        pdf.cell(36, 6, "（盖章）", align="C")

        # 日期 / 编号 / 说明
        # 日期靠左、编号靠底部，编号独占一行便于人工核验证书真伪
        pdf.set_text_color(*_DARK)
        pdf.set_font("SimHei", size=11)
        pdf.set_xy(38, 164)
        # 中文日期格式与纸质证书一致，避免使用 ISO 格式造成观感不正式
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
        """把内存 PDF 写入上传目录，并登记一条成果附件记录。

        参数：
            db: 数据库会话。
            pdf: 已渲染的 FPDF 对象。
            display_name: 展示文件名（含中文，落盘前会另取随机名）。
            achievement_id: 所属成果 id，作为附件的业务归属。
            operator: 上传人（即触发签发的管理员）。
        返回：
            已 flush 取得 id 的 SysAttachment（biz_type=achievement）。
        副作用：
            1) 创建上传目录（若不存在）；
            2) 以“日期_随机串.pdf”落盘，避免中文/重名冲突；
            3) 数据库记录 POSIX 风格相对路径，兼容 Windows 与容器环境。
        注意：
            只 flush 不 commit，由调用方统一提交，保证文件记录与证书同事务。
        """
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        # 落盘名用“日期 + UUID”：中文名、重名、路径注入都不会影响实际存储
        stored = f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex}.pdf"
        # 数据库统一存 POSIX 风格相对路径，避免在 Windows 上生成时写入反斜杠导致容器内找不到文件
        rel_path = f"{Path(settings.UPLOAD_DIR).as_posix()}/{stored}"
        path = os.path.join(settings.UPLOAD_DIR, stored)
        # 先落盘再登记附件：写文件失败会直接抛异常，不会留下“有记录无文件”的脏数据
        pdf.output(path)
        # 展示名与物理路径分离：用户看到中文名，系统按随机文件名安全读取
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
            # uploader 记录签发管理员，便于后续审计“证书由谁生成”
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
        """为一个竞赛获奖成果生成团队证书 + 每位成员的个人证书（不 commit）。

        参数：
            db: 数据库会话。
            achievement: 获奖成果（提供 id、发布日期）。
            project: 获奖项目（提供名称、负责人）。
            comp: 大赛（提供名称、主办方）。
            award_level: 奖项名称，如“校级一等奖”。
            operator: 执行签发的管理员，作为 PDF 上传人。
        返回：
            新创建的 ProjCertificate 列表（团队证书在首位）；无有效持证人时返回空列表。
        副作用：
            每个持证人写一条证书、一份 PDF 附件；并向全体成员推送一条站内通知。
        注意：
            1) 本方法只 flush，不 commit，事务由 generate_awards 统一提交；
            2) 负责人与团队成员可能重复，按 student_id 去重，避免同一人拿两份个人证书；
            3) 团队证书 user_id 置空，查询时按项目成员关系对全员可见；
            4) 任何异常向上抛出，由调用方隔离，防止单项目失败影响整批名单。
        """
        # 负责人优先列入持证人名单：即使团队成员表未同步，也能保证至少有一张个人证书
        leader = db.query(SysUser).filter(SysUser.id == project.leader_id).first()
        members = db.query(ProjTeamMember).filter(
            ProjTeamMember.project_id == project.id,
            ProjTeamMember.is_deleted == 0,
        ).order_by(ProjTeamMember.id).all()

        people: List[Tuple[int, str]] = []
        # 持证人列表顺序固定为“负责人优先，其余按成员表 id”，保证证书序号可复现
        if leader:
            people.append((leader.id, leader.real_name))
        for m in members:
            # 负责人可能也在成员表中，按 student_id 去重，避免重复签发个人证书
            if m.student_id and all(m.student_id != uid for uid, _ in people):
                people.append((m.student_id, m.student_name))
        names = [n for _, n in people]
        if not names:
            # 无负责人且无成员时不生成证书，避免出现空持证人的无效 PDF
            return []

        issue_date = achievement.publish_date or date.today()
        # 比赛未填主办方时回退到“学校 + 创新创业学院”，保证印章与正文不出现空单位
        organizer = comp.organizer or f"{settings.SCHOOL_NAME}创新创业学院"
        # 证书编号规则：XJ+年份-比赛id(3位)-成果id(5位)，天然按比赛/成果分桶；
        # 团队证书后缀 T，个人证书追加两位成员序号，保证同一成果下不重号。
        prefix = f"XJ{issue_date.year}-{comp.id:03d}-{achievement.id:05d}"
        created: List[ProjCertificate] = []

        # 1) 团队证书
        # 团队证书为全体成员共有，user_id 留空，持有人名单用顿号拼接
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
            # 展示名包含项目名，下载后用户能直接辨认；落盘名由 _store_pdf 另外随机生成
            f"{_safe_filename(project.project_name)}_团队获奖证书.pdf",
            achievement.id, operator,
        )
        team_cert = ProjCertificate(
            achievement_id=achievement.id,
            project_id=project.id,
            competition_id=comp.id,
            user_id=None,
            # 团队证书类型标记为 1，列表查询据此对项目全体成员放开可见性
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
        # flush 取得团队证书 id，后面推送通知时作为 biz_id 引用
        db.flush()
        created.append(team_cert)

        # 2) 每人一张个人证书
        # 序号按 people 顺序（负责人优先、再按团队成员 id）稳定生成，重复触发时编号不变
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
                # 个人证书文件名带姓名与比赛名，便于学生下载后在本地区分多张证书
                f"{_safe_filename(name)}_{_safe_filename(comp.title)}_获奖证书.pdf",
                achievement.id, operator,
            )
            cert = ProjCertificate(
                achievement_id=achievement.id,
                project_id=project.id,
                competition_id=comp.id,
                # 个人证书的 user_id 落为成员用户 id，学生端“我的证书”据此精确匹配
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
        # 在证书落库后统一推送，biz_id 指向团队证书，便于前端按业务聚合与跳转
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
        """我的证书：本人个人证书 + 本人参与项目的团队证书（按发证日期倒序）。

        参数：
            db: 数据库会话。
            user_id: 当前登录学生的用户 id。
            page / page_size: 页码（从 1 开始）与每页条数。
        返回：
            (CertificateItem 列表, 总条数)；每条含文件名、下载次数与是否已下载。
        权限：
            只返回与本人相关证书：个人证书按 user_id 匹配；团队证书按“本人负责或
            参与的项目”匹配，因此团队证书无需为每个成员复制一份台账。
        注意：
            已软删除的证书或附件不返回（附件缺失会导致无法下载，故一起过滤）。
        """
        # 本人负责或参与的项目（团队证书 user_id 为空，需要按项目归属发放给全体成员）
        # union 自带去重：负责人同时是团队成员时，项目 id 在子查询中不会重复
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
            # 关联附件表：列表需要文件名/下载次数，同时过滤掉附件已删除的证书
            .join(SysAttachment, SysAttachment.id == ProjCertificate.attachment_id)
            .filter(
                ProjCertificate.is_deleted == 0,
                SysAttachment.is_deleted == 0,
                or_(
                    # 个人证书按接收人匹配；团队证书只要属于本人参与的项目，即对本人可见
                    ProjCertificate.user_id == user_id,
                    and_(
                        ProjCertificate.cert_type == CERT_TYPE_TEAM,
                        ProjCertificate.project_id.in_(my_project_ids),
                    ),
                ),
            )
        )
        total = q.count()
        # 总数与列表使用同一组过滤条件，保证分页器页码与实际数据一致
        # 发证日期倒序；同一天再按 id 倒序兜底，保证分页顺序稳定
        rows = (
            q.order_by(ProjCertificate.issue_date.desc(), ProjCertificate.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        items = [
            # 组装列表项时复用附件记录，避免前端再发一次请求查文件名/下载状态
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
                # 已下载标记由下载次数推导，不额外维护状态字段，避免两处状态不一致
                downloaded=(att.download_count or 0) > 0,
            )
            for cert, att in rows
        ]
        return items, total
