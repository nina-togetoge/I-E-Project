# ====================================================================
# 项目申报/审核模块 Schema
# --------------------------------------------------------------------
# 分组说明：
#   1. 状态常量与文案映射：PROJECT_STATUS_* / PROJECT_STATUS_NAME，与库中 status 一一对应；
#   2. 子结构：TeamMember* / BudgetItem*（嵌套在项目创建与详情中）；
#   3. 申报核心：ProjectCreate / ProjectUpdate / ProjectQueryParams / ProjectListItem /
#      ProjectDetailResponse / ProjectSubmitResponse / FinalSubmitRequest；
#   4. 成果：Achievement*（登记、编辑、认定）；
#   5. 统计：StatisticsTrendItem / ProjectStatisticsResponse / CollegeStatisticsItem；
#   6. 报销：EXPENSE_STATUS_* 与 Expense*。
# 校验职责边界：本层只做格式/取值/日期先后校验；跨表业务校验（余额、阶段、权限）在 Service。
# ====================================================================
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
PROJECT_STATUS_DRAFT = 0          # 草稿：仅负责人可见，可任意编辑
PROJECT_STATUS_PENDING_TEACHER = 12  # 待指导教师确认：提交后先找导师，导师驳回可改后重提
PROJECT_STATUS_PENDING_COLLEGE = 1  # 待学院初审：导师确认后由学院管理员审核
PROJECT_STATUS_COLLEGE_PASSED = 2   # 学院初审通过：瞬时态，随即进入待校级复审
PROJECT_STATUS_PENDING_UNIVERSITY = 3  # 待校级复审：校级管理员审核
PROJECT_STATUS_UNIVERSITY_PASSED = 4   # 校级复审通过：瞬时态，随即分配专家
PROJECT_STATUS_PENDING_EXPERT = 5      # 待专家评审：专家已分配、等待打分
PROJECT_STATUS_PENDING_EXPERT_ASSIGN = 13  # 待分配评审专家：等待校级/学院指派专家
PROJECT_STATUS_APPROVED = 6            # 已立项：可执行项目、报销、中期检查
PROJECT_STATUS_MIDTERM = 7              # 中期检查阶段：已立项且进入执行中期
PROJECT_STATUS_PENDING_FINAL = 8        # 待结题：结项验收报告待专家评审
PROJECT_STATUS_FINISHED = 9             # 已结题：流程终态，可下载证书/归档
PROJECT_STATUS_REJECTED = 10            # 已驳回：学院/校级/专家驳回即落选（导师驳回除外）
PROJECT_STATUS_CANCELLED = 11           # 已撤销：负责人主动撤销，不可恢复

# 数值 -> 中文文案映射，供 Service 回填 status_name；新增状态必须与库中一致
PROJECT_STATUS_NAME = {
    0: "草稿", 12: "待指导教师确认", 1: "待学院初审", 2: "学院初审通过", 3: "待校级复审",
    4: "校级复审通过", 5: "待专家评审", 13: "待分配评审专家", 6: "已立项", 7: "中期检查中",
    8: "待结题", 9: "已结题", 10: "已驳回", 11: "已撤销",
}

# ====================================================================
# 团队成员
# ====================================================================
class TeamMemberBase(BaseModel):
    """团队成员公共字段：创建与响应复用，学生语义字段均为必填快照"""
    # 学生用户ID：必填，用于成员去重与权限判断
    student_id: int = Field(..., description="学生用户ID")
    # 姓名/学号：前端选择学生后自动带出，后端再次落库为快照
    student_name: str = Field(..., max_length=64)
    student_no: str = Field(..., max_length=64)
    # 专业/年级：非必填，申报书展示用
    major: Optional[str] = Field(default=None, max_length=128)
    grade: Optional[str] = Field(default=None, max_length=32)
    # 团队角色与分工：自由文本，评审考察团队结构时参考
    role_in_team: Optional[str] = Field(default=None, max_length=64, description="团队角色")
    task_desc: Optional[str] = Field(default=None, max_length=255, description="分工")


class TeamMemberCreate(TeamMemberBase):
    """创建成员请求：字段与 Base 完全一致，单独成类便于后续扩展"""
    pass


