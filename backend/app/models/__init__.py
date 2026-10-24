# ====================================================================
# ORM 模型统一导出模块
# --------------------------------------------------------------------
# 本模块不承载任何业务逻辑，只做两件事：
#   1. 汇总导入各业务域的 ORM 类，调用方可以用 from app.models import Xxx；
#   2. 用 __all__ 显式声明对外公开的模型集合，避免通配导入失控。
# 注意：SQLAlchemy 只有"类被导入过一次"才会注册进 Base.metadata，
# 因此 Alembic 自动迁移与 create_all 建表都依赖本模块的导入完整性；
# 新增模型时必须同步补齐 import 与 __all__，否则会静默漏表。
# ====================================================================
"""
数据模型统一导出模块
使外部可以通过 from app.models import Xxx 直接导入所有模型
"""
# 基础抽象层：主键、时间戳、软删除混入，所有业务模型都从这里继承
from app.models.base import BaseModel, TimestampMixin, SoftDeleteMixin
# 用户/基础数据域：学院、用户、操作日志、字典、附件（跨业务复用）
from app.models.user import (
    SysCollege,
    SysUser,
    SysOperationLog,
    SysDict,
    SysAttachment,
)
# 项目业务域：申报、成员、审核、预算、报销、成果、中期、变更
from app.models.project import (
    ProjProject,
    ProjTeamMember,
    ProjReview,
    ProjBudget,
    ProjExpense,
    ProjAchievement,
    ProjAchievementReview,
    ProjMidtermCheck,
    ProjChangeRequest,
)
# 赛事域：大创/学科竞赛等比赛主数据（项目通过 competition_id 关联）
from app.models.competition import Competition
# 公告域：面向全校发布的系统/申报/公示类公告
from app.models.announcement import Announcement
# 通知域：按用户投递的站内消息，承载审核结果等业务提醒
from app.models.notification import SysNotification
# 证书域：获奖后自动生成的团队证书与个人证书
from app.models.certificate import ProjCertificate

__all__ = [
    # Base：抽象基类与混入，不映射实体表
    "BaseModel",           # 公共主键 + 时间戳 + 软删除基类
    "TimestampMixin",      # created_at / updated_at 混入
    "SoftDeleteMixin",     # is_deleted 逻辑删除混入
    # User models：基础数据域
    "SysCollege",          # 学院主数据，同时是数据权限隔离的维度
    "SysUser",             # 统一用户表，角色 1学生/2教师/3专家/4管理员
    "SysOperationLog",     # 操作审计日志，独立主键、不参与软删除
    "SysDict",             # 通用字典，供前端下拉与文案映射
    "SysAttachment",       # 附件元数据，按 biz_type + biz_id 多业务复用
    # Project models：项目业务域
    "ProjProject",           # 项目主表，状态机驱动全流程
    "ProjTeamMember",        # 团队成员快照（冗余姓名/学号）
    "ProjReview",            # 各阶段审核记录（含专家分配占位记录）
    "ProjBudget",            # 预算科目明细
    "ProjExpense",           # 经费报销单，多级审批
    "ProjAchievement",       # 项目成果登记
    "ProjAchievementReview", # 成果认定记录，一条成果至多一条
    "ProjMidtermCheck",      # 中期检查，一项目至多一条
    "ProjChangeRequest",     # 变更/延期申请，按阶段限制次数
    # Competition：赛事主数据
    "Competition",
    # Announcement：公告
    "Announcement",
    # Notification：站内通知
    "SysNotification",
    # Certificate：获奖证书
    "ProjCertificate",
]
