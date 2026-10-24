# ====================================================================
# 审核/中期/变更模块 Schema
# --------------------------------------------------------------------
# 分组说明：
#   1. 阶段与结果枚举：REVIEW_STAGE_* / REVIEW_RESULT_* 及其 NAME 映射；
#   2. 审核入参：ReviewCreateRequest（通用）、ExpertReviewCreateRequest（带评分）、
#      ExpertAssignRequest（分配专家）；
#   3. 审核出参：ReviewRecordItem、ProjectReviewFlowResponse、ExpertProjectItem；
#   4. 中期检查：MidtermCheckCreate / MidtermCheckResponse / MidtermReviewRequest；
#   5. 变更申请：ChangeRequestCreate / ChangeRequestResponse 与状态常量。
# 审核阶段：0教师确认 1学院 2校级 3专家 4结题；结果：1通过 2驳回 3修改后重提，
# 专家分配占位记录用 99（不参与票数）。
# ====================================================================
"""
项目审核模块 Pydantic v2 数据模型
三级审核流程：学院初审 -> 校级复审 -> 专家评审
"""
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict, model_validator


# ====================================================================
# 审核阶段/结果枚举常量
# ====================================================================
REVIEW_STAGE_TEACHER = 0         # 指导教师确认：项目提交后的第一关
REVIEW_STAGE_COLLEGE = 1       # 学院初审：学院管理员审核
REVIEW_STAGE_UNIVERSITY = 2    # 校级复审：校级管理员审核
REVIEW_STAGE_EXPERT = 3        # 专家评审：多位专家打分
REVIEW_STAGE_FINAL = 4         # 结题验收：结题报告专家评审

# 阶段数值 -> 中文文案；流程详情页回填 review_stage_name
REVIEW_STAGE_NAME = {
    0: "指导教师确认", 1: "学院初审", 2: "校级复审", 3: "专家评审", 4: "结题验收",
}

REVIEW_RESULT_PASS = 1         # 通过：推进到下一阶段
REVIEW_RESULT_REJECT = 2       # 驳回：学院/校级/专家驳回即落选
REVIEW_RESULT_MODIFY = 3       # 修改后重提：历史语义，现统一按驳回处理

# 结果数值 -> 中文文案；注意 99 为专家分配占位，不在此映射内
REVIEW_RESULT_NAME = {
    1: "通过", 2: "驳回", 3: "修改后重提",
}


# ====================================================================
# 审核请求/响应模型
# ====================================================================
class ReviewCreateRequest(BaseModel):
    """通用审核请求：学院/校级/结题验收 通用（专家评审请用 ExpertReviewCreateRequest）"""
    # 待审核项目
    project_id: int = Field(..., description="项目ID")
    # 审核阶段 0-4
    review_stage: int = Field(..., ge=0, le=4, description="审核阶段:0指导教师确认1学院2校级3专家4结题")
    # 结果 1-3；3 已废弃但仍兼容入参
    review_result: int = Field(..., ge=1, le=3, description="结果:1通过2驳回3修改后重提")
    # 评审意见：非通过时必填，长度上限 1000
    review_comment: Optional[str] = Field(default=None, max_length=1000, description="评审意见")

    @model_validator(mode="after")
    def _validate_reject_comment(self):
        """驳回（含已废弃的3修改后重提，统一按驳回处理）时必须填写评审意见"""
        if self.review_result != REVIEW_RESULT_PASS:
            if not self.review_comment or not self.review_comment.strip():
                raise ValueError("判定为驳回时，必须填写评审意见")
        return self


