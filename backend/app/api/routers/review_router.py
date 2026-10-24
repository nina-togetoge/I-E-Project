"""
项目审核模块 API 路由层
"""
# ====================================================================
# 项目审核 / 中期检查 / 变更延期路由
# ----------------------------------------------------------------------------
# 对外接口分组：
#   /api/reviews   GET "" 待我审核列表、POST "" 通用审核（指导教师确认/学院初审/
#                  校级复审/结题验收）、POST /expert 专家打分、POST /assign-experts
#                  分配专家、GET /flow/{project_id} 审核流程时间线、
#                  GET /expert-tasks 专家待办/已评历史
#   /api/midterm   GET /by-project/{id} 查询、POST /draft 存草稿、POST /submit 提交、
#                  POST /withdraw 撤回、POST /review 审核
#   /api/changes   POST "" 发起、GET "" 列表、POST /{id}/approve 通过、
#                  POST /{id}/reject 驳回、POST /{id}/withdraw 撤回、
#                  POST /{id}/resubmit 重新提交
# 前端对应：教师/管理员「审核中心」、专家评审页、学生「中期检查」「变更申请」。
# 依赖 Service：ReviewService（通用审核/专家评审/专家分配/流程查询）、
#               MidtermService、ChangeService。
# 权限约束：
#   - 待审核列表仅教师、管理员（专家走 /expert-tasks）；
#   - 通用审核允许教师/专家/管理员，服务层按审核阶段校验具体审核人；
#   - 专家打分仅专家与超管；分配专家仅超管/学院管理员，学院管理员限本院；
#   - 流程查询复用项目详情可见性（草稿仅本人/成员、教师限本院、专家限被分配）。
# 状态机与特殊规则：
#   - 审核阶段：0 指导教师确认 / 1 学院初审 / 2 校级复审 / 3 专家评审 / 4 结题验收；
#   - 项目状态：0草稿/1待学院初审/3待校级复审/5待专家评审/6已立项/7中期检查中/
#     8待结题/9已结题/10已驳回/12待指导教师确认/13待分配评审专家；
#   - 指导教师确认受截止日（学院初审审核日）限制；学院/校级审核不锁；
#   - 结题报告提交受截止日限制，但提交后的验收不受截止日限制，避免逾期卡死；
#   - 结题验收必须先有负责人提交的报告占位记录(review_result=99)，且满足
#     中期已通过、成果≥1、报销结清三条件；
#   - 专家评审使用项目行锁串行化，待全部已分配专家提交后按多数+平均分结算；
#   - 专家之间不可见彼此评分，保证打分独立性；
#   - 变更申请每阶段限 1 次、累计次数上限，超审批缓冲期自动作废。
# ====================================================================
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, OperationContext
from app.core.security import (
    RequireRole, RoleEnum, require_login, require_admin,
)
from app.core.response import ResponseModel, success, PageResult
from app.database.session import get_db
from app.models import SysUser
from app.schemas.review import (
    ReviewCreateRequest, ExpertReviewCreateRequest, ExpertAssignRequest,
    ReviewRecordItem, ProjectReviewFlowResponse, ExpertProjectItem,
    MidtermCheckCreate, MidtermCheckResponse, MidtermReviewRequest,
    ChangeRequestCreate, ChangeRequestResponse,
)
from app.schemas.project import ProjectListItem
from app.services.review_service import ReviewService, MidtermService, ChangeService


router_review = APIRouter(prefix="/reviews", tags=["项目审核流程"])
router_midterm = APIRouter(prefix="/midterm", tags=["中期检查"])
router_change = APIRouter(prefix="/changes", tags=["变更/延期申请"])


# ====================================================================
# 项目审核流程接口
# ====================================================================

