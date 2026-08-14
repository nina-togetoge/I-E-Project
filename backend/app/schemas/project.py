"""
项目申报与审核模块 Pydantic v2 数据模型
"""
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict, model_validator


# ====================================================================
# 项目状态常量（与数据库 status 字段一致）
# ====================================================================
PROJECT_STATUS_DRAFT = 0          # 草稿
PROJECT_STATUS_PENDING_COLLEGE = 1  # 待学院初审
PROJECT_STATUS_COLLEGE_PASSED = 2   # 学院初审通过
PROJECT_STATUS_PENDING_UNIVERSITY = 3  # 待校级复审
PROJECT_STATUS_UNIVERSITY_PASSED = 4   # 校级复审通过
PROJECT_STATUS_PENDING_EXPERT = 5      # 待专家评审
PROJECT_STATUS_APPROVED = 6            # 已立项
PROJECT_STATUS_MIDTERM = 7              # 中期检查阶段
PROJECT_STATUS_PENDING_FINAL = 8        # 待结题
PROJECT_STATUS_FINISHED = 9             # 已结题
PROJECT_STATUS_REJECTED = 10            # 已驳回
PROJECT_STATUS_CANCELLED = 11           # 已撤销

PROJECT_STATUS_NAME = {
    0: "草稿", 1: "待学院初审", 2: "学院初审通过", 3: "待校级复审",
    4: "校级复审通过", 5: "待专家评审", 6: "已立项", 7: "中期检查中",
    8: "待结题", 9: "已结题", 10: "已驳回", 11: "已撤销",
}

# ====================================================================
# 团队成员
# ====================================================================
class TeamMemberBase(BaseModel):
    student_id: int = Field(..., description="学生用户ID")
    student_name: str = Field(..., max_length=64)
    student_no: str = Field(..., max_length=64)
    major: Optional[str] = Field(default=None, max_length=128)
    grade: Optional[str] = Field(default=None, max_length=32)
    role_in_team: Optional[str] = Field(default=None, max_length=64, description="团队角色")
    task_desc: Optional[str] = Field(default=None, max_length=255, description="分工")


class TeamMemberCreate(TeamMemberBase):
    pass


