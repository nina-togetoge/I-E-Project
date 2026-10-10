"""
创新创业大赛 业务逻辑层
"""
from typing import Optional, Tuple, List
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models import Competition, SysUser
from app.schemas.competition import (
    CompetitionCreate, CompetitionUpdate,
    CompetitionListItem, CompetitionDetail,
    COMPETITION_TYPE_NAME, COMPETITION_LEVEL_NAME, COMPETITION_STATUS_NAME,
)
from app.core.security import is_super_admin


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
            # 学生端只看已发布的（报名中/进行中/已结束）
            query = query.filter(Competition.status.in_([1, 2, 3]))

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
    def get_detail(db: Session, comp_id: int, increment_view: bool = False) -> Competition:
        """获取大赛详情"""
        comp = (
            db.query(Competition)
            .filter(Competition.id == comp_id, Competition.is_deleted == 0)
            .first()
        )
        if not comp:
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
