"""
数据模型统一导出模块
使外部可以通过 from app.models import Xxx 直接导入所有模型
"""
from app.models.base import BaseModel, TimestampMixin, SoftDeleteMixin
from app.models.user import (
    SysCollege,
    SysUser,
    SysOperationLog,
    SysDict,
    SysAttachment,
)
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
from app.models.competition import Competition
from app.models.announcement import Announcement
from app.models.notification import SysNotification

__all__ = [
    # Base
    "BaseModel",
    "TimestampMixin",
    "SoftDeleteMixin",
    # User models
    "SysCollege",
    "SysUser",
    "SysOperationLog",
    "SysDict",
    "SysAttachment",
    # Project models
    "ProjProject",
    "ProjTeamMember",
    "ProjReview",
    "ProjBudget",
    "ProjExpense",
    "ProjAchievement",
    "ProjAchievementReview",
    "ProjMidtermCheck",
    "ProjChangeRequest",
    # Competition
    "Competition",
    # Announcement
    "Announcement",
    # Notification
    "SysNotification",
]
