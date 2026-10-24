# ============================================================================
# 创新创业大赛 业务逻辑层
# ----------------------------------------------------------------------------
# 业务功能：大赛信息（校级/省级/国家级）的增删改查与状态流转；校级比赛结束后，
#           按学院分组、按专家评审平均分排名，自动生成获奖成果与获奖证书。
# 核心表：
#   competition        大赛主表（类型、级别、状态、届次、主办方、创建人）
#   proj_project       参赛项目（competition_id、competition_session、college_id、status）
#   proj_review        专家评审记录（review_stage=专家、score、review_result）
#   proj_achievement   成果表（achievement_type=4 表示竞赛获奖）
#   proj_certificate   获奖证书（团队/个人）
#   sys_college        学院（获奖名单按学院分组展示）
#   sys_user           系统用户（创建人姓名、权限判断）
# 上游路由：app/api/v1/competition.py（列表/详情/维护/状态/生成获奖名单）
# 下游依赖：CertificateService 签发 PDF 证书、NotificationService 推送通知、
#           schemas.competition 的类型/级别/状态名称映射、security 超管判定。
# 关键约束：
#   1) 大赛的新增/编辑/删除/改状态仅超级管理员可操作；
#   2) 学生端只展示报名中/进行中（status=1/2），已结束/已取消视为下架；
#   3) 自动获奖仅支持校级比赛（level=1），省级/国家级只能手工登记证书；
#   4) 排名池按“同一比赛 + 同一届次 + 已立项及之后”筛选，跨院组队归负责人学院；
#   5) 自动生成可重复触发，触发时先清理上一轮自动成果及证书，保证幂等。
# ============================================================================
import logging
from typing import Optional, Tuple, List
from datetime import date, datetime

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models import (
    Competition, SysUser, SysCollege, ProjProject, ProjReview, ProjAchievement,
    ProjCertificate, SysAttachment,
)
from app.schemas.competition import (
    CompetitionCreate, CompetitionUpdate,
    CompetitionListItem, CompetitionDetail,
    COMPETITION_TYPE_NAME, COMPETITION_LEVEL_NAME, COMPETITION_STATUS_NAME,
)
from app.schemas.review import REVIEW_STAGE_EXPERT
from app.core.security import is_super_admin
from app.services.certificate_service import CertificateService

logger = logging.getLogger(__name__)


# 自动获奖分配常量
# 名次 → 奖项名称：只对前 3 名授予一/二/三等奖，其余获奖项目统一为参与奖。
AWARD_LEVEL_NAMES = {1: "校级一等奖", 2: "校级二等奖", 3: "校级三等奖"}
PARTICIPATION_AWARD_NAME = "参与奖"
PARTICIPATION_AWARD_COUNT = 7  # 三等奖之后顺次取的参与奖数量（不并列）
# 自动生成成果的摘要前缀，用于重复触发时识别并清理上一轮自动数据
AUTO_AWARD_SUMMARY_PREFIX = "[自动生成]"
# 参与自动分配的项目状态：已立项及之后（专家评审已完成，具备评分）
# 6=已立项 7=中期检查中 8=中期检查通过 9=已结题，均属于“已立项之后”的有效项目
AWARD_ELIGIBLE_STATUS = (6, 7, 8, 9)