# --- 接口说明 ---
# GET /api/reviews：待我审核的项目列表。
# 谁可以调用：教师(2)、管理员(4)；专家待办走 /reviews/expert-tasks。
# 数据范围：教师只看 status=12 且自己是指导教师的项目；
#           学院管理员只看本院 status=1；超管看 status=3 与 13。
# 入参：keyword 项目名/编号模糊搜索；page/page_size 分页。
# 返回：PageResult[ProjectListItem]，含项目状态、学院、负责人、指导教师等。
# 副作用：只读。
@router_review.get("", response_model=ResponseModel[PageResult[ProjectListItem]],
                   summary="待我审核的项目列表(教师/学院管理员/超管)")
def api_review_list(
    keyword: Optional[str] = Query(default=None, max_length=100),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(
        RoleEnum.TEACHER, RoleEnum.ADMIN
    )),
):
    items, total = ReviewService.pending_projects(db, current_user, pager, keyword)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


# --- 接口说明 ---
# POST /api/reviews：提交通用审核结果（指导教师确认/学院初审/校级复审/结题验收）。
# 谁可以调用：教师、专家、管理员；具体审核人由服务层按阶段与项目归属校验。
# 入参：project_id、review_stage(0/1/2/4)、review_result(通过/驳回)、review_comment。
# 返回：新写入的 ReviewRecordItem（含阶段名、结果名）。
# 异常：专家阶段误走此接口、状态不匹配、重复审核、超指导教师确认截止日、
#       结项条件/报告未满足 → 参数异常；无权审核 → 403；项目不存在 → 404。
# 副作用：新增审核记录、推进项目状态、写驳回原因/立项时间、通知负责人、
#         刷新 current_approver_id；写审计日志。
@router_review.post("", response_model=ResponseModel[ReviewRecordItem],
                    summary="提交审核结果(学院初审/校级复审/结题验收通用)")
def api_do_review(
    req: ReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(
        RoleEnum.TEACHER, RoleEnum.EXPERT, RoleEnum.ADMIN
    )),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"审核项目#{req.project_id}(阶段{req.review_stage})")
        data = ReviewService.do_review(db, req, current_user)
    return success(data=data, message="审核完成")


# --- 接口说明 ---
# POST /api/reviews/expert：专家提交评审（含评分）。
# 谁可以调用：专家(3) 与超管（超管可代操作演示）；学院管理员不得代替专家打分。
# 入参：project_id、score、dim_scores 分项评分、review_result、review_comment。
# 返回：该专家本次的 ReviewRecordItem。
# 异常：非专家/未被分配 → 403；项目不在待专家评审(5)、重复打分 → 参数异常。
# 副作用：更新/新增专家评审记录；最后一位专家提交时按“多数同意 + 平均分及格”
#         结算立项(6)或驳回(10)，并刷新当前审批人；写审计日志。
@router_review.post("/expert", response_model=ResponseModel[ReviewRecordItem], summary="专家提交评审(含评分)")
def api_expert_review(
    req: ExpertReviewCreateRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.EXPERT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"专家评审项目#{req.project_id}，评分{req.score}")
        data = ReviewService.do_expert_review(db, req, current_user)
    return success(data=data, message="评审提交成功")


# --- 接口说明 ---
# POST /api/reviews/assign-experts：为项目分配/调整评审专家。
# 谁可以调用：管理员（require_admin）；服务层限定超管全校、学院管理员仅本院。
# 入参：project_id；expert_ids 为本次期望的完整名单（全量覆盖语义，不是增量追加）。
# 返回：{assigned_count: 去重后人数, project_id}。
# 异常：项目阶段不可分配、已有专家正式打分（名单锁定）、人数不足 EXPERT_MIN_COUNT、
#       含非专家用户 → 参数异常；跨院分配 → 403。
# 副作用：增删 stage=3 的 99 占位记录；待分配(13) 推进到待专家评审(5)；写审计日志。
@router_review.post("/assign-experts", response_model=ResponseModel, summary="分配专家到项目")
def api_assign_experts(
    req: ExpertAssignRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"为项目#{req.project_id}分配{len(req.expert_ids)}位专家")
        data = ReviewService.assign_experts(db, req, current_user)
    return success(data=data, message="专家分配完成")


