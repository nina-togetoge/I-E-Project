"""
项目审核模块 Pydantic v2 数据模型
三级审核流程：学院初审 -> 校级复审 -> 专家评审
"""
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


# ====================================================================
# 审核阶段/结果枚举常量
# ====================================================================
REVIEW_STAGE_COLLEGE = 1       # 学院初审
REVIEW_STAGE_UNIVERSITY = 2    # 校级复审
REVIEW_STAGE_EXPERT = 3        # 专家评审
REVIEW_STAGE_FINAL = 4         # 结题验收

REVIEW_STAGE_NAME = {
    1: "学院初审", 2: "校级复审", 3: "专家评审", 4: "结题验收",
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
    review_stage: int = Field(..., ge=1, le=4, description="审核阶段:1学院2校级3专家4结题")
    review_result: int = Field(..., ge=1, le=3, description="结果:1通过2驳回3修改后重提")
    review_comment: Optional[str] = Field(default=None, max_length=1000, description="评审意见")


class ExpertReviewCreateRequest(BaseModel):
    """专家评审请求：额外包含评分"""
    project_id: int
    score: Decimal = Field(..., ge=0, le=100, decimal_places=2, description="专家评分(百分制)")
    review_result: int = Field(..., ge=1, le=3)
    review_comment: Optional[str] = Field(default=None, max_length=1000)


class ExpertAssignRequest(BaseModel):
    """分配专家到项目"""
    project_id: int
    expert_ids: List[int] = Field(..., min_length=1, max_length=10, description="评审专家ID列表")
    review_stage: int = Field(default=3, ge=1, le=4)


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
    budget_usage: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)


class MidtermCheckResponse(MidtermCheckCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: int
    status_name: str = ""
    reviewer_id: Optional[int] = None
    review_comment: Optional[str] = None
    review_time: Optional[datetime] = None
    submit_time: Optional[datetime] = None


class MidtermReviewRequest(BaseModel):
    """中期检查审核"""
    check_id: int
    result: int = Field(..., ge=1, le=4, description="结果:1通过2驳回3修改后重提")
    review_comment: str = Field(..., max_length=1000)


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
CHANGE_STATUS_NAME = {0: "待审核", 1: "导师同意", 2: "学院同意", 3: "校级同意", 4: "已驳回"}
MIDTERM_STATUS_NAME = {0: "草稿", 1: "待审核", 2: "审核通过", 3: "需修改", 4: "已驳回"}
