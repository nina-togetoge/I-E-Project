"""
公告 业务逻辑层
"""
from typing import Optional, Tuple, List
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models import Announcement, SysUser
from app.schemas.announcement import (
    AnnouncementCreate, AnnouncementUpdate,
    ANNOUNCEMENT_TYPE_NAME, ANNOUNCEMENT_STATUS_NAME, ANNOUNCEMENT_PRIORITY_NAME,
)
from app.core.security import is_super_admin


class AnnouncementService:
    """公告服务"""

    @staticmethod
    def _fill_names(item: Announcement) -> Announcement:
        """填充类型/状态/优先级名称"""
        item.announcement_type_name = ANNOUNCEMENT_TYPE_NAME.get(item.announcement_type, "未知")
        item.status_name = ANNOUNCEMENT_STATUS_NAME.get(item.status, "未知")
        item.priority_name = ANNOUNCEMENT_PRIORITY_NAME.get(item.priority, "未知")
        return item

    @staticmethod
    def _auto_expire(db: Session) -> None:
        """将已到期的已发布公告自动下线（status=2）"""
        now = datetime.now()
        expired = (
            db.query(Announcement)
            .filter(
                Announcement.is_deleted == 0,
                Announcement.status == 1,
                Announcement.expire_time.isnot(None),
                Announcement.expire_time < now,
            )
            .all()
        )
        for ann in expired:
            ann.status = 2
        if expired:
            db.commit()

    @staticmethod
    def paginate(
        db: Session,
        page: int,
        page_size: int,
        keyword: Optional[str] = None,
        announcement_type: Optional[int] = None,
        status: Optional[int] = None,
        only_published: bool = False,
    ) -> Tuple[List[Announcement], int]:
        """分页查询公告列表"""
        # 先处理到期自动下线
        AnnouncementService._auto_expire(db)

        query = db.query(Announcement).filter(Announcement.is_deleted == 0)

        if only_published:
            # 非管理员只看已发布的
            query = query.filter(Announcement.status == 1)

        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    Announcement.title.like(like),
                    Announcement.content.like(like),
                )
            )
        if announcement_type is not None:
            query = query.filter(Announcement.announcement_type == announcement_type)
        if status is not None:
            query = query.filter(Announcement.status == status)

        total = query.count()
        items = (
            query.order_by(Announcement.priority.desc(), Announcement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        # 创建人姓名：批量查询，避免列表 N+1
        creator_ids = {it.created_by for it in items if it.created_by}
        creator_map = {}
        if creator_ids:
            creator_map = dict(
                db.query(SysUser.id, SysUser.real_name)
                .filter(SysUser.id.in_(creator_ids))
                .all()
            )
        for it in items:
            AnnouncementService._fill_names(it)
            it.creator_name = creator_map.get(it.created_by)
        return items, total

    @staticmethod
    def get_detail(db: Session, ann_id: int, increment_view: bool = False,
                   only_published: bool = False) -> Announcement:
        """获取公告详情；only_published=True 时非发布状态(草稿/已下线)视为不存在"""
        ann = (
            db.query(Announcement)
            .filter(Announcement.id == ann_id, Announcement.is_deleted == 0)
            .first()
        )
        if not ann or (only_published and ann.status != 1):
            from app.core.exceptions import BizException
            raise BizException("公告不存在或已删除")
        AnnouncementService._fill_names(ann)
        if increment_view:
            ann.view_count = (ann.view_count or 0) + 1
            db.commit()
            db.refresh(ann)
        # 创建人姓名
        if ann.created_by:
            creator = db.query(SysUser).filter(SysUser.id == ann.created_by).first()
            ann.creator_name = creator.real_name if creator else None
        return ann

    @staticmethod
    def create(db: Session, req: AnnouncementCreate, operator: SysUser) -> Announcement:
        """创建公告（仅管理员）"""
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅管理员可创建公告")
        ann = Announcement(**req.model_dump(), created_by=operator.id)
        # 如果状态为已发布，记录发布时间
        if ann.status == 1:
            ann.publish_time = datetime.now()
        db.add(ann)
        db.commit()
        db.refresh(ann)
        AnnouncementService._fill_names(ann)
        return ann

    @staticmethod
    def update(db: Session, ann_id: int, req: AnnouncementUpdate, operator: SysUser) -> Announcement:
        """更新公告（仅管理员）"""
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅管理员可编辑公告")
        ann = AnnouncementService.get_detail(db, ann_id)
        update_data = req.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(ann, k, v)
        # 如果状态改为已发布且之前未发布，记录发布时间
        if update_data.get("status") == 1 and not ann.publish_time:
            ann.publish_time = datetime.now()
        db.commit()
        db.refresh(ann)
        AnnouncementService._fill_names(ann)
        return ann

    @staticmethod
    def delete(db: Session, ann_id: int, operator: SysUser) -> None:
        """删除公告（软删除，仅管理员）"""
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅管理员可删除公告")
        ann = AnnouncementService.get_detail(db, ann_id)
        ann.is_deleted = 1
        db.commit()

    @staticmethod
    def update_status(db: Session, ann_id: int, status: int, operator: SysUser) -> Announcement:
        """更新公告状态（仅管理员）"""
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅管理员可修改公告状态")
        if status not in ANNOUNCEMENT_STATUS_NAME:
            from app.core.exceptions import BizException
            raise BizException("无效的公告状态")
        ann = AnnouncementService.get_detail(db, ann_id)
        ann.status = status
        if status == 1 and not ann.publish_time:
            ann.publish_time = datetime.now()
        db.commit()
        db.refresh(ann)
        AnnouncementService._fill_names(ann)
        return ann
