"""
创新创业大赛 业务逻辑层
"""
from typing import Optional, Tuple, List
from datetime import date, datetime

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models import (
    Competition, SysUser, SysCollege, ProjProject, ProjReview, ProjAchievement,
)
from app.schemas.competition import (
    CompetitionCreate, CompetitionUpdate,
    CompetitionListItem, CompetitionDetail,
    COMPETITION_TYPE_NAME, COMPETITION_LEVEL_NAME, COMPETITION_STATUS_NAME,
)
from app.schemas.review import REVIEW_STAGE_EXPERT
from app.core.security import is_super_admin


# 自动获奖分配常量
AWARD_LEVEL_NAMES = {1: "校级一等奖", 2: "校级二等奖", 3: "校级三等奖"}
PARTICIPATION_AWARD_NAME = "参与奖"
PARTICIPATION_AWARD_COUNT = 7  # 三等奖之后顺次取的参与奖数量（不并列）
AUTO_AWARD_SUMMARY_PREFIX = "[自动生成]"
# 参与自动分配的项目状态：已立项及之后（专家评审已完成，具备评分）
AWARD_ELIGIBLE_STATUS = (6, 7, 8, 9)


class CompetitionService:
    """大赛服务"""

    @staticmethod
    def _fill_names(item: Competition) -> Competition:
        """填充类型/级别/状态名称"""
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
        """分页查询大赛列表"""
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
        """获取大赛详情；only_published=True 时未发布(草稿/已取消)视为不存在"""
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
        """创建大赛（仅超级管理员）"""
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
        """更新大赛（仅超级管理员）"""
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
        """删除大赛（软删除，仅超级管理员）"""
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅超级管理员可删除比赛")
        comp = CompetitionService.get_detail(db, comp_id)
        comp.is_deleted = 1
        db.commit()

    @staticmethod
    def update_status(db: Session, comp_id: int, status: int, operator: SysUser) -> Competition:
        """更新比赛状态（仅超级管理员）"""
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
        """
        from app.core.exceptions import BizException
        if not is_super_admin(operator):
            raise BizException("仅超级管理员可生成获奖名单")
        comp = CompetitionService.get_detail(db, comp_id)
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
        proj_ids = [p.id for p in projects]
        if proj_ids:
            db.query(ProjAchievement).filter(
                ProjAchievement.project_id.in_(proj_ids),
                ProjAchievement.achievement_type == 4,
                ProjAchievement.summary.like(f"{AUTO_AWARD_SUMMARY_PREFIX}%"),
                ProjAchievement.is_deleted == 0,
            ).update({ProjAchievement.is_deleted: 1}, synchronize_session=False)

        # 按负责人学院分组（跨院组队归项目负责人学院）
        groups: dict = {}
        for p in projects:
            groups.setdefault(p.college_id, []).append(p)
        college_names = dict(db.query(SysCollege.id, SysCollege.college_name).filter(
            SysCollege.id.in_(list(groups.keys()) or [0])
        ).all())

        result_groups = []
        total_awarded = 0
        for college_id, plist in groups.items():
            scored = []
            for p in plist:
                avg = db.query(func.avg(ProjReview.score)).filter(
                    ProjReview.project_id == p.id,
                    ProjReview.review_stage == REVIEW_STAGE_EXPERT,
                    ProjReview.review_result != 99,
                    ProjReview.is_deleted == 0,
                    ProjReview.score.isnot(None),
                ).scalar()
                scored.append((p, float(avg) if avg is not None else 0.0))
            # 排序：分数降序；同分按提交时间/ID 升序，保证名次不并列
            scored.sort(key=lambda t: (-t[1], t[0].submit_time or datetime.min, t[0].id))

            items = []
            for idx, (p, score) in enumerate(scored, start=1):
                if idx <= 3:
                    award = AWARD_LEVEL_NAMES[idx]
                elif idx <= 3 + PARTICIPATION_AWARD_COUNT:
                    award = PARTICIPATION_AWARD_NAME
                else:
                    break  # 超出获奖范围，不再奖励
                title = (f"{comp.title}（{comp.session}）{award}" if comp.session
                         else f"{comp.title}{award}")
                db.add(ProjAchievement(
                    project_id=p.id,
                    achievement_type=4,  # 竞赛获奖
                    title=title,
                    level=1,
                    award_level=award,
                    publisher=comp.organizer,
                    summary=(f"{AUTO_AWARD_SUMMARY_PREFIX}比赛:{comp.title} "
                             f"届次:{comp.session or '—'} 名次:{idx} 平均分:{score:.2f}"),
                ))
                items.append({
                    "project_id": p.id,
                    "project_name": p.project_name,
                    "average_score": round(score, 2),
                    "rank": idx,
                    "award_level": award,
                })
                total_awarded += 1
            result_groups.append({
                "college_id": college_id,
                "college_name": college_names.get(college_id),
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
