"""
公告 Pydantic 数据模型
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ====================================================================
# 常量
# ====================================================================
ANNOUNCEMENT_TYPE_NAME = {1: "系统通知", 2: "申报通知", 3: "结果公示", 4: "其他"}
ANNOUNCEMENT_STATUS_NAME = {0: "草稿", 1: "已发布", 2: "已下线"}
ANNOUNCEMENT_PRIORITY_NAME = {1: "普通", 2: "重要", 3: "紧急"}


# ====================================================================
# 创建 / 更新
# ====================================================================
class AnnouncementCreate(BaseModel):
    title: str = Field(..., max_length=255, description="公告标题")
    content: str = Field(..., description="公告内容")
    announcement_type: int = Field(1, ge=1, le=4, description="公告类型:1系统通知 2申报通知 3结果公示 4其他")
    status: int = Field(0, ge=0, le=2, description="状态:0草稿 1已发布 2已下线")
    priority: int = Field(1, ge=1, le=3, description="优先级:1普通 2重要 3紧急")
    expire_time: Optional[datetime] = Field(None, description="到期时间，到期后自动下线")


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = None
    announcement_type: Optional[int] = Field(None, ge=1, le=4)
    status: Optional[int] = Field(None, ge=0, le=2)
    priority: Optional[int] = Field(None, ge=1, le=3)
    expire_time: Optional[datetime] = Field(None, description="到期时间，到期后自动下线")


# ====================================================================
# 列表项 / 详情
# ====================================================================
class AnnouncementListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str = ""
    announcement_type: int
    announcement_type_name: str = ""
    status: int
    status_name: str = ""
    priority: int
    priority_name: str = ""
    publish_time: Optional[datetime] = None
    expire_time: Optional[datetime] = None
    view_count: int = 0
    created_by: Optional[int] = None
    creator_name: Optional[str] = None
    created_at: datetime


class AnnouncementDetail(AnnouncementListItem):
    content: str = ""