class TeamMemberResponse(TeamMemberBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    join_time: datetime


# ====================================================================
# 预算
# ====================================================================
class BudgetItemBase(BaseModel):
    budget_item: str = Field(..., max_length=128, description="预算科目")
    budget_amount: Decimal = Field(..., ge=0, decimal_places=2, description="预算金额")
    remark: Optional[str] = Field(default=None, max_length=255)


class BudgetItemCreate(BudgetItemBase):
    pass


class BudgetItemResponse(BudgetItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    used_amount: Decimal


# ====================================================================
# 项目申报核心模型
# ====================================================================
class ProjectCreate(BaseModel):
    """创建/草稿保存"""
    project_name: str = Field(..., min_length=2, max_length=255)
    project_type: int = Field(..., ge=1, le=3)
    project_level: int = Field(..., ge=1, le=3)
    college_id: int
    teacher_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    project_summary: Optional[str] = None
    innovation_points: Optional[str] = None
    expected_results: Optional[str] = None
    team_members: List[TeamMemberCreate] = Field(default_factory=list, description="团队成员(不含负责人)")
    budgets: List[BudgetItemCreate] = Field(default_factory=list, description="预算明细")

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class ProjectUpdate(BaseModel):
    """更新项目信息"""
    project_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    project_type: Optional[int] = Field(default=None, ge=1, le=3)
    project_level: Optional[int] = Field(default=None, ge=1, le=3)
    teacher_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    project_summary: Optional[str] = None
    innovation_points: Optional[str] = None
    expected_results: Optional[str] = None
    team_members: Optional[List[TeamMemberCreate]] = None
    budgets: Optional[List[BudgetItemCreate]] = None


class ProjectQueryParams(BaseModel):
    """项目列表查询筛选条件"""
    keyword: Optional[str] = Field(default=None, max_length=128, description="项目名称/编号/简介关键词")
    project_type: Optional[int] = None
    project_level: Optional[int] = None
    college_id: Optional[int] = None
    leader_id: Optional[int] = None
    teacher_id: Optional[int] = None
    status: Optional[int] = None
    start_year: Optional[int] = Field(default=None, description="立项年份起")
    end_year: Optional[int] = Field(default=None, description="立项年份止")


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_no: Optional[str]
    project_name: str
    project_type: int
    project_type_name: str = ""
    project_level: int
    project_level_name: str = ""
    college_id: int
    college_name: str = ""
    leader_id: int
    leader_name: str = ""
    teacher_id: Optional[int]
    teacher_name: Optional[str] = None
    start_date: Optional[date]
    end_date: Optional[date]
    budget_amount: Decimal
    used_amount: Decimal
    status: int
    status_name: str = ""
    submit_time: Optional[datetime]
    created_at: datetime


class ProjectDetailResponse(ProjectListItem):
    project_summary: Optional[str] = None
    innovation_points: Optional[str] = None
    expected_results: Optional[str] = None
    reject_reason: Optional[str] = None
    approval_time: Optional[datetime] = None
    team_members: List[TeamMemberResponse] = Field(default_factory=list)
    budgets: List[BudgetItemResponse] = Field(default_factory=list)


class ProjectSubmitResponse(BaseModel):
    """提交审核后的响应"""
    project_id: int
    status: int
    status_name: str
    message: str


# ====================================================================
# 成果登记模型（用于项目归档部分）
# ====================================================================
class AchievementCreate(BaseModel):
    project_id: int
    achievement_type: int = Field(..., ge=1, le=6, description="成果类型:1论文2专利3软著4竞赛5创业6其他")
    title: str = Field(..., max_length=255)
    author: Optional[str] = None
    publish_date: Optional[date] = None
    publisher: Optional[str] = None
    achievement_no: Optional[str] = None
    level: Optional[int] = Field(default=None, ge=1, le=4)
    award_level: Optional[str] = None
    summary: Optional[str] = None


class AchievementResponse(AchievementCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ====================================================================
# 统计分析响应（ECharts适配格式）
# ====================================================================
class StatisticsTrendItem(BaseModel):
    """申报趋势：时间轴数据"""
    period: str = Field(..., description="时间区间：如2024-01")
    apply_count: int = Field(default=0, description="申报数")
    approved_count: int = Field(default=0, description="立项数")


class ProjectStatisticsResponse(BaseModel):
    """首页统计概览"""
    total_projects: int
    pending_review: int
    approved_projects: int
    finished_projects: int
    total_budget: Decimal
    total_used: Decimal
    approval_rate: float = Field(default=0, description="整体立项率%")


# ====================================================================
# 经费报销 Schema
# ====================================================================
EXPENSE_STATUS_DRAFT = 0               # 草稿
EXPENSE_STATUS_PENDING_ADVISOR = 1      # 待导师审批
EXPENSE_STATUS_ADVISOR_APPROVED = 2     # 导师审批通过
EXPENSE_STATUS_PENDING_COLLEGE = 3      # 待学院审批
EXPENSE_STATUS_COLLEGE_APPROVED = 4     # 学院审批通过
EXPENSE_STATUS_PENDING_FINANCE = 5      # 待财务审批
EXPENSE_STATUS_COMPLETED = 6            # 已完成（已报销）
EXPENSE_STATUS_REJECTED = 7            # 已驳回


class ExpenseCreate(BaseModel):
    """创建报销申请"""
    project_id: int
    expense_amount: Decimal
    expense_desc: str = Field(min_length=1, max_length=500)
    invoice_no: Optional[str] = None
    budget_item_id: Optional[int] = None


class ExpenseListItem(BaseModel):
    """报销列表项"""
    id: int
    expense_no: str
    project_id: int
    project_name: Optional[str] = None
    applicant_id: int
    applicant_name: str
    expense_amount: Decimal
    expense_desc: str
    status: int
    status_text: str = ""
    reject_reason: Optional[str] = None
    submit_time: Optional[datetime] = None
    approval_time: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ExpenseReviewRequest(BaseModel):
    """审批请求：approved=True通过(推进下一阶段)，False驳回"""
    approved: bool = Field(..., description="True=通过 False=驳回")
    opinion: Optional[str] = None


class ExpenseSummary(BaseModel):
    """报销汇总"""
    total_count: int = 0
    total_amount: Decimal = Decimal("0")
    approved_amount: Decimal = Decimal("0")
    pending_count: int = 0