class TeamMemberResponse(TeamMemberBase):
    """成员响应：由 ORM 对象直接转换，额外返回主键、所属项目与加入时间"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    join_time: datetime


# ====================================================================
# 预算
# ====================================================================
class BudgetItemBase(BaseModel):
    """预算科目公共字段：科目名必填，金额非负且保留两位小数"""
    # 预算科目：如设备费/材料费/差旅费/劳务费
    budget_item: str = Field(..., max_length=128, description="预算科目")
    # 预算金额：ge=0 禁止负数，decimal_places=2 与库中 Numeric(12,2) 对齐
    budget_amount: Decimal = Field(..., ge=0, decimal_places=2, description="预算金额")
    # 备注：测算依据说明
    remark: Optional[str] = Field(default=None, max_length=255)


class BudgetItemCreate(BudgetItemBase):
    """创建预算明细请求（嵌套在项目创建中，不单独暴露接口）"""
    pass


class BudgetItemResponse(BudgetItemBase):
    """预算明细响应：额外返回已使用金额，用于前端展示科目余额"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    used_amount: Decimal


# ====================================================================
# 项目申报核心模型
# ====================================================================
class ProjectCreate(BaseModel):
    """
    创建项目/保存草稿请求（POST /projects）

    必填：project_name、project_type、project_level、college_id；
    leader_id 在管理员代建时必填，学生自建时由登录态推断。
    嵌套 team_members / budgets 一次性提交，attachment_ids 为临时附件（biz_id=0）。
    """
    # 名称过短无意义，限制 2~255 字
    project_name: str = Field(..., min_length=2, max_length=255)
    # 项目类型 1-3：创新训练/创业训练/创业实践
    project_type: int = Field(..., ge=1, le=3)
    # 项目级别 1-4：院级/校级/省级/国家级（数值含义不同于成果级别）
    project_level: int = Field(..., ge=1, le=4)
    # 申报学院：数据权限归属，学生自建时通常取本人学院
    college_id: int
    # 负责人：管理员代建必填；学生自建可空，由 Service 用当前用户补齐
    leader_id: Optional[int] = Field(default=None, description="负责人ID（管理员创建时必填）")
    # 指导教师：可暂不选择，提交前补齐
    teacher_id: Optional[int] = None
    # 参赛比赛：参赛类项目填写
    competition_id: Optional[int] = Field(default=None, description="参赛比赛ID")
    # 起止日期：同时提供时校验先后
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # 申报书正文三段：简介/创新点/预期成果
    project_summary: Optional[str] = None
    innovation_points: Optional[str] = None
    expected_results: Optional[str] = None
    # 团队成员（不含负责人）；空列表表示暂无成员
    team_members: List[TeamMemberCreate] = Field(default_factory=list, description="团队成员(不含负责人)")
    # 预算明细：提交时校验合计不超过总额（Service 层）
    budgets: List[BudgetItemCreate] = Field(default_factory=list, description="预算明细")
    # 临时附件ID：上传接口先写 biz_id=0，创建成功后回填真实项目ID
    attachment_ids: List[int] = Field(default_factory=list, description="上传时 biz_id=0 的临时附件IDs，创建后关联到项目")

    @model_validator(mode="after")
    def check_dates(self):
        """起止日期同时存在时校验先后，避免落库后出现负工期"""
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class ProjectUpdate(BaseModel):
    """
    更新项目请求（PUT/PATCH /projects/{id}）

    全部字段可选，支持部分更新；团队/预算传入即整体替换（Service 层按删除重建处理）。
    仅草稿、待教师确认、需修改后重提等允许编辑的状态可调用。
    """
    # 基础信息：与创建一致，传 null 表示不修改
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
    # 传列表即整体替换；传 null 表示不动
    team_members: Optional[List[TeamMemberCreate]] = None
    budgets: Optional[List[BudgetItemCreate]] = None
    # 新增的临时附件ID：更新成功后追加关联到项目
    attachment_ids: Optional[List[int]] = Field(default=None, description="上传时 biz_id=0 的临时附件IDs，更新后关联到项目")

    @model_validator(mode="after")
    def check_dates(self):
        """同时提交起止日期时校验先后顺序（仅提交一端时由 Service 与库中值合并校验）"""
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class ProjectQueryParams(BaseModel):
    """项目列表查询筛选条件（所有字段可选，按 AND 组合；权限过滤由 Service 追加）"""
    # 关键词模糊匹配：名称/编号/简介
    keyword: Optional[str] = Field(default=None, max_length=128, description="项目名称/编号/简介关键词")
    # 类型/级别/学院/负责人/教师/状态：精确匹配
    project_type: Optional[int] = None
    project_level: Optional[int] = Field(default=None, ge=1, le=4)
    college_id: Optional[int] = None
    leader_id: Optional[int] = None
    teacher_id: Optional[int] = None
    status: Optional[int] = None
    # 立项年份区间：按 approval_time 或 created_at 年份过滤
    start_year: Optional[int] = Field(default=None, description="立项年份起")
    end_year: Optional[int] = Field(default=None, description="立项年份止")


