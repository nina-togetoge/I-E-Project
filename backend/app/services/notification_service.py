"""
站内通知业务服务

提供统一的通知写入与查询能力，供审核、成果认定等业务调用。
"""
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundException
from app.models import SysNotification
from app.schemas.notification import NotificationItem

# 通知级别：1-普通 2-警告 3-成功
NOTICE_LEVEL_INFO = 1
NOTICE_LEVEL_WARNING = 2
NOTICE_LEVEL_SUCCESS = 3


class NotificationService:
    """站内通知业务服务"""

    @staticmethod
    def push(
        db: Session,
        user_id: Optional[int],
        title: str,
        content: str,
        level: int = NOTICE_LEVEL_INFO,
        biz_type: Optional[str] = None,
        biz_id: Optional[int] = None,
        link: Optional[str] = None,
    ) -> Optional[SysNotification]:
        """写入一条通知（不提交事务，由调用方统一 commit）"""
        if not user_id:
            return None
        obj = SysNotification(
            user_id=user_id,
            title=title[:128],
            content=content[:1000],
            level=level,
            biz_type=biz_type,
            biz_id=biz_id,
            link=link,
            is_read=0,
        )
        db.add(obj)
        return obj

    @staticmethod
    def push_many(
        db: Session,
        user_ids: Iterable[Optional[int]],
        title: str,
        content: str,
        level: int = NOTICE_LEVEL_INFO,
        biz_type: Optional[str] = None,
        biz_id: Optional[int] = None,
        link: Optional[str] = None,
    ) -> None:
        """批量写入通知（自动去重、忽略空用户）"""
        for uid in {int(u) for u in user_ids if u}:
            NotificationService.push(
                db, uid, title, content, level, biz_type, biz_id, link
            )

    @staticmethod
    def paginate(
        db: Session,
        user_id: int,
        page: int,
        page_size: int,
        is_read: Optional[int] = None,
    ) -> Tuple[List[NotificationItem], int]:
        q = db.query(SysNotification).filter(
            SysNotification.user_id == user_id,
            SysNotification.is_deleted == 0,
        )
        if is_read is not None:
            q = q.filter(SysNotification.is_read == is_read)
        total = q.count()
        rows = q.order_by(SysNotification.id.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
        return [NotificationItem.model_validate(x) for x in rows], total

    @staticmethod
    def unread_count(db: Session, user_id: int) -> int:
        return db.query(SysNotification.id).filter(
            SysNotification.user_id == user_id,
            SysNotification.is_read == 0,
            SysNotification.is_deleted == 0,
        ).count()

    @staticmethod
    def mark_read(db: Session, user_id: int, pk: int) -> None:
        obj = db.query(SysNotification).filter(
            SysNotification.id == pk,
            SysNotification.user_id == user_id,
            SysNotification.is_deleted == 0,
        ).first()
        if not obj:
            raise ResourceNotFoundException(message="通知不存在")
        if obj.is_read == 0:
            obj.is_read = 1
            obj.read_time = datetime.now()
            db.commit()

    @staticmethod
    def mark_all_read(db: Session, user_id: int) -> int:
        rows = db.query(SysNotification).filter(
            SysNotification.user_id == user_id,
            SysNotification.is_read == 0,
            SysNotification.is_deleted == 0,
        ).update(
            {"is_read": 1, "read_time": datetime.now()},
            synchronize_session=False,
        )
        db.commit()
        return int(rows)
