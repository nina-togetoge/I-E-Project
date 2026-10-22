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
REVIEW_STAGE_TEACHER = 0         # 指导教师确认
REVIEW_STAGE_COLLEGE = 1       # 学院初审
REVIEW_STAGE_UNIVERSITY = 2    # 校级复审
REVIEW_STAGE_EXPERT = 3        # 专家评审
REVIEW_STAGE_FINAL = 4         # 结题验收

REVIEW_STAGE_NAME = {
    0: "指导教师确认", 1: "学院初审", 2: "校级复审", 3: "专家评审", 4: "结题验收",
}

REVIEW_RESULT_PASS = 1         # 通过
REVIEW_RESULT_REJECT = 2       # 驳回
REVIEW_RESULT_MODIFY = 3       # 修改后重提

REVIEW_RESULT_NAME = {
    1: "通过", 2: "驳回", 3: "修改后重提",
}


# ====================================================================
# 审核请求/响应模型
# ====================================================================
class ReviewCreateRequest(BaseModel):
    """通用审核请求：学院/校级/结题验收 通用"""
    project_id: int = Field(..., description="项目ID")
    review_stage: int = Field(..., ge=0, le=4, description="审核阶段:0指导教师确认1学院2校级3专家4结题")
    review_result: int = Field(..., ge=1, le=3, description="结果:1通过2驳回3修改后重提")
    review_comment: Optional[str] = Field(default=None, max_length=1000, description="评审意见")

    @model_validator(mode="after")
    def _validate_reject_comment(self):
        """驳回（含已废弃的3修改后重提，统一按驳回处理）时必须填写评审意见"""
        if self.review_result != REVIEW_RESULT_PASS:
            if not self.review_comment or not self.review_comment.strip():
                raise ValueError("判定为驳回时，必须填写评审意见")
        return self


class ExpertReviewCreateRequest(BaseModel):
    """专家评审请求：额外包含评分"""
    project_id: int
    score: Decimal = Field(..., ge=0, le=100, decimal_places=2, description="专家评分(百分制)")
    review_result: int = Field(..., ge=1, le=2, description="专家评审结果:1通过 2驳回(不含已废弃的3修改后重提)")
    review_comment: Optional[str] = Field(default=None, max_length=1000)
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
    """分配专家到项目（仅针对专家评审阶段）"""
    project_id: int
    expert_ids: List[int] = Field(..., min_length=2, max_length=10, description="评审专家ID列表(至少2位)")


class ReviewRecordItem(BaseModel):
    """单条审核记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    review_stage: int
    review_stage_name: str = ""
    reviewer_id: int
    reviewer_name: str
    review_result: int
    review_result_name: str = ""
    score: Optional[Decimal] = None
    dim_scores: Optional[dict] = None
    review_comment: Optional[str] = None
    review_time: datetime
    created_at: datetime


class ProjectReviewFlowResponse(BaseModel):
    """项目完整审核流程响应（含所有阶段的所有审核记录）"""
    project_id: int
    current_status: int
    current_status_name: str
    current_stage_name: str
    records: List[ReviewRecordItem] = Field(default_factory=list)
    assigned_expert_ids: List[int] = Field(default_factory=list, description="已分配的专家ID列表(待评审)")


class ExpertProjectItem(BaseModel):
    """专家待评审项目列表项"""
    project_id: int
    project_no: Optional[str]
    project_name: str
    college_name: str
    leader_name: str
    project_type_name: str
    project_level_name: str
    submit_time: Optional[datetime]
    status: int
    my_score: Optional[Decimal] = None  # 当前专家已评分（若已评）
    my_review_result: Optional[int] = None


class MidtermCheckCreate(BaseModel):
    """中期检查提交请求"""
    project_id: int
    progress_desc: Optional[str] = None
    completed_tasks: Optional[str] = None
    remaining_tasks: Optional[str] = None
    problems: Optional[str] = None
    next_plan: Optional[str] = None
    report: Optional[str] = Field(default=None, max_length=10000, description="中期报告正文")
    budget_usage: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    attachment_ids: List[int] = Field(default_factory=list, description="中期报告附件IDs")


class MidtermCheckResponse(MidtermCheckCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: int
    status_name: str = ""
    reviewer_id: Optional[int] = None
    review_comment: Optional[str] = None
    review_time: Optional[datetime] = None
    submit_time: Optional[datetime] = None
    attachments: List[dict] = Field(default_factory=list, description="中期报告附件列表")


class MidtermReviewRequest(BaseModel):
    """中期检查审核"""
    check_id: int
    result: int = Field(..., ge=1, le=4, description="结果:1通过2驳回3修改后重提")
    review_comment: str = Field(..., max_length=1000)

    @model_validator(mode="after")
    def _validate_reject_comment(self):
        """判定为驳回(result=2)时必须填写评审意见"""
        if self.result == REVIEW_RESULT_REJECT:
            if not self.review_comment or not self.review_comment.strip():
                raise ValueError("判定为驳回时，必须填写评审意见")
        return self


class ChangeRequestCreate(BaseModel):
    """项目变更/延期申请"""
    project_id: int
    change_type: int = Field(..., ge=1, le=5, description="1延期2人员变更3内容变更4预算调整5其他")
    change_reason: str = Field(..., max_length=1000)
    original_content: Optional[str] = None
    new_content: Optional[str] = None


class ChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    project_name: Optional[str] = Field(default=None, description="所属项目名称（列表回填）")
    change_type: int
    change_type_name: str = ""
    change_reason: str
    original_content: Optional[str]
    new_content: Optional[str]
    applicant_id: int
    status: int
    status_name: str = ""
    reject_reason: Optional[str]
    submit_time: Optional[datetime]
    approval_time: Optional[datetime]
    created_at: datetime


CHANGE_TYPE_NAME = {1: "延期申请", 2: "人员变更", 3: "内容变更", 4: "预算调整", 5: "其他"}
# 单级状态：由指导教师一次审批即终态（0待审核 -> 3已通过 / 4已驳回；申请人可撤回为5）
CHANGE_STATUS_PENDING = 0
CHANGE_STATUS_APPROVED = 3
CHANGE_STATUS_REJECTED = 4
CHANGE_STATUS_WITHDRAWN = 5
CHANGE_STATUS_EXPIRED = 6  # 超过审批缓冲期自动作废（记录保留以便追责）
CHANGE_STATUS_NAME = {0: "待审核", 3: "已通过", 4: "已驳回", 5: "已撤回", 6: "已作废"}
CHANGE_MAX_TIMES = 2  # 同一项目累计可提交的变更申请次数上限（不含已撤回、已作废）
MIDTERM_STATUS_NAME = {0: "草稿", 1: "待审核", 2: "审核通过", 3: "需修改", 4: "已驳回", 5: "已作废"}