class ProjectListItem(BaseModel):
    """
    项目列表项响应（GET /projects）

    ORM 字段直接映射，*_name 展示字段由 Service 回填（本层不做联表）。
    统计类字段（专家数/获奖数/可重提）为业务计算值，用于列表按钮与徽标。
    """
    model_config = ConfigDict(from_attributes=True)

    # 主键与业务编号/名称/类型/级别
    id: int
    project_no: Optional[str]
    project_name: str
    project_type: int
    project_type_name: str = ""
    project_level: int
    project_level_name: str = ""
    # 学院与人员展示字段：由 Service 关联 sys_college / sys_user 回填
    college_id: int
    college_name: str = ""
    leader_id: int
    leader_name: str = ""
    teacher_id: Optional[int]
    teacher_name: Optional[str] = None
    # 参赛信息：非参赛项目为空
    competition_id: Optional[int] = None
    competition_name: Optional[str] = None
    competition_session: Optional[str] = None
    # 执行期与经费
    start_date: Optional[date]
    end_date: Optional[date]
    budget_amount: Decimal
    used_amount: Decimal
    # 流程状态与文案
    status: int
    status_name: str = ""
    # 专家评审进度：已分配数 vs 已提交数（>0 后不可再改名单）
    assigned_expert_count: int = Field(default=0, description="已分配专家数量")
    reviewed_expert_count: int = Field(default=0, description="已提交评审的专家数量（>0 时不可再调整专家名单）")
    # 竞赛获奖成果数：成果类型=4 且未删除的计数
    award_count: int = Field(default=0, description="竞赛获奖成果数量（成果类型=4 且未删除）")
    # 可重提标志：仅指导教师驳回允许改后重提，其余阶段驳回即落选
    resubmittable: bool = Field(default=False, description="是否可修改后重新提交（仅「指导教师驳回」为 True；学院/校级/专家驳回即落选）")
    # 关键时间：提交/立项/创建
    submit_time: Optional[datetime]
    approval_time: Optional[datetime] = None
    created_at: datetime


class ProjectDetailResponse(ProjectListItem):
    """
    项目详情响应（GET /projects/{id}）

    在列表项基础上增加申报书正文、驳回原因、结题验收状态与流程截止日，
    以及完整的团队成员/预算/附件列表。
    """
    # 申报书正文
    project_summary: Optional[str] = None
    innovation_points: Optional[str] = None
    expected_results: Optional[str] = None
    # 最近一次驳回原因
    reject_reason: Optional[str] = None
    # —— 结题验收相关 ——
    final_report_submitted: bool = Field(default=False, description="是否已提交结项验收报告（待结题阶段）")
    final_report: Optional[str] = Field(default=None, description="结项验收报告正文")
    final_report_status: int = Field(
        default=0, description="结项报告状态：0未提交 1待验收 2已通过 3已驳回"
    )
    final_reject_reason: Optional[str] = Field(default=None, description="最近一次结题验收驳回意见")
    # 验收进度：专家总数 vs 已提交数，用于前端进度条
    final_review_total: int = Field(default=0, description="参与结题验收的专家数")
    final_review_done: int = Field(default=0, description="本轮已提交结题验收意见的专家数")
    # 当前用户维度的操作权限标记
    final_can_accept: bool = Field(default=False, description="当前用户是否可进行结题验收")
    final_reviewed_by_me: bool = Field(default=False, description="当前用户本轮是否已提交结题验收意见")
    # 结项条件检查清单：[{key,label,passed,detail}]，由 Service 计算
    final_checklist: List[dict] = Field(default_factory=list, description="结项条件检查清单")
    # 流程截止日（截止日驱动锁定）
    change_deadline: Optional[date] = Field(default=None, description="变更/延期申请锁死日（当前阶段审核日）")
    change_locked: bool = Field(default=False, description="是否已超过当前阶段审核日，变更/延期已锁定")
    midterm_deadline: Optional[date] = Field(default=None, description="中期报告提交截止日")
    final_deadline: Optional[date] = Field(default=None, description="结题报告提交截止日")
    # 子列表：成员/预算/附件
    team_members: List[TeamMemberResponse] = Field(default_factory=list)
    budgets: List[BudgetItemResponse] = Field(default_factory=list)
    attachments: List[dict] = Field(default_factory=list, description="项目附件列表")