# --- 接口说明 ---
# GET /api/reviews/flow/{project_id}：查询项目完整审核流程。
# 谁可以调用：任意已登录用户，但需对项目有可见权限（复用项目详情规则）。
# 入参：project_id 项目主键。
# 返回：ProjectReviewFlowResponse（正式审核记录时间线、当前状态/阶段名、
#       已分配未评审专家 id 列表）。
# 异常：项目不存在 → 404；无权查看 → 403。
# 特殊规则：专家只能看到自己的专家/结题评审记录，避免参考他人评分；
#           占位记录(99)不出现在时间线，仅用于推导已分配专家名单。
@router_review.get("/flow/{project_id}", response_model=ResponseModel[ProjectReviewFlowResponse],
                   summary="查询项目完整审核流程记录")
def api_review_flow(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    return success(data=ReviewService.get_review_flow(db, project_id, current_user))


# --- 接口说明 ---
# GET /api/reviews/expert-tasks：专家项目列表（待办 / 已评审历史）。
# 谁可以调用：专家(3)、管理员(4)。
# 入参：scope=pending 待我评审（默认）/ reviewed 我已评审历史；keyword 项目名搜索；分页。
# 返回：PageResult[ExpertProjectItem]。
# 副作用：只读；按专家本人 id 过滤，不会返回其他专家任务。
@router_review.get("/expert-tasks", response_model=ResponseModel[PageResult[ExpertProjectItem]],
                   summary="专家项目列表(待办/已评审历史)")
def api_expert_tasks(
    keyword: Optional[str] = None,
    scope: str = Query(default="pending", pattern="^(pending|reviewed)$",
                       description="pending=待我评审; reviewed=我已评审(历史)"),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.EXPERT, RoleEnum.ADMIN)),
):
    # 1. 按 scope 选择服务方法：pending 只含未打分占位，reviewed 只含已提交正式结论
    service = (ReviewService.expert_reviewed_projects if scope == "reviewed"
               else ReviewService.expert_pending_projects)
    items, total = service(db, current_user.id, pager, keyword)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


# ====================================================================
# 中期检查接口
# ====================================================================

# --- 接口说明 ---
# GET /api/midterm/by-project/{project_id}：查询项目中期检查。
# 谁可以调用：任意已登录用户，但需对项目有可见权限。
# 入参：project_id 项目主键（不是中期检查记录 id）。
# 返回：MidtermCheckResponse；尚未创建中期记录时 data 为 null，前端展示空表单。
# 异常：项目不存在 → 404；无权查看 → 403。
# 副作用：只读。
@router_midterm.get("/by-project/{project_id}", response_model=ResponseModel[Optional[MidtermCheckResponse]],
                    summary="查询项目中期检查")