class ExpertReviewCreateRequest(BaseModel):
    """
    专家评审请求：额外包含评分。

    专家结果只允许 1通过/2驳回（无"修改后重提"）；
    通过时分数不得低于及格线且意见不少于 10 字，驳回时意见必填。
    """
    project_id: int
    # 百分制评分，保留两位小数
    score: Decimal = Field(..., ge=0, le=100, decimal_places=2, description="专家评分(百分制)")
    # 专家结果 1-2
    review_result: int = Field(..., ge=1, le=2, description="专家评审结果:1通过 2驳回(不含已废弃的3修改后重提)")
    # 评审意见：通过≥10字，驳回必填
    review_comment: Optional[str] = Field(default=None, max_length=1000)
    # 分项评分：键为 创新性/可行性/团队/应用价值
    dim_scores: Optional[dict] = Field(default=None, description="分项评分明细：创新性/可行性/团队/应用价值")

    @model_validator(mode="after")
    def _validate_review_rule(self):
        """评审结果校验：
        - 通过(1)：评分不低于及格线，且评审意见不少于 10 字；
        - 驳回(2)：必须填写评审意见（说明驳回原因）。
        """
        if self.review_result == REVIEW_RESULT_PASS:
            from app.core.config import settings
            if self.score < settings.EXPERT_PASS_SCORE:
                raise ValueError(f"评分低于及格线({settings.EXPERT_PASS_SCORE}分)，不能判定为通过")
            if not self.review_comment or len(self.review_comment.strip()) < 10:
                raise ValueError("判定为通过时，评审意见不得少于10个字符")
        elif self.review_result == REVIEW_RESULT_REJECT:
            if not self.review_comment or not self.review_comment.strip():
                raise ValueError("判定为驳回时，必须填写评审意见")
        return self


class ExpertAssignRequest(BaseModel):
    """分配专家到项目（仅针对专家评审阶段）：至少 2 位、最多 10 位，避免单专家一言堂"""
    project_id: int
    # 专家名单：2~10 位，提交后写入 99 占位审核记录
    expert_ids: List[int] = Field(..., min_length=2, max_length=10, description="评审专家ID列表(至少2位)")


class ReviewRecordItem(BaseModel):
    """单条审核记录响应：*_name 由 Service 依据 NAME 映射回填"""
    model_config = ConfigDict(from_attributes=True)

    # 记录主键与项目
    id: int
    project_id: int
    # 阶段及其文案
    review_stage: int
    review_stage_name: str = ""
    # 审核人快照
    reviewer_id: int
    reviewer_name: str
    # 结果及其文案（99 表示占位，name 可能为空）
    review_result: int
    review_result_name: str = ""
    # 评分与分项评分（仅专家阶段有值）
    score: Optional[Decimal] = None
    dim_scores: Optional[dict] = None
    # 意见与时间
    review_comment: Optional[str] = None
    review_time: datetime
    created_at: datetime


class ProjectReviewFlowResponse(BaseModel):
    """项目完整审核流程响应（含所有阶段的所有审核记录）"""
    project_id: int
    # 当前项目状态与文案
    current_status: int
    current_status_name: str
    # 当前所处阶段名称
    current_stage_name: str
    # 全部审核记录，按时间/阶段排序由 Service 保证
    records: List[ReviewRecordItem] = Field(default_factory=list)
    # 已分配但尚未评审的专家（来自 99 占位记录）
    assigned_expert_ids: List[int] = Field(default_factory=list, description="已分配的专家ID列表(待评审)")


class ExpertProjectItem(BaseModel):
    """专家待评审项目列表项：my_* 为当前专家本人的评审结果回填"""
    project_id: int
    # 项目编号/名称/学院/负责人
    project_no: Optional[str]
    project_name: str
    college_name: str
    leader_name: str
    # 类型与级别文案
    project_type_name: str
    project_level_name: str
    # 提交时间与当前状态
    submit_time: Optional[datetime]
    status: int
    # 本人评分与结论（未评审为 None）
    my_score: Optional[Decimal] = None  # 当前专家已评分（若已评）
    my_review_result: Optional[int] = None


class MidtermCheckCreate(BaseModel):
    """中期检查提交请求：各汇报项可选，report 正文上限 10000 字；附件为临时附件ID"""
    project_id: int
    # 结构化汇报项
    progress_desc: Optional[str] = None
    completed_tasks: Optional[str] = None
    remaining_tasks: Optional[str] = None
    problems: Optional[str] = None
    next_plan: Optional[str] = None
    # 中期报告正文
    report: Optional[str] = Field(default=None, max_length=10000, description="中期报告正文")
    # 已使用经费：非负、两位小数
    budget_usage: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    # 附件临时ID
    attachment_ids: List[int] = Field(default_factory=list, description="中期报告附件IDs")