class CompetitionService:
    """大赛业务服务。

    查询类方法为只读；创建/更新/删除/生成获奖名单等写操作在方法内提交事务。
    获奖分配规则集中在 generate_awards，便于审计与调整。
    """

    @staticmethod
    def _fill_names(item: Competition) -> Competition:
        """把数据库中的枚举值翻译成中文名称，供前端直接展示。

        参数：item 大赛 ORM 对象（会被原地写入三个名称属性）。
        返回：同一个对象，便于链式调用。
        注意：未知取值统一返回“未知”，避免前端出现空白或报错。
        """
        item.competition_type_name = COMPETITION_TYPE_NAME.get(item.competition_type, "未知")
        item.level_name = COMPETITION_LEVEL_NAME.get(item.level, "未知")
        item.status_name = COMPETITION_STATUS_NAME.get(item.status, "未知")
        return item

    @staticmethod
    def paginate(
        db: Session,
        page: int,
        page_size: int,
        keyword: Optional[str] = None,
        competition_type: Optional[int] = None,
        level: Optional[int] = None,
        status: Optional[int] = None,
        only_published: bool = False,
    ) -> Tuple[List[Competition], int]:
        """分页查询大赛列表。

        参数：
            db: 数据库会话。
            page / page_size: 页码（从 1 开始）与每页条数。
            keyword: 模糊匹配标题 / 主办方 / 描述。
            competition_type / level / status: 按类型、级别、状态精确筛选。
            only_published: 学生端视角，仅返回可参与的比赛（报名中/进行中）。
        返回：
            (当前页大赛列表, 总条数)。
        注意：
            名称字段在查询后逐条填充；列表按创建时间倒序，最新比赛优先展示。
        """
        query = db.query(Competition).filter(Competition.is_deleted == 0)

        if only_published:
            # 学生端只看可参与的（报名中/进行中）；已结束(3)/已取消(4)即"下架"，不再展示
            query = query.filter(Competition.status.in_([1, 2]))

        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    Competition.title.like(like),
                    Competition.organizer.like(like),
                    Competition.description.like(like),
                )
            )
        if competition_type is not None:
            query = query.filter(Competition.competition_type == competition_type)
        if level is not None:
            query = query.filter(Competition.level == level)
        if status is not None:
            query = query.filter(Competition.status == status)

        total = query.count()
        items = (
            query.order_by(Competition.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        for it in items:
            CompetitionService._fill_names(it)
        return items, total

    @staticmethod
    def get_detail(db: Session, comp_id: int, increment_view: bool = False,
                   only_published: bool = False) -> Competition:
        """获取大赛详情。

        参数：
            db: 数据库会话。
            comp_id: 大赛 id。
            increment_view: 是否累加浏览量（详情页首次打开时使用）。
            only_published: 学生端视角，仅允许查看报名中/进行中/已结束，
                            草稿(0)与已取消(4)视为不存在。
        返回：
            填充了中文名称与创建人姓名的大赛对象。
        异常：
            不存在、已软删除或不可见 → BizException("比赛不存在或已删除")。
        副作用：
            increment_view=True 时会写库并刷新对象。
        """
        comp = (
            db.query(Competition)
            .filter(Competition.id == comp_id, Competition.is_deleted == 0)
            .first()
        )
        if not comp or (only_published and comp.status not in (1, 2, 3)):
            from app.core.exceptions import BizException
            raise BizException("比赛不存在或已删除")
        CompetitionService._fill_names(comp)
        if increment_view:
            comp.view_count = (comp.view_count or 0) + 1
            db.commit()
            db.refresh(comp)
        # 创建人姓名
        if comp.created_by:
            creator = db.query(SysUser).filter(SysUser.id == comp.created_by).first()
            comp.creator_name = creator.real_name if creator else None
        return comp

    @staticmethod
    def create(db: Session, req: CompetitionCreate, operator: SysUser) -> Competition:
        """创建大赛。

        参数：db 会话、创建表单、当前操作人。
        返回：已落库并填充名称的新大赛对象。
        权限：仅超级管理员。
        异常：非超管 → BizException("仅超级管理员可创建比赛")。
        副作用：写入 created_by 并提交事务。
        """
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅超级管理员可创建比赛")
        comp = Competition(**req.model_dump(), created_by=operator.id)
        db.add(comp)
        db.commit()
        db.refresh(comp)
        CompetitionService._fill_names(comp)
        return comp

    @staticmethod
    def update(db: Session, comp_id: int, req: CompetitionUpdate, operator: SysUser) -> Competition:
        """更新大赛信息（全字段覆盖式更新）。

        参数：db 会话、大赛 id、更新表单、当前操作人。
        返回：更新后并填充名称的大赛对象。
        权限：仅超级管理员。
        异常：非超管 → BizException；大赛不存在 → 由 get_detail 抛出。
        注意：req.model_dump() 未排除未设置字段，调用方需传入完整表单。
        """
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅超级管理员可编辑比赛")
        comp = CompetitionService.get_detail(db, comp_id)
        for k, v in req.model_dump().items():
            setattr(comp, k, v)
        db.commit()
        db.refresh(comp)
        CompetitionService._fill_names(comp)
        return comp

    @staticmethod
    def delete(db: Session, comp_id: int, operator: SysUser) -> None:
        """删除大赛（软删除）。

        参数：db 会话、大赛 id、当前操作人。
        返回：无。
        权限：仅超级管理员。
        注意：只置 is_deleted=1，保留历史项目关联与获奖数据，便于追溯。
        """
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅超级管理员可删除比赛")
        comp = CompetitionService.get_detail(db, comp_id)
        comp.is_deleted = 1
        db.commit()

    @staticmethod
    def update_status(db: Session, comp_id: int, status: int, operator: SysUser) -> Competition:
        """修改大赛状态（草稿/报名中/进行中/已结束/已取消）。

        参数：db 会话、大赛 id、目标状态值、当前操作人。
        返回：更新后的大赛对象。
        权限：仅超级管理员。
        异常：非超管 / 状态值不在枚举内 → BizException。
        注意：状态值必须存在于 COMPETITION_STATUS_NAME，防止写入脏数据。
        """
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅超级管理员可修改比赛状态")
        if status not in COMPETITION_STATUS_NAME:
            from app.core.exceptions import BizException
            raise BizException("无效的比赛状态")
        comp = CompetitionService.get_detail(db, comp_id)
        comp.status = status
        db.commit()
        db.refresh(comp)
        CompetitionService._fill_names(comp)
        return comp

    # ---- 获奖名单自动生成 ----
    @staticmethod
    def generate_awards(db: Session, comp_id: int, operator: SysUser) -> dict:
        """为校级比赛自动生成获奖名单（管理员手动触发，可重复触发以刷新）。

        规则：排名池 = 本院 + 同比赛 + 同一届（跨院组队归项目负责人学院）；
        分数取专家评审平均分；名次 1/2/3 → 校级一/二/三等奖，其后顺次取 7 个参与奖（不并列）；
        省级/国家级比赛不支持自动分配，仅可手工登记获奖证书。
        生成的获奖成果(类型=竞赛获奖)会计入项目结题的成果数量门槛。

        参数：
            db: 数据库会话。
            comp_id: 大赛 id，必须是校级（level=1）。
            operator: 当前操作人，仅超级管理员可触发。
        返回：
            统计字典：比赛信息、获奖总数、按学院分组的明细
            （项目 id/名称、平均分、名次、奖项）。
        异常：
            非超管 / 非校级比赛 → BizException。
        副作用：
            1) 软删除上一轮自动生成的获奖成果及其证书、证书附件；
            2) 新增获奖成果（achievement_type=4）；
            3) 逐项目签发团队/个人证书并推送站内通知；
            4) 结束时统一提交事务。
        注意：
            证书生成失败只记 warning、不中断名单生成，保证主流程可用；
            同分时按提交时间、项目 id 升序兜底，避免名次并列导致奖项边界不稳定。
        """
        from app.core.exceptions import BizException
        if not is_super_admin(operator):
            raise BizException("仅超级管理员可生成获奖名单")
        comp = CompetitionService.get_detail(db, comp_id)
        # 自动分配依赖校级统一排名规则；省级/国家级获奖名额由主办方决定，改为手工登记
        # level=1 是校级，其余（2 省级 / 3 国家级）不进入自动分配流程
        if comp.level != 1:
            raise BizException("仅校级比赛支持自动生成获奖名单，省级/国家级请手工登记获奖证书")

        # 排名池：关联本比赛（届次一致）、已立项及之后的项目
        q = db.query(ProjProject).filter(
            ProjProject.competition_id == comp.id,
            ProjProject.is_deleted == 0,
            ProjProject.status.in_(AWARD_ELIGIBLE_STATUS),
        )
        if comp.session:
            q = q.filter(ProjProject.competition_session == comp.session)
        projects = q.all()

        # 幂等刷新：先软删"本比赛关联项目"此前自动生成的获奖成果，再按最新排名重建
        # 通过 summary 前缀区分自动/手工数据，只清理自动生成部分，不误删管理员手工登记的获奖
        proj_ids = [p.id for p in projects]
        if proj_ids:
            old_ach_ids = [row[0] for row in db.query(ProjAchievement.id).filter(
                ProjAchievement.project_id.in_(proj_ids),
                ProjAchievement.achievement_type == 4,
                ProjAchievement.summary.like(f"{AUTO_AWARD_SUMMARY_PREFIX}%"),
                ProjAchievement.is_deleted == 0,
            ).all()]
            if old_ach_ids:
                # 旧证书/附件一并软删，避免刷新名次后「我的证书」里残留重复证书
                old_certs = db.query(ProjCertificate).filter(
                    ProjCertificate.achievement_id.in_(old_ach_ids),
                    ProjCertificate.is_deleted == 0,
                ).all()
                old_att_ids = [c.attachment_id for c in old_certs if c.attachment_id]
                for c in old_certs:
                    c.is_deleted = 1
                if old_att_ids:
                    db.query(SysAttachment).filter(
                        SysAttachment.id.in_(old_att_ids)
                    ).update({SysAttachment.is_deleted: 1}, synchronize_session=False)
                db.query(ProjAchievement).filter(
                    ProjAchievement.id.in_(old_ach_ids),
                ).update({ProjAchievement.is_deleted: 1}, synchronize_session=False)

        # 按负责人学院分组（跨院组队归项目负责人学院）
        groups: dict = {}
        for p in projects:
            groups.setdefault(p.college_id, []).append(p)
        college_names = dict(db.query(SysCollege.id, SysCollege.college_name).filter(
            SysCollege.id.in_(list(groups.keys()) or [0])
        ).all())
        # 用 [0] 兜底空分组，避免 in_([]) 生成非法 SQL；查询结果转 dict 供返回时取名

        result_groups = []
        total_awarded = 0
        # 每个学院独立排名、独立分配奖项，避免小学院项目被大院项目挤占名额
        for college_id, plist in groups.items():
            scored = []
            for p in plist:
                # 专家评审平均分：排除无效评审(review_result=99)与空分数，
                # 避免被撤回/作废的评分拉低平均分，影响名次与奖项边界
                avg = db.query(func.avg(ProjReview.score)).filter(
                    ProjReview.project_id == p.id,
                    ProjReview.review_stage == REVIEW_STAGE_EXPERT,
                    ProjReview.review_result != 99,
                    ProjReview.is_deleted == 0,
                    ProjReview.score.isnot(None),
                ).scalar()
                scored.append((p, float(avg) if avg is not None else 0.0))
            # 排序：分数降序；同分按提交时间/ID 升序，保证名次不并列
            # 提交时间缺失的历史数据回退到 datetime.min，再由 id 兜底，排序结果始终确定
            scored.sort(key=lambda t: (-t[1], t[0].submit_time or datetime.min, t[0].id))

            items = []
            # 奖项切分：1~3 名 → 一/二/三等奖；4~10 名 → 参与奖；11 名及以后不获奖
            for idx, (p, score) in enumerate(scored, start=1):
                if idx <= 3:
                    award = AWARD_LEVEL_NAMES[idx]
                elif idx <= 3 + PARTICIPATION_AWARD_COUNT:
                    award = PARTICIPATION_AWARD_NAME
                else:
                    break  # 超出获奖范围，不再奖励
                title = (f"{comp.title}（{comp.session}）{award}" if comp.session
                         else f"{comp.title}{award}")
                ach = ProjAchievement(
                    project_id=p.id,
                    achievement_type=4,  # 竞赛获奖
                    title=title,
                    level=1,
                    award_level=award,
                    publisher=comp.organizer,
                    publish_date=date.today(),
                    summary=(f"{AUTO_AWARD_SUMMARY_PREFIX}比赛:{comp.title} "
                             f"届次:{comp.session or '—'} 名次:{idx} 平均分:{score:.2f}"),
                )
                db.add(ach)
                db.flush()
                items.append({
                    "project_id": p.id,
                    "project_name": p.project_name,
                    "average_score": round(score, 2),
                    "rank": idx,
                    "award_level": award,
                })
                # 校级证书：每个获奖项目生成团队证书 + 每位成员个人证书，并推送站内通知
                # 签发放在 try 中隔离：字体缺失/磁盘异常只影响当前项目，不阻断整批名单
                try:
                    CertificateService.issue_for_achievement(db, ach, p, comp, award, operator)
                except Exception as exc:  # 证书生成失败不应阻断获奖名单生成
                    logger.warning("生成获奖证书失败 project=%s: %s", p.id, exc)
                total_awarded += 1
            result_groups.append({
                "college_id": college_id,
                "college_name": college_names.get(college_id),
                # 每院的 items 保持按名次升序，前端可直接渲染“学院-名次-奖项”表格
                "items": items,
            })

        db.commit()
        return {
            "competition_id": comp.id,
            "competition_title": comp.title,
            "session": comp.session,
            "total_awarded": total_awarded,
            "groups": result_groups,
        }
