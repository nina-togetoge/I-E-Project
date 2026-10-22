"""
创新创业大赛 Pydantic 数据模型
"""
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict, model_validator


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
    session: Optional[str] = Field(None, max_length=32, description="届次(如 2026届)")
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
    # 流程时间表（截止日驱动锁定，未设置则不锁）
    college_review_date: Optional[date] = None
    university_review_date: Optional[date] = None
    expert_review_date: Optional[date] = None
    midterm_deadline: Optional[date] = None
    final_deadline: Optional[date] = None
    location: Optional[str] = Field(None, max_length=255)
    contact: Optional[str] = Field(None, max_length=255)
    cover_image: Optional[str] = Field(None, max_length=500)
    official_url: Optional[str] = Field(None, max_length=500)
    status: int = Field(0, ge=0, le=4, description="状态:0草稿 1报名中 2进行中 3已结束 4已取消")

    @model_validator(mode="after")
    def check_dates(self):
        """校验时间表先后顺序，避免配置出互相矛盾的日期导致流程锁死"""
        if self.registration_start and self.registration_end and \
                self.registration_start > self.registration_end:
            raise ValueError("报名开始日期不能晚于报名截止日期")
        if self.competition_start and self.competition_end and \
                self.competition_start > self.competition_end:
            raise ValueError("比赛开始日期不能晚于比赛结束日期")
        review_dates = [
            d for d in (self.college_review_date, self.university_review_date, self.expert_review_date)
            if d is not None
        ]
        if review_dates != sorted(review_dates):
            raise ValueError("学院初审、校级复审、专家评审的审核日须按时间先后填写")
        if self.midterm_deadline and self.final_deadline and \
                self.midterm_deadline > self.final_deadline:
            raise ValueError("中期截止日不能晚于结题截止日")
        return self


class CompetitionUpdate(CompetitionCreate):
    pass


# ====================================================================
# 列表项 / 详情
# ====================================================================
class CompetitionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    session: Optional[str] = None
    competition_type: int
    competition_type_name: str = ""
    level: int
    level_name: str = ""
    organizer: Optional[str] = None
    registration_start: Optional[date] = None
    registration_end: Optional[date] = None
    competition_start: Optional[date] = None
    competition_end: Optional[date] = None
    college_review_date: Optional[date] = None
    university_review_date: Optional[date] = None
    expert_review_date: Optional[date] = None
    midterm_deadline: Optional[date] = None
    final_deadline: Optional[date] = None
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


# ====================================================================
# 获奖名单自动生成结果
# ====================================================================
class AwardItem(BaseModel):
    project_id: int
    project_name: str
    average_score: float = Field(description="专家评审平均分")
    rank: int = Field(description="名次(不并列)")
    award_level: str = Field(description="获奖等级: 校级一等奖/二等奖/三等奖/参与奖")


class AwardGroup(BaseModel):
    college_id: int
    college_name: Optional[str] = None
    items: List[AwardItem] = Field(default_factory=list)


class AwardGenerateResult(BaseModel):
    competition_id: int
    competition_title: str
    session: Optional[str] = None
    total_awarded: int = 0
    groups: List[AwardGroup] = Field(default_factory=list)
