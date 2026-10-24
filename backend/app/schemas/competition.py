# ====================================================================
# 赛事模块 Schema
# --------------------------------------------------------------------
# 分组说明：
#   1. 常量：COMPETITION_TYPE_NAME / COMPETITION_LEVEL_NAME / COMPETITION_STATUS_NAME；
#   2. 写入：CompetitionCreate / CompetitionUpdate（Update 复用 Create 的字段与日期校验）；
#   3. 读取：CompetitionListItem / CompetitionDetail；
#   4. 获奖名单生成：AwardItem / AwardGroup / AwardGenerateResult（按学院分组）。
# 注意：比赛 level 为 1校级/2省级/3国家级，与项目级别数值含义不同。
# ====================================================================
"""
创新创业大赛 Pydantic 数据模型
"""
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict, model_validator


# ====================================================================
# 常量
# ====================================================================
# 比赛类型映射：1 创新训练类 / 2 创业实践类 / 3 学科竞赛类 / 4 综合类
COMPETITION_TYPE_NAME = {1: "创新训练类", 2: "创业实践类", 3: "学科竞赛类", 4: "综合类"}
# 比赛级别映射：1 校级 / 2 省级 / 3 国家级（与项目级别 1院级2校级3省级4国家级 不同）
COMPETITION_LEVEL_NAME = {1: "校级", 2: "省级", 3: "国家级"}
# 比赛状态映射：0 草稿 / 1 报名中 / 2 进行中 / 3 已结束 / 4 已取消
COMPETITION_STATUS_NAME = {0: "草稿", 1: "报名中", 2: "进行中", 3: "已结束", 4: "已取消"}


# ====================================================================
# 创建 / 更新
# ====================================================================
class CompetitionCreate(BaseModel):
    """
    创建比赛请求（POST /competitions）

    必填：title；类型/级别/状态有默认值；日期均非必填，
    但一旦填写就由校验器保证先后关系与阶段顺序。
    """
    # 比赛名称：必填
    title: str = Field(..., max_length=255, description="比赛名称")
    # 届次：如 2026届，同赛事年度场次区分
    session: Optional[str] = Field(None, max_length=32, description="届次(如 2026届)")
    # 比赛类型 1-4 / 级别 1-3
    competition_type: int = Field(1, ge=1, le=4, description="比赛类型")
    level: int = Field(1, ge=1, le=3, description="比赛级别:1校级2省级3国家级")
    # 主办/承办
    organizer: Optional[str] = Field(None, max_length=255)
    co_organizer: Optional[str] = Field(None, max_length=255)
    # 详情正文
    description: Optional[str] = None
    requirements: Optional[str] = None
    rewards: Optional[str] = None
    # 报名/比赛起止：两两成对校验先后
    registration_start: Optional[date] = None
    registration_end: Optional[date] = None
    competition_start: Optional[date] = None
    competition_end: Optional[date] = None
    # 流程时间表（截止日驱动锁定，未设置则不锁）
    # 学院初审日 / 校级复审日 / 专家评审日：必须按时间先后填写
    college_review_date: Optional[date] = None
    university_review_date: Optional[date] = None
    expert_review_date: Optional[date] = None
    # 中期/结题截止日：中期不得晚于结题
    midterm_deadline: Optional[date] = None
    final_deadline: Optional[date] = None
    # 展示信息
    location: Optional[str] = Field(None, max_length=255)
    contact: Optional[str] = Field(None, max_length=255)
    cover_image: Optional[str] = Field(None, max_length=500)
    official_url: Optional[str] = Field(None, max_length=500)
    # 状态:0草稿 1报名中 2进行中 3已结束 4已取消
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
    """更新比赛请求：当前与创建同构（全量提交），复用日期校验器"""
    pass


# ====================================================================
# 列表项 / 详情
# ====================================================================
class CompetitionListItem(BaseModel):
    """比赛列表项响应：*_name 为 Service 依据常量映射回填的展示文案"""
    model_config = ConfigDict(from_attributes=True)

    # 主键与名称/届次
    id: int
    title: str
    session: Optional[str] = None
    # 类型与级别及其文案
    competition_type: int
    competition_type_name: str = ""
    level: int
    level_name: str = ""
    # 主办方与赛程日期（列表用于倒计时展示）
    organizer: Optional[str] = None
    registration_start: Optional[date] = None
    registration_end: Optional[date] = None
    competition_start: Optional[date] = None
    competition_end: Optional[date] = None
    # 流程截止日：列表展示用，详情页据此判断锁定
    college_review_date: Optional[date] = None
    university_review_date: Optional[date] = None
    expert_review_date: Optional[date] = None
    midterm_deadline: Optional[date] = None
    final_deadline: Optional[date] = None
    # 展示信息与状态
    location: Optional[str] = None
    cover_image: Optional[str] = None
    status: int
    status_name: str = ""
    view_count: int = 0
    created_at: datetime


class CompetitionDetail(CompetitionListItem):
    """比赛详情响应：追加富文本正文、联系方式、创建人信息"""
    # 承办方与详情正文
    co_organizer: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    rewards: Optional[str] = None
    # 联系与官网
    contact: Optional[str] = None
    official_url: Optional[str] = None
    # 创建人信息：creator_name 由 Service 回填
    created_by: Optional[int] = None
    creator_name: Optional[str] = None


# ====================================================================
# 获奖名单自动生成结果
# ====================================================================
class AwardItem(BaseModel):
    """单个获奖项目：名次按平均分排序生成，不并列；奖项等级由名次区间决定"""
    project_id: int
    project_name: str
    average_score: float = Field(description="专家评审平均分")
    rank: int = Field(description="名次(不并列)")
    award_level: str = Field(description="获奖等级: 校级一等奖/二等奖/三等奖/参与奖")


class AwardGroup(BaseModel):
    """按学院分组的获奖名单：便于按学院发放证书与公示"""
    college_id: int
    college_name: Optional[str] = None
    items: List[AwardItem] = Field(default_factory=list)


class AwardGenerateResult(BaseModel):
    """获奖名单生成结果：一次生成的完整快照，供预览/导出"""
    competition_id: int
    competition_title: str
    session: Optional[str] = None
    # 获奖项目总数
    total_awarded: int = 0
    # 按学院分组的明细
    groups: List[AwardGroup] = Field(default_factory=list)
