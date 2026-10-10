"""
创新创业大赛 Pydantic 数据模型
"""
from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict


# ====================================================================
# 常量
# ====================================================================
COMPETITION_TYPE_NAME = {1: "创新训练类", 2: "创业实践类", 3: "学科竞赛类", 4: "综合类"}
COMPETITION_LEVEL_NAME = {1: "校级", 2: "省级", 3: "国家级", 4: "国际级"}
COMPETITION_STATUS_NAME = {0: "草稿", 1: "报名中", 2: "进行中", 3: "已结束", 4: "已取消"}


# ====================================================================
# 创建 / 更新
# ====================================================================
class CompetitionCreate(BaseModel):
    title: str = Field(..., max_length=255, description="比赛名称")
    competition_type: int = Field(1, ge=1, le=4, description="比赛类型")
    level: int = Field(1, ge=1, le=4, description="比赛级别")
    organizer: Optional[str] = Field(None, max_length=255)
    co_organizer: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    requirements: Optional[str] = None
    rewards: Optional[str] = None
    registration_start: Optional[date] = None
    registration_end: Optional[date] = None
    competition_start: Optional[date] = None
    competition_end: Optional[date] = None
    location: Optional[str] = Field(None, max_length=255)
    contact: Optional[str] = Field(None, max_length=255)
    cover_image: Optional[str] = Field(None, max_length=500)
    official_url: Optional[str] = Field(None, max_length=500)
    status: int = Field(0, ge=0, le=4, description="状态:0草稿 1报名中 2进行中 3已结束 4已取消")


class CompetitionUpdate(CompetitionCreate):
    pass


# ====================================================================
# 列表项 / 详情
# ====================================================================
class CompetitionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    competition_type: int
    competition_type_name: str = ""
    level: int
    level_name: str = ""
    organizer: Optional[str] = None
    registration_start: Optional[date] = None
    registration_end: Optional[date] = None
    competition_start: Optional[date] = None
    competition_end: Optional[date] = None
    location: Optional[str] = None
    cover_image: Optional[str] = None
    status: int
    status_name: str = ""
    view_count: int = 0
    created_at: datetime


class CompetitionDetail(CompetitionListItem):
    co_organizer: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    rewards: Optional[str] = None
    contact: Optional[str] = None
    official_url: Optional[str] = None
    created_by: Optional[int] = None
    creator_name: Optional[str] = None
