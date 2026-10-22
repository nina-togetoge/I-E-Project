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
PROJECT_STATUS_PENDING_TEACHER = 12  # 待指导教师确认
PROJECT_STATUS_PENDING_COLLEGE = 1  # 待学院初审
PROJECT_STATUS_COLLEGE_PASSED = 2   # 学院初审通过
PROJECT_STATUS_PENDING_UNIVERSITY = 3  # 待校级复审
PROJECT_STATUS_UNIVERSITY_PASSED = 4   # 校级复审通过
PROJECT_STATUS_PENDING_EXPERT = 5      # 待专家评审
PROJECT_STATUS_PENDING_EXPERT_ASSIGN = 13  # 待分配评审专家
PROJECT_STATUS_APPROVED = 6            # 已立项
PROJECT_STATUS_MIDTERM = 7              # 中期检查阶段
PROJECT_STATUS_PENDING_FINAL = 8        # 待结题
PROJECT_STATUS_FINISHED = 9             # 已结题
PROJECT_STATUS_REJECTED = 10            # 已驳回
PROJECT_STATUS_CANCELLED = 11           # 已撤销

PROJECT_STATUS_NAME = {
    0: "草稿", 12: "待指导教师确认", 1: "待学院初审", 2: "学院初审通过", 3: "待校级复审",
    4: "校级复审通过", 5: "待专家评审", 13: "待分配评审专家", 6: "已立项", 7: "中期检查中",
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
    project_level: int = Field(..., ge=1, le=4)
    college_id: int
    leader_id: Optional[int] = Field(default=None, description="负责人ID（管理员创建时必填）")
    teacher_id: Optional[int] = None
    competition_id: Optional[int] = Field(default=None, description="参赛比赛ID")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    project_summary: Optional[str] = None
    innovation_points: Optional[str] = None
    expected_results: Optional[str] = None
    team_members: List[TeamMemberCreate] = Field(default_factory=list, description="团队成员(不含负责人)")
    budgets: List[BudgetItemCreate] = Field(default_factory=list, description="预算明细")
    attachment_ids: List[int] = Field(default_factory=list, description="上传时 biz_id=0 的临时附件IDs，创建后关联到项目")

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class ProjectUpdate(BaseModel):
    """更新项目信息"""
    project_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    project_type: Optional[int] = Field(default=None, ge=1, le=3)
    project_level: Optional[int] = Field(default=None, ge=1, le=4)
    teacher_id: Optional[int] = None
    competition_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    project_summary: Optional[str] = None
    innovation_points: Optional[str] = None
    expected_results: Optional[str] = None
    team_members: Optional[List[TeamMemberCreate]] = None
    budgets: Optional[List[BudgetItemCreate]] = None
    attachment_ids: Optional[List[int]] = Field(default=None, description="上传时 biz_id=0 的临时附件IDs，更新后关联到项目")

    @model_validator(mode="after")
    def check_dates(self):
        """同时提交起止日期时校验先后顺序（仅提交一端时由 Service 与库中值合并校验）"""
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class ProjectQueryParams(BaseModel):
    """项目列表查询筛选条件"""
    keyword: Optional[str] = Field(default=None, max_length=128, description="项目名称/编号/简介关键词")
    project_type: Optional[int] = None
    project_level: Optional[int] = Field(default=None, ge=1, le=4)
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
    competition_id: Optional[int] = None
    competition_name: Optional[str] = None
    competition_session: Optional[str] = None
    start_date: Optional[date]
    end_date: Optional[date]
    budget_amount: Decimal
    used_amount: Decimal
    status: int
    status_name: str = ""
    assigned_expert_count: int = Field(default=0, description="已分配专家数量")
    reviewed_expert_count: int = Field(default=0, description="已提交评审的专家数量（>0 时不可再调整专家名单）")
    award_count: int = Field(default=0, description="竞赛获奖成果数量（成果类型=4 且未删除）")
    resubmittable: bool = Field(default=False, description="是否可修改后重新提交（仅「指导教师驳回」为 True；学院/校级/专家驳回即落选）")
    submit_time: Optional[datetime]
    approval_time: Optional[datetime] = None
    created_at: datetime


class ProjectDetailResponse(ProjectListItem):
    project_summary: Optional[str] = None
    innovation_points: Optional[str] = None
    expected_results: Optional[str] = None
    reject_reason: Optional[str] = None
    final_report_submitted: bool = Field(default=False, description="是否已提交结项验收报告（待结题阶段）")
    final_report: Optional[str] = Field(default=None, description="结项验收报告正文")
    final_report_status: int = Field(
        default=0, description="结项报告状态：0未提交 1待验收 2已通过 3已驳回"
    )
    final_reject_reason: Optional[str] = Field(default=None, description="最近一次结题验收驳回意见")
    final_review_total: int = Field(default=0, description="参与结题验收的专家数")
    final_review_done: int = Field(default=0, description="本轮已提交结题验收意见的专家数")
    final_can_accept: bool = Field(default=False, description="当前用户是否可进行结题验收")
    final_reviewed_by_me: bool = Field(default=False, description="当前用户本轮是否已提交结题验收意见")
    final_checklist: List[dict] = Field(default_factory=list, description="结项条件检查清单")
    # 流程截止日（截止日驱动锁定）
    change_deadline: Optional[date] = Field(default=None, description="变更/延期申请锁死日（当前阶段审核日）")
    change_locked: bool = Field(default=False, description="是否已超过当前阶段审核日，变更/延期已锁定")
    midterm_deadline: Optional[date] = Field(default=None, description="中期报告提交截止日")
    final_deadline: Optional[date] = Field(default=None, description="结题报告提交截止日")
    team_members: List[TeamMemberResponse] = Field(default_factory=list)
    budgets: List[BudgetItemResponse] = Field(default_factory=list)
    attachments: List[dict] = Field(default_factory=list, description="项目附件列表")


class ProjectSubmitResponse(BaseModel):
    """提交审核后的响应"""
    project_id: int
    status: int
    status_name: str
    message: str


class FinalSubmitRequest(BaseModel):
    """提交结项验收报告"""
    final_report: str = Field(min_length=1, max_length=2000, description="结项验收报告")
    attachment_ids: List[int] = Field(default_factory=list, description="结项验收报告附件IDs")


# ====================================================================
# 成果登记模型（用于项目归档部分）
# ====================================================================
class AchievementBase(BaseModel):
    achievement_type: int = Field(..., ge=1, le=6, description="成果类型:1论文2专利3软著4竞赛5创业6其他")
    title: str = Field(..., min_length=1, max_length=255)
    author: Optional[str] = Field(default=None, max_length=255)
    publish_date: Optional[date] = None
    publisher: Optional[str] = Field(default=None, max_length=255)
    achievement_no: Optional[str] = Field(default=None, max_length=128)
    level: Optional[int] = Field(default=None, ge=1, le=4)
    award_level: Optional[str] = Field(default=None, max_length=64)
    summary: Optional[str] = None


class AchievementCreate(AchievementBase):
    project_id: int
    attachment_ids: List[int] = Field(default_factory=list, description="证明材料临时附件IDs（biz_id=0）")


class AchievementUpdate(BaseModel):
    """编辑项目成果：仅传入需要修改的字段"""
    achievement_type: Optional[int] = Field(default=None, ge=1, le=6)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    author: Optional[str] = Field(default=None, max_length=255)
    publish_date: Optional[date] = None
    publisher: Optional[str] = Field(default=None, max_length=255)
    achievement_no: Optional[str] = Field(default=None, max_length=128)
    level: Optional[int] = Field(default=None, ge=1, le=4)
    award_level: Optional[str] = Field(default=None, max_length=64)
    summary: Optional[str] = None
    attachment_ids: List[int] = Field(default_factory=list, description="新增证明材料临时附件IDs（biz_id=0）")


class AchievementResponse(AchievementBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    created_at: datetime
    attachments: List[dict] = Field(default_factory=list, description="成果证明材料列表")
    # 成果认定（无认定记录的历史成果按「已认定」展示）
    review_status: int = Field(default=1, description="认定状态:0待认定 1已认定 2不通过")
    review_status_name: str = Field(default="已认定", description="认定状态名称")
    review_comment: Optional[str] = Field(default=None, description="认定意见")
    reviewer_name: Optional[str] = Field(default=None, description="认定人")
    review_time: Optional[datetime] = Field(default=None, description="认定时间")


class AchievementReviewRequest(BaseModel):
    """成果认定请求"""
    result: int = Field(..., ge=1, le=2, description="认定结果:1通过 2不通过")
    comment: Optional[str] = Field(default=None, max_length=500, description="认定意见")


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
    # —— 数据看板补充字段（真实数据）——
    category_dist: List[dict] = Field(default_factory=list, description="项目类别分布[{name,value}]")
    status_dist: List[dict] = Field(default_factory=list, description="项目状态分布[{name,value}]")
    budget_by_category: List[dict] = Field(default_factory=list, description="经费科目使用分布[{name,amount}]")


class CollegeStatisticsItem(BaseModel):
    """单学院统计数据（雷达图/热力图/学院立项率柱状图）"""
    college_id: int
    college_name: str
    total_projects: int = 0
    approved_projects: int = 0
    finished_projects: int = 0
    total_budget: Decimal = Decimal("0.00")
    total_used: Decimal = Decimal("0.00")
    approval_rate: float = 0.0
    achievements: int = 0
    avg_score: float = 0.0


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
    expense_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="报销金额(必须大于0)")
    expense_desc: str = Field(min_length=1, max_length=500)
    invoice_no: Optional[str] = Field(default=None, max_length=128)
    budget_item_id: Optional[int] = None
    attachment_ids: List[int] = Field(default_factory=list, description="上传时 biz_id=0 的临时附件IDs，创建后关联到报销单")


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
    invoice_no: Optional[str] = None
    status: int
    status_text: str = ""
    reject_reason: Optional[str] = None
    submit_time: Optional[datetime] = None
    approval_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    attachments: List[dict] = Field(default_factory=list, description="报销票据附件")

    model_config = ConfigDict(from_attributes=True)


class ExpenseReviewRequest(BaseModel):
    """审批请求：approved=True通过(推进下一阶段)，False驳回"""
    approved: bool = Field(..., description="True=通过 False=驳回")
    opinion: Optional[str] = Field(default=None, max_length=500, description="审批意见")


class ExpenseQueryRequest(BaseModel):
    """[P1-5] 经费列表查询请求（Pydantic校验，替代裸dict）"""
    applicant_id: Optional[int] = Field(default=None, ge=1, description="申请人ID")
    status: Optional[int] = Field(default=None, ge=1, le=7, description="报销状态 1-7")
    keyword: Optional[str] = Field(default=None, max_length=100, description="关键词(项目名称/单号/说明)")


class ExpenseSummary(BaseModel):
    """报销汇总"""
    total_count: int = 0
    total_amount: Decimal = Decimal("0")
    approved_amount: Decimal = Decimal("0")
    pending_count: int = 0