class ProjectSubmitResponse(BaseModel):
    """提交审核后的响应：返回最新状态，供前端直接刷新徽标与按钮"""
    project_id: int
    status: int
    status_name: str
    message: str


class FinalSubmitRequest(BaseModel):
    """提交结项验收报告请求：正文必填，附件可选（临时附件ID）"""
    final_report: str = Field(min_length=1, max_length=2000, description="结项验收报告")
    attachment_ids: List[int] = Field(default_factory=list, description="结项验收报告附件IDs")


# ====================================================================
# 成果登记模型（用于项目归档部分）
# ====================================================================
class AchievementBase(BaseModel):
    """成果公共字段：类型必填，其余为登记信息；level 特指成果级别（1校级2省级3国家级）"""
    # 成果类型: 1论文 2专利 3软著 4竞赛获奖 5创业成果 6其他
    achievement_type: int = Field(..., ge=1, le=6, description="成果类型:1论文2专利3软著4竞赛5创业6其他")
    # 成果标题：必填
    title: str = Field(..., min_length=1, max_length=255)
    # 作者/发明人、发表/授权日期、刊物/机构、成果编号
    author: Optional[str] = Field(default=None, max_length=255)
    publish_date: Optional[date] = None
    publisher: Optional[str] = Field(default=None, max_length=255)
    achievement_no: Optional[str] = Field(default=None, max_length=128)
    # 成果级别: 1校级 2省级 3国家级（与项目级别 1院级2校级3省级4国家级 含义不同）
    level: Optional[int] = Field(default=None, ge=1, le=3, description="成果级别:1校级2省级3国家级")
    # 获奖等级：仅竞赛获奖类成果填写
    award_level: Optional[str] = Field(default=None, max_length=64)
    # 成果简介
    summary: Optional[str] = None


class AchievementCreate(AchievementBase):
    """登记成果请求：必须指定所属项目，可带证明材料临时附件"""
    project_id: int
    attachment_ids: List[int] = Field(default_factory=list, description="证明材料临时附件IDs（biz_id=0）")


class AchievementUpdate(BaseModel):
    """编辑项目成果：仅传入需要修改的字段"""
    # 类型/标题可改；level 仍限 1-3
    achievement_type: Optional[int] = Field(default=None, ge=1, le=6)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    author: Optional[str] = Field(default=None, max_length=255)
    publish_date: Optional[date] = None
    publisher: Optional[str] = Field(default=None, max_length=255)
    achievement_no: Optional[str] = Field(default=None, max_length=128)
    level: Optional[int] = Field(default=None, ge=1, le=3, description="成果级别:1校级2省级3国家级")
    award_level: Optional[str] = Field(default=None, max_length=64)
    summary: Optional[str] = None
    # 本次新增的证明材料附件（不传表示不改动已有附件）
    attachment_ids: List[int] = Field(default_factory=list, description="新增证明材料临时附件IDs（biz_id=0）")


class AchievementResponse(AchievementBase):
    """
    成果响应：在成果字段上追加认定状态与证明材料。

    review_status 默认 1（已认定）是兼容策略：早期成果没有认定记录，按已认定展示。
    """
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
    """成果认定请求：仅允许 1通过 / 2不通过（与成果 review_status 的 1/2 对应）"""
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
    """首页统计概览（GET /statistics/overview），数值口径由 Service 按权限范围计算"""
    # 四个核心计数：总数/待审核/已立项/已结题
    total_projects: int
    pending_review: int
    approved_projects: int
    finished_projects: int
    # 经费：预算总额与已使用
    total_budget: Decimal
    total_used: Decimal
    # 立项率 = 已立项 / 全部申报，百分比数值
    approval_rate: float = Field(default=0, description="整体立项率%")
    # —— 数据看板补充字段（真实数据）——
    # 供 ECharts 直接消费的分布数据
    category_dist: List[dict] = Field(default_factory=list, description="项目类别分布[{name,value}]")
    status_dist: List[dict] = Field(default_factory=list, description="项目状态分布[{name,value}]")
    budget_by_category: List[dict] = Field(default_factory=list, description="经费科目使用分布[{name,amount}]")


