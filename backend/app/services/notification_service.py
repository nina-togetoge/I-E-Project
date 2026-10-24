# ============================================================================
# 站内通知 业务服务
# ----------------------------------------------------------------------------
# 业务功能：向单个/多个用户写入站内通知，提供“我的通知”分页、未读数统计、
#           单条已读与全部已读；供审批、成果认定、证书签发等业务调用。
# 核心表：
#   sys_notification  站内通知（接收人、标题、内容、级别、业务类型/id、跳转链接、已读状态）
# 上游路由：app/api/v1/notification.py（列表/未读数/标记已读/全部已读）
# 下游依赖：app.core.exceptions 的 404 异常、schemas.notification 的响应模型。
# 关键约束：
#   1) push/push_many 只 add 不 commit，由业务调用方统一提交，保证通知与业务同事务；
#   2) 通知只发给存在且有效的用户 id，空/零值直接忽略；
#   3) 已读操作必须校验 user_id，防止越权读/改他人通知；
#   4) 通知均为软删除，查询一律带 is_deleted=0。
# ============================================================================
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundException
from app.models import SysNotification
from app.schemas.notification import NotificationItem

# 通知级别：1-普通 2-警告 3-成功
# 前端据此显示不同颜色/图标；业务侧引用常量而非裸数字，避免级别含义漂移。
NOTICE_LEVEL_INFO = 1
NOTICE_LEVEL_WARNING = 2
NOTICE_LEVEL_SUCCESS = 3


class NotificationService:
    """站内通知业务服务。

    写入方法只把对象加入 session，不提交事务；查询与已读方法按需自行提交。
    """

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
        """写入一条通知（不提交事务，由调用方统一 commit）。

        参数：
            db: 数据库会话。
            user_id: 接收人 id；None/0 时直接忽略，返回 None。
            title / content: 标题与正文，分别截断到 128/1000 字符，适配表字段长度。
            level: 通知级别，默认普通（1）。
            biz_type / biz_id: 业务来源标识，便于前端跳转或按业务聚合。
            link: 前端路由，如 "/my-certificates"。
        返回：
            新建的 SysNotification 对象（未提交）；接收人为空时返回 None。
        注意：
            不在此处 commit，确保调用方业务失败回滚时通知一并回滚，避免“幽灵通知”。
        """
        if not user_id:
            return None
        # 标题/正文按表字段长度截断，避免超长内容写库报错；新通知初始为未读
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
        """批量写入同一条通知（自动去重、忽略空用户）。

        参数：db 会话、接收人 id 可迭代对象、通知内容/级别/业务标识/链接。
        返回：无。
        注意：
            用集合去重，避免同一成员因“负责人 + 团队成员”双重身份收到重复通知；
            仍只 add 不 commit，由调用方统一提交。
        """
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
        """分页查询当前用户的通知（按 id 倒序，最新在前）。

        参数：
            db: 数据库会话。
            user_id: 当前用户 id，作为强制过滤条件，防止越权查看他人通知。
            page / page_size: 页码（从 1 开始）与每页条数。
            is_read: 0=仅未读，1=仅已读，None=全部。
        返回：
            (通知响应列表, 总条数)。
        注意：只返回未软删除的通知。
        """
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
        """统计当前用户的未读通知数（用于顶部小红点）。

        参数：db 会话、当前用户 id。
        返回：未读且未删除的通知条数。
        """
        return db.query(SysNotification.id).filter(
            SysNotification.user_id == user_id,
            SysNotification.is_read == 0,
            SysNotification.is_deleted == 0,
        ).count()

    @staticmethod
    def mark_read(db: Session, user_id: int, pk: int) -> None:
        """把指定通知标记为已读。

        参数：db 会话、当前用户 id、通知主键。
        返回：无。
        异常：通知不存在、已删除或不属于当前用户 → ResourceNotFoundException。
        副作用：仅未读时写入 read_time 并提交；已读重复调用不重复写库。
        权限：查询条件强制带 user_id，防止通过 id 越权操作他人通知。
        """
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
        """把当前用户的全部未读通知标记为已读。

        参数：db 会话、当前用户 id。
        返回：本次实际更新的通知条数。
        副作用：批量 UPDATE 已读状态与 read_time 并提交；不触碰他人或已删除通知。
        注意：使用 synchronize_session=False 的批量更新，避免逐条加载 ORM 对象。
        """
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
