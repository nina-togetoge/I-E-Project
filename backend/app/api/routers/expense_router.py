"""
经费报销模块 API 路由
"""
# ====================================================================
# 经费报销路由
# ----------------------------------------------------------------------------
# 对外接口分组（前缀 /api/expenses）：
#   POST /list              报销分页列表（POST 因筛选条件较多，避免超长 URL）
#   POST ""                 提交报销申请
#   PATCH /{expense_id}/review 分级审批（导师 / 学院 / 财务）
# 前端对应：项目「经费报销」页（学生提交与查看）、教师/学院/管理端审批页。
# 依赖 Service：ExpenseService（创建、分页、汇总、审批状态推进）。
# 权限约束：
#   - 列表：学生只能看本人申请；教师/学院管理员按 DataScope 限定本院；超管全校；
#   - 提交：仅项目负责人本人（超管可代操作）；
#   - 审批：路由要求管理员或教师；服务层按状态分级校验具体审批人，
#     待导师阶段必须指导教师本人，学院阶段必须本院学院管理员，财务终审必须超管。
# 报销状态机：0 草稿 / 1 待导师 / 2 导师通过 / 3 待学院 / 4 学院通过 /
#             5 待财务 / 6 完成 / 7 驳回。
# 特殊业务规则：
#   - 创建即提交（直接进入状态 1），不存在草稿提交动作；
#   - 金额受项目总预算与预算科目余额双重限制，已驳回单据释放额度；
#   - 财务终审完成(6)时回写项目与预算科目的 used_amount，并加行级锁防止并发重复累加；
#   - 驳回是终态，不可再次审批；审批接口使用 SELECT ... FOR UPDATE 串行化。
# ====================================================================
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, DataScope, OperationContext
from app.core.security import (
    RequireRole, RoleEnum, require_login, is_super_admin, is_college_admin,
)
from app.core.response import ResponseModel, success, PageResult
from app.core.exceptions import BizException, PermissionDeniedException, ParamValidateException
from app.database.session import get_db
from app.models import SysUser, ProjProject, ProjExpense
from app.schemas.project import (
    ExpenseCreate, ExpenseListItem, ExpenseReviewRequest, ExpenseSummary,
    ExpenseQueryRequest,
    EXPENSE_STATUS_PENDING_ADVISOR,
    EXPENSE_STATUS_ADVISOR_APPROVED,
    EXPENSE_STATUS_PENDING_COLLEGE,
    EXPENSE_STATUS_COLLEGE_APPROVED,
    EXPENSE_STATUS_PENDING_FINANCE,
)
from app.services.expense_service import ExpenseService

router_expense = APIRouter(prefix="/expenses", tags=["经费报销"])