def api_midterm_get(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    return success(data=MidtermService.get_by_project(db, project_id, current_user))


# --- 接口说明 ---
# POST /api/midterm/draft：保存中期检查草稿。
# 谁可以调用：项目负责人本人（超管可代操作）。
# 入参：项目 id、进展说明、经费使用、附件 ids 等。
# 返回：MidtermCheckResponse，记录状态为 0 草稿。
# 特殊规则：草稿不受提交截止日限制，且不推进项目状态，避免学生因截止日丢失已写内容。
# 副作用：创建或复用该项目唯一的中期记录；绑定本人临时附件；写审计日志。
@router_midterm.post("/draft", response_model=ResponseModel[MidtermCheckResponse], summary="保存中期检查草稿")
def api_midterm_save(
    req: MidtermCheckCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"保存项目#{req.project_id}中期检查草稿")
        data = MidtermService.submit(db, req, current_user, is_draft=True)
    return success(data=data, message="草稿保存成功")


# --- 接口说明 ---
# POST /api/midterm/submit：正式提交中期检查。
# 谁可以调用：项目负责人本人（超管可代操作）。
# 返回：MidtermCheckResponse，状态 1 待审核。
# 异常：项目不在已立项(6)/中期检查中(7)、超过中期提交截止日、已通过或审核中 → 参数异常。
# 副作用：记录提交时间；项目 6→7；绑定附件；进入教师/管理员审核待办；写审计日志。
@router_midterm.post("/submit", response_model=ResponseModel[MidtermCheckResponse], summary="提交中期检查")
def api_midterm_submit(
    req: MidtermCheckCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"提交项目#{req.project_id}中期检查")
        data = MidtermService.submit(db, req, current_user, is_draft=False)
    return success(data=data, message="中期检查已提交审核")


# --- 接口说明 ---
# POST /api/midterm/withdraw：撤回已提交的中期检查报告。
# 谁可以调用：项目负责人本人（超管可代操作）。
# 入参：check_id 中期检查记录 id（不是项目 id）。
# 返回：MidtermCheckResponse，状态退回 0 草稿。
# 异常：记录不在待审核(1)、已过中期截止日 → 参数异常。
# 特殊规则：项目状态保持 7（中期流程已开启），不回退到 6；写审计日志。
@router_midterm.post("/withdraw", response_model=ResponseModel[MidtermCheckResponse],
                     summary="撤回中期检查报告提交")
def api_midterm_withdraw(
    check_id: int = Query(..., description="中期检查记录ID"),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"撤回中期检查#{check_id}提交")
        data = MidtermService.withdraw(db, check_id, current_user)
    return success(data=data, message="已撤回提交，可重新填写并提交")


# --- 接口说明 ---
# POST /api/midterm/review：审核中期检查。
# 谁可以调用：教师、管理员、专家；服务层按项目归属校验审核资格。
# 入参：check_id、result（通过/驳回）、审核意见。
# 返回：更新后的 MidtermCheckResponse。
# 异常：记录不在待审核、无权审核 → 业务异常/403。
# 副作用：写入审核结论与时间；通过后项目可进入结题阶段，驳回后学生可修改重提；
#         通知负责人；写审计日志。
@router_midterm.post("/review", response_model=ResponseModel[MidtermCheckResponse], summary="审核中期检查")
def api_midterm_review(
    req: MidtermReviewRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.TEACHER, RoleEnum.ADMIN, RoleEnum.EXPERT)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"审核中期检查#{req.check_id}，结果={req.result}")
        data = MidtermService.review(db, req, current_user)
    return success(data=data, message="中期审核完成")


# ====================================================================
# 变更/延期申请接口
# ====================================================================

# --- 接口说明 ---
# POST /api/changes：发起变更/延期申请。
# 谁可以调用：项目负责人本人（超管可代操作）。
# 入参：project_id、change_type、原因、原内容/新内容等。
# 返回：ChangeRequestResponse（状态=待审核）。
# 异常：当前阶段不可申请、已过阶段审核日、本阶段已用过 1 次、累计超限、
#       已有待审批申请 → 参数异常。
# 特殊规则：提交时快照项目状态，作为“每阶段 1 次”配额与后续回退依据；
#           超审批缓冲期的旧申请先被清扫作废，已作废不占配额。
# 副作用：写变更申请表并提交；写审计日志。
@router_change.post("", response_model=ResponseModel[ChangeRequestResponse], summary="提交变更/延期申请")
def api_change_create(
    req: ChangeRequestCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"提交项目#{req.project_id}变更/延期申请(类型{req.change_type})")
        data = ChangeService.create(db, req, current_user)
    return success(data=data, message="申请提交成功")


# --- 接口说明 ---
# GET /api/changes：变更/延期申请分页列表。
# 谁可以调用：任意已登录用户，按角色裁剪可见范围：
#   学生=本人申请；超管=全校；学院管理员=本院；教师=本人指导；专家=被分配项目。
# 入参：project_id、change_type、status 可选过滤；page/page_size 分页。
# 返回：PageResult[ChangeRequestResponse]。
# 副作用：查询前会清扫超期未审申请（自动置为已作废）并提交。
@router_change.get("", response_model=ResponseModel[PageResult[ChangeRequestResponse]],
                   summary="变更/延期申请列表")