class MidtermCheckResponse(MidtermCheckCreate):
    """中期检查响应：追加审核状态、审核信息与附件列表"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    # 状态 0草稿 1待审核 2通过 3需修改 4驳回（5已作废见 MIDTERM_STATUS_NAME）
    status: int
    status_name: str = ""
    # 审核信息
    reviewer_id: Optional[int] = None
    review_comment: Optional[str] = None
    review_time: Optional[datetime] = None
    submit_time: Optional[datetime] = None
    # 附件列表：[{id,name,url,size}]
    attachments: List[dict] = Field(default_factory=list, description="中期报告附件列表")


class MidtermReviewRequest(BaseModel):
    """中期检查审核：result 1通过 2驳回 3修改后重提（4 预留）"""
    check_id: int
    # 审核结论 1-4
    result: int = Field(..., ge=1, le=4, description="结果:1通过2驳回3修改后重提")
    # 审核意见：必填
    review_comment: str = Field(..., max_length=1000)

    @model_validator(mode="after")
    def _validate_reject_comment(self):
        """判定为驳回(result=2)时必须填写评审意见"""
        if self.result == REVIEW_RESULT_REJECT:
            if not self.review_comment or not self.review_comment.strip():
                raise ValueError("判定为驳回时，必须填写评审意见")
        return self


class ChangeRequestCreate(BaseModel):
    """项目变更/延期申请：变更类型与原因必填；原/新内容用于对照留痕"""
    project_id: int
    # 变更类型: 1延期 2人员变更 3内容变更 4预算调整 5其他
    change_type: int = Field(..., ge=1, le=5, description="1延期2人员变更3内容变更4预算调整5其他")
    # 变更原因：必填，上限 1000 字
    change_reason: str = Field(..., max_length=1000)
    # 变更前 / 变更后内容
    original_content: Optional[str] = None
    new_content: Optional[str] = None


class ChangeRequestResponse(BaseModel):
    """变更申请响应：*_name、project_name 由 Service 回填"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    project_name: Optional[str] = Field(default=None, description="所属项目名称（列表回填）")
    # 变更类型及文案
    change_type: int
    change_type_name: str = ""
    # 原因与内容对照
    change_reason: str
    original_content: Optional[str]
    new_content: Optional[str]
    # 申请人
    applicant_id: int
    # 审批状态及文案
    status: int
    status_name: str = ""
    reject_reason: Optional[str]
    # 时间
    submit_time: Optional[datetime]
    approval_time: Optional[datetime]
    created_at: datetime


# 变更类型映射：1 延期 / 2 人员变更 / 3 内容变更 / 4 预算调整 / 5 其他
CHANGE_TYPE_NAME = {1: "延期申请", 2: "人员变更", 3: "内容变更", 4: "预算调整", 5: "其他"}
# 单级状态：由指导教师一次审批即终态（0待审核 -> 3已通过 / 4已驳回；申请人可撤回为5）
CHANGE_STATUS_PENDING = 0    # 待审核：已提交，等待指导教师处理
CHANGE_STATUS_APPROVED = 3   # 已通过：审批终态，变更内容生效
CHANGE_STATUS_REJECTED = 4   # 已驳回：审批终态，申请人可重新发起（占用配额）
CHANGE_STATUS_WITHDRAWN = 5  # 已撤回：申请人主动撤回，不占配额
CHANGE_STATUS_EXPIRED = 6  # 超过审批缓冲期自动作废（记录保留以便追责）
# 变更状态映射：仅当前单级审批的 4 个有效状态 + 作废
CHANGE_STATUS_NAME = {0: "待审核", 3: "已通过", 4: "已驳回", 5: "已撤回", 6: "已作废"}
CHANGE_MAX_TIMES = 2  # 同一项目累计可提交的变更申请次数上限（不含已撤回、已作废）
# 中期检查状态映射：0 草稿 / 1 待审核 / 2 审核通过 / 3 需修改 / 4 已驳回 / 5 已作废
MIDTERM_STATUS_NAME = {0: "草稿", 1: "待审核", 2: "审核通过", 3: "需修改", 4: "已驳回", 5: "已作废"}
