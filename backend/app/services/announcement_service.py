# ============================================================================
# 公告 业务逻辑层
# ----------------------------------------------------------------------------
# 业务功能：平台公告的发布、编辑、下线、软删除与分页查询；公告支持类型、
#           优先级、有效期，到期后自动下线，学生端只看已发布内容。
# 核心表：
#   announcement  公告主表（标题/内容/类型/优先级/状态/有效期/创建人/浏览量）
#   sys_user      系统用户（批量补全列表中的创建人姓名）
# 上游路由：app/api/v1/announcement.py（列表/详情/新增/编辑/删除/改状态）
# 下游依赖：schemas.announcement 的类型/状态/优先级名称映射、security 超管判定。
# 关键约束：
#   1) 创建/编辑/删除/改状态仅管理员（is_super_admin）可操作；
#   2) 状态约定：1=已发布，2=已下线/已过期；只有已发布对普通用户可见；
#   3) 列表查询前先执行到期自动下线，避免用户看到过期公告；
#   4) 列表创建人姓名用一次 IN 查询批量取，禁止逐条查询造成 N+1。
# ============================================================================
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
    """公告业务服务。

    查询方法只读；写方法内部提交事务。公告均为软删除，保留历史便于审计。
    """

    @staticmethod
    def _fill_names(item: Announcement) -> Announcement:
        """把类型/状态/优先级枚举翻译成中文名称。

        参数：item 公告 ORM 对象（原地写入三个名称属性）。
        返回：同一个对象。
        注意：未知枚举值统一显示“未知”，避免前端空白。
        """
        item.announcement_type_name = ANNOUNCEMENT_TYPE_NAME.get(item.announcement_type, "未知")
        item.status_name = ANNOUNCEMENT_STATUS_NAME.get(item.status, "未知")
        item.priority_name = ANNOUNCEMENT_PRIORITY_NAME.get(item.priority, "未知")
        return item

    @staticmethod
    def _auto_expire(db: Session) -> None:
        """把已超过有效期的“已发布”公告自动置为“已下线”（status=2）。

        参数：db 会话。
        返回：无。
        副作用：有到期公告时批量改状态并提交事务；无到期数据则完全不写库。
        注意：仅处理 is_deleted=0 且 expire_time 非空的数据；该操作在每次列表
              查询前执行，属于轻量的惰性过期策略，无需定时任务。
        """
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
        """分页查询公告列表（管理端与学生端共用）。

        参数：
            db: 数据库会话。
            page / page_size: 页码（从 1 开始）与每页条数。
            keyword: 模糊匹配标题 / 正文。
            announcement_type: 按公告类型筛选。
            status: 按状态筛选（管理端使用）。
            only_published: 学生端视角，仅返回已发布公告。
        返回：
            (当前页公告列表, 总条数)，每条已填充类型/状态/优先级名称与创建人姓名。
        注意：
            查询前先做惰性到期下线；排序按“优先级降序 + 创建时间降序”，
            保证置顶/重要公告优先展示。
        """
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
        """获取公告详情。

        参数：
            db: 数据库会话。
            ann_id: 公告 id。
            increment_view: 是否累加浏览量（详情页打开时使用）。
            only_published: 学生端视角，非“已发布”状态一律视为不存在。
        返回：
            填充名称与创建人姓名的公告对象。
        异常：
            不存在 / 已软删除 / 不可见 → BizException。
        副作用：
            increment_view=True 时更新浏览量并提交。
        """
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
        """创建公告。

        参数：db 会话、创建表单、当前操作人。
        返回：已落库并填充名称的公告对象。
        权限：仅管理员。
        异常：非管理员 → BizException("仅管理员可创建公告")。
        副作用：若表单状态直接为已发布(1)，同时写入发布时间；提交事务。
        """
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
        """更新公告（按传入字段部分更新）。

        参数：db 会话、公告 id、更新表单、当前操作人。
        返回：更新后并填充名称的公告对象。
        权限：仅管理员。
        异常：非管理员 → BizException；公告不存在 → 由 get_detail 抛出。
        注意：使用 exclude_unset 只更新显式传入的字段；首次改为已发布时补写发布时间，
              之后再次编辑不会覆盖原始发布时间。
        """
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
        """删除公告（软删除）。

        参数：db 会话、公告 id、当前操作人。
        返回：无。
        权限：仅管理员。
        注意：仅置 is_deleted=1，保留数据以便追溯或恢复。
        """
        if not is_super_admin(operator):
            from app.core.exceptions import BizException
            raise BizException("仅管理员可删除公告")
        ann = AnnouncementService.get_detail(db, ann_id)
        ann.is_deleted = 1
        db.commit()

    @staticmethod
    def update_status(db: Session, ann_id: int, status: int, operator: SysUser) -> Announcement:
        """修改公告状态（发布/下线）。

        参数：db 会话、公告 id、目标状态（1=已发布，2=已下线）、当前操作人。
        返回：更新后的公告对象。
        权限：仅管理员。
        异常：非管理员 / 状态值不在枚举内 → BizException。
        注意：首次发布时补写发布时间，重复发布不覆盖；下线不回清发布时间。
        """
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