# --- 接口说明 ---
# POST /api/expenses/list：报销单分页列表。
# 谁可以调用：任意已登录用户，服务端按角色自动收敛数据范围。
# 入参（JSON）：applicant_id / project_id / status / keyword 可选筛选；分页参数走 Query。
# 返回：{items, total, page, page_size, summary}；
#       summary 为当前数据范围内的金额汇总（申请数、通过数、金额合计等）。
# 权限：学生强制 applicant_id=自己；教师/学院管理员按 college_ids 限本院；超管全校。
# 副作用：只读查询；can_approve 为列表项附加标记，不写库。
@router_expense.post("/list", response_model=ResponseModel, summary="报销列表(分页)")
def api_expense_list(
    data: ExpenseQueryRequest,
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    """POST方式列表查询，支持筛选"""
    # 1. 取出前端筛选条件；后续会按角色覆盖 applicant_id / college_ids
    applicant_id = data.applicant_id
    project_id = data.project_id
    status = data.status
    keyword = data.keyword

    # 2. 角色 → 数据范围（修复学院管理员越权看全校经费的Bug）
    scope = data_scope.scope
    college_ids: Optional[list] = None
    if not scope.get("all"):
        if current_user.role not in (RoleEnum.ADMIN, RoleEnum.TEACHER):
            # 学生：无视前端传参，强制只看本人申请，防止遍历他人报销
            applicant_id = current_user.id
        else:
            # 学院管理员 / 教师 → 学院范围过滤（教师仅本院，学院管理员仅绑定学院）
            college_ids = scope.get("college_ids")

    # 3. 分页查询；offset/limit 由 PaginationParams 根据 page/page_size 计算
    items, total = ExpenseService.paginate(
        db, pager.offset, pager.limit,
        applicant_id=applicant_id,
        project_id=project_id,
        status=status,
        keyword=keyword,
        college_ids=college_ids,
    )
    item_list = ExpenseService.to_list_items(db, items)
    # 4. 批量取项目元信息（指导教师/学院），用于逐条判断当前用户能否审批
    # 按当前用户所处审批阶段标记是否可审批，避免前端对无权单据弹出 403
    proj_map = {}
    if item_list:
        proj_map = {
            pid: (tid, cid)
            for pid, tid, cid in db.query(
                ProjProject.id, ProjProject.teacher_id, ProjProject.college_id
            ).filter(ProjProject.id.in_([it.project_id for it in item_list])).all()
        }
    # 5. can_approve 只影响前端按钮显隐，真正的权限仍在审批接口二次校验
    for it in item_list:
        it.can_approve = _can_user_approve(current_user, it.status, proj_map.get(it.project_id))
    # 6. 汇总统计与列表使用同一过滤条件，保证总数/金额与列表可见范围一致
    summary = ExpenseService.get_summary(db, applicant_id, college_ids=college_ids)
    return success(data={
        "items": item_list,
        "total": total,
        "page": pager.page,
        "page_size": pager.page_size,
        "summary": summary.model_dump(),
    })


# --- 接口说明 ---
# POST /api/expenses：提交报销申请。
# 谁可以调用：项目负责人本人（超管可代任意项目提交）。
# 入参：project_id、expense_amount、expense_desc、invoice_no、budget_item_id、附件 ids。
# 返回：ExpenseListItem（含报销单号、状态=1 待导师、可审批标记等）。
# 异常：项目不存在、金额超项目/科目预算、科目不属于该项目 → 业务异常；无权 → 403。
# 副作用：生成全局唯一报销单号、绑定本人临时附件；单据直接进入待导师审批；
#         写审计日志（描述由 ctx 补充）。
@router_expense.post("", response_model=ResponseModel[ExpenseListItem], summary="提交报销申请")
def api_expense_create(
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    with ctx:
        # 1. 服务层校验预算余额、科目归属并创建单据（状态直接为待导师）
        exp = ExpenseService.create(db, data, current_user)
        # 2. 补充审计描述：报销单号 + 金额，便于操作日志追溯
        ctx.set_desc(f"提交报销申请#{exp.expense_no}，金额{exp.expense_amount}元")
        # 3. 转为列表项返回，与列表页字段保持一致，前端可直接刷新行
        item = ExpenseService.to_list_item(db, exp)
        return success(data=item, message="报销申请已提交")


def _can_user_approve(user: SysUser, status: int, project_meta: Optional[tuple]) -> bool:
    """与审批接口权限保持一致，供列表标记「通过/驳回」按钮是否可用。

    参数：
        user: 当前登录用户。
        status: 报销单当前状态（0~7）。
        project_meta: (teacher_id, college_id)，所属项目的指导教师与学院；
                      项目缺失时传 None，直接视为不可审批。
    返回：True 表示该用户此刻有权处理这张单据；仅用于前端按钮显隐，
          真正权限仍由 /{expense_id}/review 服务端校验。
    """
    if not project_meta:
        return False
    teacher_id, college_id = project_meta
    # 真超管可处理全部非终态单据（0/6/7 为草稿/完成/驳回，无可审批动作）
    if is_super_admin(user):
        return status in (1, 2, 3, 4, 5)
    # 待导师审批(1)：仅该项目指导教师本人，学院管理员不得代审
    if status == EXPENSE_STATUS_PENDING_ADVISOR:
        return user.role == RoleEnum.TEACHER and user.id == teacher_id
    # 导师通过后进入学院环节(2/3/4)：仅项目所属学院的学院管理员
    if status in (EXPENSE_STATUS_ADVISOR_APPROVED,
                  EXPENSE_STATUS_PENDING_COLLEGE,
                  EXPENSE_STATUS_COLLEGE_APPROVED):
        return is_college_admin(user) and user.college_id == college_id
    return False


# 各级审批可处理的状态范围：
# 导师环节覆盖“待导师(1)”和“导师已通过(2)”，后者用于把单据推进到学院环节；
# 学院环节覆盖“待学院(3)”和“学院已通过(4)”，后者用于推进到财务；
# 财务环节仅“待财务(5)”，通过后进入完成(6)。
REVIEWABLE_BY_ADVISOR = (EXPENSE_STATUS_PENDING_ADVISOR, EXPENSE_STATUS_ADVISOR_APPROVED)
REVIEWABLE_BY_COLLEGE = (EXPENSE_STATUS_PENDING_COLLEGE, EXPENSE_STATUS_COLLEGE_APPROVED)
REVIEWABLE_BY_FINANCE = (EXPENSE_STATUS_PENDING_FINANCE,)


# --- 接口说明 ---
# PATCH /api/expenses/{expense_id}/review：审批报销单。
# 谁可以调用：管理员(4) 或教师(2)（路由层 RequireRole）；服务端再按状态分级校验。
# 入参：expense_id；approved=True 通过 / False 驳回；opinion 审批意见。
# 返回：更新后的 ExpenseListItem。
# 异常：单据/项目不存在 → 业务异常；当前状态不可审批 → 参数异常；越权审批 → 403。
# 副作用：通过则推进下一状态；终审完成时回写项目与预算科目 used_amount；
#         驳回为终态并记录原因；写审计日志。
# 并发：服务层对单据加行级锁，重复审批会被串行化并因终态保护而拒绝。
@router_expense.patch("/{expense_id}/review", response_model=ResponseModel[ExpenseListItem], summary="审批报销")
def api_expense_review(
    expense_id: int,
    req: ExpenseReviewRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.ADMIN, RoleEnum.TEACHER)),
    ctx: OperationContext = Depends(),
):
    """按报销状态分级校验审批权限（修复学院管理员越权审批全校经费的Bug）"""
    with ctx:
        # 1. 读取报销单与所属项目：后续权限判断依赖项目指导教师与学院归属
        exp_obj = db.query(ProjExpense).filter(
            ProjExpense.id == expense_id, ProjExpense.is_deleted == 0
        ).first()
        if not exp_obj:
            raise BizException("报销记录不存在")
        project = db.query(ProjProject).filter(ProjProject.id == exp_obj.project_id).first()
        if not project:
            raise BizException("报销关联项目不存在")

        st = exp_obj.status

        # 2. 按当前状态定位审批环节，并校验操作人身份
        if st in REVIEWABLE_BY_ADVISOR:
            if is_super_admin(current_user):
                pass
            elif st == EXPENSE_STATUS_PENDING_ADVISOR:
                # 待导师审批阶段：仅项目指导教师本人；学院管理员禁止代审（保证流程严谨）
                if current_user.id != project.teacher_id:
                    raise PermissionDeniedException(message="待导师审批阶段需由项目指导教师本人审批")
            else:
                # 导师审批通过(状态2)：推进到学院审批，仅项目所属学院的学院管理员可操作
                if not (is_college_admin(current_user)
                        and current_user.college_id == project.college_id):
                    raise PermissionDeniedException(message="仅项目所属学院的学院管理员可推进到学院审批阶段")

        elif st in REVIEWABLE_BY_COLLEGE:
            # 学院级审批：仅项目所属学院的学院管理员 / 超级管理员，普通教师不得审批
            if not is_super_admin(current_user):
                if not (is_college_admin(current_user)
                        and current_user.college_id == project.college_id):
                    raise PermissionDeniedException(message="仅系统管理员或项目所属学院的学院管理员可执行学院级审批")

        elif st in REVIEWABLE_BY_FINANCE:
            # 财务终审：仅真超级管理员，学院管理员禁止
            if not is_super_admin(current_user):
                raise PermissionDeniedException(message="仅系统管理员可执行财务终审")

        else:
            # 草稿(0)/已完成(6)/已驳回(7) 均不可再审批，驳回是终态
            raise ParamValidateException(message="当前报销状态不可审批")

        # 3. 执行状态推进（服务层内部加行级锁并回写终审金额）
        result = ExpenseService.review(db, expense_id, req.approved, req.opinion)
        item = ExpenseService.to_list_item(db, result)
        # 4. 补充审计描述：单据 id + 通过/驳回动作
        ctx.set_desc(f"审批报销#{expense_id}，{'通过' if req.approved else '驳回'}")
        return success(data=item, message="审批完成")