def api_change_list(
    project_id: Optional[int] = None,
    change_type: Optional[int] = None,
    status: Optional[int] = None,
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 传入当前用户，由服务层按角色计算可见项目集合或本人申请范围
    items, total = ChangeService.paginate(db, pager, project_id, change_type, status, current_user)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


# --- 接口说明 ---
# POST /api/changes/{change_id}/approve：审批变更申请（通过）。
# 谁可以调用：教师、管理员；服务层限定为该项目的指导教师或所属学院管理员（超管可代操作）。
# 入参：change_id；comment 审批意见（≤1000 字）。
# 返回：更新后的 ChangeRequestResponse。
# 异常：申请非待审核、项目状态已变化、已过“审核日+1天”缓冲期 → 参数异常；无权 → 403。
# 副作用：按提交时所处阶段把项目回退到上一审核段，并软删后续阶段的正式审核记录，
#         使项目重新走受影响流程；写审计日志。
@router_change.post("/{change_id}/approve", response_model=ResponseModel[ChangeRequestResponse],
                    summary="审批变更申请(通过)")
def api_change_approve(
    change_id: int,
    comment: str = Query(default="", max_length=1000, description="审批意见"),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.TEACHER, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"审批变更申请#{change_id}通过")
        data = ChangeService.approve(db, change_id, approve=True, comment=comment, operator=current_user)
    return success(data=data, message="已通过")


# --- 接口说明 ---
# POST /api/changes/{change_id}/reject：审批变更申请（驳回）。
# 谁可以调用：该项目的指导教师或所属学院管理员（超管可代操作）。
# 入参：change_id；comment 驳回理由（建议必填，便于学生修改）。
# 返回：更新后的 ChangeRequestResponse。
# 异常：同审批通过；申请不在待审核 → 参数异常。
# 副作用：仅改申请状态与驳回原因，不回退项目状态、不删除审核记录；写审计日志。
@router_change.post("/{change_id}/reject", response_model=ResponseModel[ChangeRequestResponse],
                    summary="审批变更申请(驳回)")
def api_change_reject(
    change_id: int,
    comment: str = Query(default="", max_length=1000, description="驳回理由"),
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.TEACHER, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"驳回变更申请#{change_id}")
        data = ChangeService.approve(db, change_id, approve=False, comment=comment, operator=current_user)
    return success(data=data, message="已驳回")


# --- 接口说明 ---
# POST /api/changes/{change_id}/withdraw：申请人撤回变更申请。
# 谁可以调用：申请提交人本人（超管可代操作）。
# 入参：change_id。
# 返回：更新后的 ChangeRequestResponse。
# 异常：非本人或申请不在待审核 → 403/参数异常。
# 特殊规则：撤回不退配额（仍计入每阶段 1 次），防止反复提交-撤回试错；写审计日志。
@router_change.post("/{change_id}/withdraw", response_model=ResponseModel[ChangeRequestResponse],
                    summary="撤回变更申请(申请人)")
def api_change_withdraw(
    change_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"撤回变更申请#{change_id}")
        data = ChangeService.withdraw(db, change_id, current_user)
    return success(data=data, message="已撤回")


# --- 接口说明 ---
# POST /api/changes/{change_id}/resubmit：重新提交被驳回的变更申请。
# 谁可以调用：原申请人本人（超管可代操作）。
# 入参：change_id；req 为更新后的申请内容。
# 返回：更新后的 ChangeRequestResponse（回到待审核）。
# 异常：申请不是已驳回状态、项目状态/截止日不再允许 → 参数异常。
# 副作用：覆盖申请内容、重置审核状态与驳回原因；写审计日志。
@router_change.post("/{change_id}/resubmit", response_model=ResponseModel[ChangeRequestResponse],
                    summary="重新提交被驳回的变更申请")
def api_change_resubmit(
    change_id: int,
    req: ChangeRequestCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        ctx.set_desc(f"重新提交变更申请#{change_id}")
        data = ChangeService.resubmit(db, change_id, req, current_user)
    return success(data=data, message="已重新提交")