class CollegeStatisticsItem(BaseModel):
    """单学院统计数据（雷达图/热力图/学院立项率柱状图）"""
    # 学院标识与名称
    college_id: int
    college_name: str
    # 申报/立项/结题计数
    total_projects: int = 0
    approved_projects: int = 0
    finished_projects: int = 0
    # 经费汇总
    total_budget: Decimal = Decimal("0.00")
    total_used: Decimal = Decimal("0.00")
    # 立项率（%）、成果数、平均评审分
    approval_rate: float = 0.0
    achievements: int = 0
    avg_score: float = 0.0


# ====================================================================
# 经费报销 Schema
# ====================================================================
EXPENSE_STATUS_DRAFT = 0               # 草稿：可编辑，尚未进入审批流
EXPENSE_STATUS_PENDING_ADVISOR = 1      # 待导师审批：第一级
EXPENSE_STATUS_ADVISOR_APPROVED = 2     # 导师审批通过：瞬时态，随即转学院
EXPENSE_STATUS_PENDING_COLLEGE = 3      # 待学院审批：第二级
EXPENSE_STATUS_COLLEGE_APPROVED = 4     # 学院审批通过：瞬时态，随即转财务
EXPENSE_STATUS_PENDING_FINANCE = 5      # 待财务审批：第三级
EXPENSE_STATUS_COMPLETED = 6            # 已完成（已报销）：终态，累加项目/科目已用金额
EXPENSE_STATUS_REJECTED = 7            # 已驳回：退回申请人，可修改后重提


class ExpenseCreate(BaseModel):
    """
    创建报销申请请求（POST /expenses）

    必填：project_id、expense_amount（>0）、expense_desc；
    金额精度与库中 Numeric(12,2) 对齐，超出预算余额由 Service 校验。
    """
    project_id: int
    # 报销金额：必须大于 0，整数部分最多 10 位
    expense_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="报销金额(必须大于0)")
    # 费用说明：必填 1~500 字
    expense_desc: str = Field(min_length=1, max_length=500)
    # 发票号/预算科目：可选
    invoice_no: Optional[str] = Field(default=None, max_length=128)
    budget_item_id: Optional[int] = None
    # 票据临时附件：创建后回填 biz_id
    attachment_ids: List[int] = Field(default_factory=list, description="上传时 biz_id=0 的临时附件IDs，创建后关联到报销单")


class ExpenseListItem(BaseModel):
    """报销列表项响应：status_text 与 can_approve 由 Service 按当前用户回填"""
    id: int
    expense_no: str
    # 所属项目：project_name 为回填展示字段
    project_id: int
    project_name: Optional[str] = None
    # 申请人
    applicant_id: int
    applicant_name: str
    # 金额/说明/发票
    expense_amount: Decimal
    expense_desc: str
    invoice_no: Optional[str] = None
    # 审批状态与文案
    status: int
    status_text: str = ""
    reject_reason: Optional[str] = None
    # 关键时间
    submit_time: Optional[datetime] = None
    approval_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # 票据附件与当前用户审批权限
    attachments: List[dict] = Field(default_factory=list, description="报销票据附件")
    can_approve: bool = Field(default=False, description="当前登录用户是否可审批此单")

    model_config = ConfigDict(from_attributes=True)


class ExpenseReviewRequest(BaseModel):
    """审批请求：approved=True 推进到下一阶段，False 驳回并退回申请人"""
    approved: bool = Field(..., description="True=通过 False=驳回")
    opinion: Optional[str] = Field(default=None, max_length=500, description="审批意见")


class ExpenseQueryRequest(BaseModel):
    """[P1-5] 经费列表查询请求（Pydantic校验，替代裸dict）"""
    # 按申请人/项目过滤；project_id 用于核算该项目预算余额
    applicant_id: Optional[int] = Field(default=None, ge=1, description="申请人ID")
    project_id: Optional[int] = Field(default=None, ge=1, description="项目ID（用于按项目核算预算余额）")
    # 状态 1~7：不含草稿 0，供审批列表使用
    status: Optional[int] = Field(default=None, ge=1, le=7, description="报销状态 1-7")
    # 关键词：项目名称/单号/说明模糊匹配
    keyword: Optional[str] = Field(default=None, max_length=100, description="关键词(项目名称/单号/说明)")


class ExpenseSummary(BaseModel):
    """报销汇总：按当前筛选条件聚合，供列表页顶部卡片展示"""
    # 总单数 / 总金额 / 已通过金额 / 待审批单数
    total_count: int = 0
    total_amount: Decimal = Decimal("0")
    approved_amount: Decimal = Decimal("0")
    pending_count: int = 0
