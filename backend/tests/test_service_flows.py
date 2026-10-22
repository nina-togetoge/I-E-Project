"""服务层行为测试（真实 ORM + 临时 SQLite，覆盖上一轮修复的核心业务规则）。

覆盖：
- ReviewService.do_expert_review：多数评审须等待全部已分配专家完成后才判定；
  多数通过(含平票) → 已立项(6)，多数驳回 → 已驳回(10)。
- ExpenseService.create：非负责人提交 403；超剩余预算 400；attachment_ids 仅绑定本人上传的临时附件。
"""
from datetime import datetime
from decimal import Decimal

import pytest

import app.models as M
from app.core.exceptions import BizException, PermissionDeniedException, ParamValidateException
from app.schemas.review import (
    ExpertReviewCreateRequest, ReviewCreateRequest,
    REVIEW_STAGE_TEACHER, REVIEW_STAGE_COLLEGE, REVIEW_STAGE_FINAL,
    REVIEW_RESULT_PASS, REVIEW_RESULT_REJECT,
)
from app.schemas.project import ExpenseCreate, EXPENSE_STATUS_PENDING_ADVISOR, ProjectUpdate
from app.services.project_service import ProjectService
from app.services.review_service import ReviewService
from app.services.expense_service import ExpenseService
from app.services.user_service import UserService


def _expert_req(project_id, score, result, comment=None):
    return ExpertReviewCreateRequest(
        project_id=project_id, score=Decimal(str(score)),
        review_result=result, review_comment=comment,
    )


# ====================================================================
# 9. 专家评审状态流转
# ====================================================================
def test_expert_review_waits_for_all_assigned(seed, db):
    """首位专家通过不得立即立项，其余已分配专家仍可提交打分。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    e1 = seed.user(3, college.id)
    e2 = seed.user(3, college.id)
    project = seed.project(college.id, leader.id, status=5)
    seed.assign_expert(project.id, e1.id, stage=3)
    seed.assign_expert(project.id, e2.id, stage=3)

    # 第一位专家通过：项目仍在待专家评审(5)
    # 判定通过需满足：评分≥及格线 且 意见不少于10字
    ReviewService.do_expert_review(db, _expert_req(project.id, 90, 1, "项目方案完整，同意通过"), e1)
    assert seed.reload(M.ProjProject, project.id).status == 5

    # 全部完成且全部通过（均分85≥及格线）-> 已立项(6)
    ReviewService.do_expert_review(db, _expert_req(project.id, 80, 1, "技术路线可行，同意通过"), e2)
    assert seed.reload(M.ProjProject, project.id).status == 6


def test_expert_review_majority_reject_flow(seed, db):
    """3 位专家中多数驳回（2 驳回 1 通过）-> 已驳回(10)，不得卡死在待专家评审。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    experts = [seed.user(3, college.id) for _ in range(3)]
    project = seed.project(college.id, leader.id, status=5)
    for e in experts:
        seed.assign_expert(project.id, e.id, stage=3)

    ReviewService.do_expert_review(db, _expert_req(project.id, 95, 1, "项目创新性较强，同意通过"), experts[0])
    ReviewService.do_expert_review(db, _expert_req(project.id, 40, 2, "驳回"), experts[1])
    assert seed.reload(M.ProjProject, project.id).status == 5  # 仍有专家未评
    ReviewService.do_expert_review(db, _expert_req(project.id, 30, 2, "驳回"), experts[2])

    proj = seed.reload(M.ProjProject, project.id)
    assert proj.status == 10
    assert "未过半数" in (proj.reject_reason or "")


# ====================================================================
# 10. 结题验收：驳回不得打死项目 / 非流程态不得被回退
# ====================================================================
def _final_ready_project(seed):
    """造一个具备结项条件、已提交结项报告、且处于待结题(8)的项目"""
    college = seed.college()
    leader = seed.user(1, college.id)
    expert = seed.user(3, college.id)
    project = seed.project(college.id, leader.id, status=8)
    seed.midterm(project.id, status=2)          # 中期检查已通过
    seed.achievement(project.id)                 # 至少 1 项成果
    seed.assign_expert(project.id, expert.id, stage=3)  # 专家评审阶段被分配
    seed.assign_expert(project.id, leader.id, stage=4)  # 结项报告占位(review_result=99)
    return project, expert


def test_final_reject_keeps_project_resubmittable(seed, db):
    """结题验收驳回应退回「待结题(8)」而非驳回(10)，否则项目永久无法再次结项。"""
    project, expert = _final_ready_project(seed)
    req = ReviewCreateRequest(
        project_id=project.id, review_stage=REVIEW_STAGE_FINAL,
        review_result=REVIEW_RESULT_REJECT, review_comment="验收材料不完整，请补充后重新提交",
    )
    ReviewService.do_review(db, req, expert)

    proj = seed.reload(M.ProjProject, project.id)
    assert proj.status == 8
    assert "验收材料不完整" in (proj.reject_reason or "")


def test_non_flow_status_cannot_be_reviewed(seed, db):
    """已立项(6)等非流程态不属于任何审核阶段，不得被回退为待学院初审(1)。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    teacher = seed.user(2, college.id)
    project = seed.project(college.id, leader.id, teacher_id=teacher.id, status=6)

    with pytest.raises(BizException):
        ReviewService.do_review(db, ReviewCreateRequest(
            project_id=project.id, review_stage=REVIEW_STAGE_TEACHER,
            review_result=REVIEW_RESULT_PASS, review_comment="同意",
        ), teacher)
    assert seed.reload(M.ProjProject, project.id).status == 6


# ====================================================================
# 11. 驳回后的可重提性
#     仅「指导教师驳回(阶段0)」可修改后重提；学院及之后驳回即「落选」（终局）
# ====================================================================
def test_teacher_reject_allows_resubmit(seed, db):
    """指导教师驳回为软门槛：学生可修改并重新提交（不被判为「落选」）。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    teacher = seed.user(2, college.id)
    project = seed.project(college.id, leader.id, teacher_id=teacher.id, status=12)
    seed.assign_expert(project.id, teacher.id, stage=0)  # 指导教师确认占位记录

    ReviewService.do_review(db, ReviewCreateRequest(
        project_id=project.id, review_stage=REVIEW_STAGE_TEACHER,
        review_result=REVIEW_RESULT_REJECT, review_comment="选题不聚焦，请修改后重新提交",
    ), teacher)
    proj = seed.reload(M.ProjProject, project.id)
    assert proj.status == 10
    # 未落选 → 可修改重提
    assert ProjectService.get_detail(db, project.id, leader).resubmittable is True

    # 编辑不被拦截
    ProjectService.update(db, project.id, ProjectUpdate(project_name="修改后的项目名称"), leader)

    # 提交越过「落选」权限拦截，进到必填校验（缺团队成员/预算 → 400 参数错误，而非 403 权限拒绝）
    with pytest.raises(ParamValidateException) as ei:
        ProjectService.submit(db, project.id, leader)
    assert ei.value.code == 400


def test_college_reject_is_eliminated(seed, db):
    """学院初审驳回即终局「落选」：不可再编辑、不可重新提交。"""
    college = seed.college()
    admin = seed.user(4, college.id)  # 学院管理员（绑定 college_id）
    leader = seed.user(1, college.id)
    teacher = seed.user(2, college.id)
    project = seed.project(college.id, leader.id, teacher_id=teacher.id, status=1)

    ReviewService.do_review(db, ReviewCreateRequest(
        project_id=project.id, review_stage=REVIEW_STAGE_COLLEGE,
        review_result=REVIEW_RESULT_REJECT, review_comment="不符合本年度申报要求",
    ), admin)
    proj = seed.reload(M.ProjProject, project.id)
    assert proj.status == 10
    assert ProjectService.get_detail(db, project.id, leader).resubmittable is False

    with pytest.raises(PermissionDeniedException):
        ProjectService.update(db, project.id, ProjectUpdate(project_name="试图修改"), leader)
    with pytest.raises(PermissionDeniedException):
        ProjectService.submit(db, project.id, leader)


# ====================================================================
# 12. 报销创建：权限 / 预算 / 附件绑定
# ====================================================================
def test_expense_create_non_leader_forbidden(seed, db):
    college = seed.college()
    leader = seed.user(1, college.id)
    other = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=6, budget="1000.00")

    data = ExpenseCreate(project_id=project.id, expense_amount=Decimal("100.00"), expense_desc="材料费")
    with pytest.raises(PermissionDeniedException) as ei:
        ExpenseService.create(db, data, other)
    assert ei.value.code == 403


def test_expense_create_over_budget_rejected(seed, db):
    college = seed.college()
    leader = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=6, budget="1000.00")
    # 已提交报销 800（占用额度，非驳回状态）
    seed.expense(project.id, leader.id, "800.00", status=EXPENSE_STATUS_PENDING_ADVISOR)

    over = ExpenseCreate(project_id=project.id, expense_amount=Decimal("300.00"), expense_desc="超预算")
    with pytest.raises(BizException) as ei:
        ExpenseService.create(db, over, leader)
    assert ei.value.code == 400

    # 边界：恰好等于剩余预算 200 -> 通过
    ok = ExpenseCreate(project_id=project.id, expense_amount=Decimal("200.00"), expense_desc="恰好剩余预算")
    exp = ExpenseService.create(db, ok, leader)
    assert exp.id is not None
    assert exp.status == EXPENSE_STATUS_PENDING_ADVISOR


def test_expense_create_binds_only_own_temp_attachments(seed, db):
    college = seed.college()
    leader = seed.user(1, college.id)
    other = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=6, budget="1000.00")

    own = seed.attachment("expense", 0, uploader_id=leader.id, file_name="own.pdf")
    foreign = seed.attachment("expense", 0, uploader_id=other.id, file_name="foreign.pdf")

    data = ExpenseCreate(
        project_id=project.id, expense_amount=Decimal("50.00"), expense_desc="报销",
        attachment_ids=[own.id, foreign.id],
    )
    exp = ExpenseService.create(db, data, leader)

    assert seed.reload(M.SysAttachment, own.id).biz_id == exp.id
    assert seed.reload(M.SysAttachment, foreign.id).biz_id == 0  # 他人附件不被绑定


# ====================================================================
# 13. 数据边界（P1）：专家可见性回收 / 评审独立性 / 跨院指导教师 / 未绑定学院用户
# ====================================================================
def test_expert_visibility_revoked_after_assignment_removed(seed, db):
    """专家分配记录被软删后，不得再凭该记录查看项目详情。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    expert = seed.user(3, college.id)
    project = seed.project(college.id, leader.id, status=5)
    rec = seed.assign_expert(project.id, expert.id, stage=3)

    ProjectService.get_detail(db, project.id, expert)  # 分配有效时可查看

    assignment = db.get(M.ProjReview, rec.id)
    assignment.is_deleted = 1
    db.commit()

    with pytest.raises(PermissionDeniedException) as ei:
        ProjectService.get_detail(db, project.id, expert)
    assert ei.value.code == 403


def test_review_flow_hides_other_experts_from_expert(seed, db):
    """专家查看审核流程时只能看到本人的专家记录，管理员仍可见全量。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    e1 = seed.user(3, college.id)
    e2 = seed.user(3, college.id)
    admin = seed.user(4)  # 真超级管理员（未绑定学院）
    project = seed.project(college.id, leader.id, status=5)
    seed.assign_expert(project.id, e1.id, stage=3)
    seed.assign_expert(project.id, e2.id, stage=3)

    ReviewService.do_expert_review(db, _expert_req(project.id, 90, 1, "方案完整，同意通过立项"), e1)
    ReviewService.do_expert_review(db, _expert_req(project.id, 70, 1, "技术可行，同意通过立项"), e2)
    assert seed.reload(M.ProjProject, project.id).status == 6

    mine = ReviewService.get_review_flow(db, project.id, e1)
    assert [r.reviewer_id for r in mine.records if r.review_stage == 3] == [e1.id]

    full = ReviewService.get_review_flow(db, project.id, admin)
    assert len([r for r in full.records if r.review_stage == 3]) == 2


def test_update_rejects_foreign_college_teacher(seed, db):
    """指导教师须属于项目所在学院：他院教师被拒，本院教师通过（超管不受限）。"""
    c1 = seed.college()
    c2 = seed.college()
    admin1 = seed.user(4, c1.id)  # 学院管理员
    leader = seed.user(1, c1.id)
    teacher1 = seed.user(2, c1.id)
    teacher2 = seed.user(2, c2.id)
    project = seed.project(c1.id, leader.id, status=10)  # 已驳回，学院管理员可编辑

    with pytest.raises(BizException) as ei:
        ProjectService.update(db, project.id, ProjectUpdate(teacher_id=teacher2.id), admin1)
    assert ei.value.code == 400
    assert seed.reload(M.ProjProject, project.id).teacher_id is None

    ProjectService.update(db, project.id, ProjectUpdate(teacher_id=teacher1.id), admin1)
    assert seed.reload(M.ProjProject, project.id).teacher_id == teacher1.id


def test_college_admin_cannot_reach_unassigned_user(seed, db):
    """未绑定学院的用户不归任何学院管理员管辖：不可改状态、不可删除。"""
    c1 = seed.college()
    admin1 = seed.user(4, c1.id)
    orphan = seed.user(1, None)
    mine = seed.user(1, c1.id)

    with pytest.raises(PermissionDeniedException):
        UserService.batch_update_status(db, [orphan.id], 0, admin1)
    with pytest.raises(PermissionDeniedException):
        UserService.delete(db, orphan.id, admin1)

    assert UserService.batch_update_status(db, [mine.id], 0, admin1) == 1


# ====================================================================
# 14. 并发/数据完整性（P2）：预算就地更新 / 科目额度 / 级联删除 / 撤回清字段 / 编号冲突
# ====================================================================
def test_project_update_preserves_budget_used_amount(seed, db):
    """[P2-⑤] 修改项目预算时同名科目就地更新：已使用金额与行 id 不得被重置。"""
    from app.schemas.project import BudgetItemCreate
    college = seed.college()
    leader = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=10, budget="1000.00")
    b = seed.budget(project.id, item="设备费", amount="1000.00", used="300.00")

    ProjectService.update(db, project.id, ProjectUpdate(
        budgets=[BudgetItemCreate(budget_item="设备费", budget_amount=Decimal("1200.00"))]
    ), leader)

    after = seed.reload(M.ProjBudget, b.id)
    assert after is not None                        # 行未被删除重建
    assert after.used_amount == Decimal("300.00")   # 已使用金额保留
    assert after.budget_amount == Decimal("1200.00")
    assert seed.reload(M.ProjProject, project.id).budget_amount == Decimal("1200.00")


def test_expense_create_subject_quota_rejected(seed, db):
    """[P2-④] 指定预算科目时，单项报销不得超过该科目额度（即便项目总额充足）。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=6, budget="10000.00")
    b1 = seed.budget(project.id, item="设备费", amount="500.00")
    b2 = seed.budget(project.id, item="材料费", amount="9500.00")

    over = ExpenseCreate(project_id=project.id, expense_amount=Decimal("600.00"),
                         expense_desc="设备费超科目额度", budget_item_id=b1.id)
    with pytest.raises(BizException) as ei:
        ExpenseService.create(db, over, leader)
    assert ei.value.code == 400

    ok = ExpenseCreate(project_id=project.id, expense_amount=Decimal("600.00"),
                       expense_desc="材料费报销", budget_item_id=b2.id)
    assert ExpenseService.create(db, ok, leader).id is not None


def test_project_delete_cascades_children(seed, db):
    """[P2-⑧] 删除项目时级联软删除子表，避免报销/成果/预算在列表与统计中残留。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    admin = seed.user(4)  # 真超级管理员
    project = seed.project(college.id, leader.id, status=6, budget="1000.00")
    exp = seed.expense(project.id, leader.id, "100.00", status=6)
    ach = seed.achievement(project.id)
    bud = seed.budget(project.id, item="设备费", amount="1000.00")
    rev = seed.assign_expert(project.id, seed.user(3, college.id).id, stage=3)
    mid = seed.midterm(project.id)
    chg = seed.change(project.id, leader.id)

    ProjectService.delete(db, project.id, admin)

    assert seed.reload(M.ProjProject, project.id).is_deleted == 1
    for model, pk in ((M.ProjExpense, exp.id), (M.ProjAchievement, ach.id),
                      (M.ProjBudget, bud.id), (M.ProjReview, rev.id),
                      (M.ProjMidtermCheck, mid.id), (M.ProjChangeRequest, chg.id)):
        assert seed.reload(model, pk).is_deleted == 1


def test_withdraw_clears_reject_fields(seed, db):
    """[P3] 撤回退回草稿时清空驳回原因与当前审批人，避免旧字段残留。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    # 仅「待指导教师确认」(12) 阶段可撤回
    project = seed.project(college.id, leader.id, status=12)
    p = db.get(M.ProjProject, project.id)
    p.reject_reason = "上一轮驳回原因"
    p.current_approver_id = 999
    db.commit()

    ProjectService.withdraw(db, project.id, leader)
    after = seed.reload(M.ProjProject, project.id)
    assert after.status == 0
    assert after.reject_reason is None
    assert after.current_approver_id is None


def test_project_no_bump_on_collision():
    """[P2-③] 项目编号唯一键冲突后可按序递增重试。"""
    from app.crud.project import ProjectCRUD
    assert ProjectCRUD.bump_project_no("IE2025000007") == "IE2025000008"
    assert ProjectCRUD.bump_project_no("IE2025000007", step=3) == "IE2025000010"


def test_sync_current_approver_mapping(seed, db):
    """[P3] "当前审批人"随阶段同步：待指导教师确认→指导教师；待学院初审→学院管理员；其余→空。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    teacher = seed.user(2, college.id)
    college_admin = seed.user(4, college.id)  # 学院管理员(绑定学院)
    p = seed.project(college.id, leader.id, teacher_id=teacher.id, status=12)

    ProjectService._sync_current_approver(db, p)
    assert p.current_approver_id == teacher.id

    p.status = 1
    ProjectService._sync_current_approver(db, p)
    assert p.current_approver_id == college_admin.id

    p.status = 5
    ProjectService._sync_current_approver(db, p)
    assert p.current_approver_id is None


def test_midterm_submit_rejects_status_8(seed, db):
    """[P3] 待结题(8)阶段不再允许提交中期检查（与前端按钮可见范围 6/7 对齐）。"""
    from app.core.exceptions import ParamValidateException
    from app.schemas.review import MidtermCheckCreate
    from app.services.review_service import MidtermService

    college = seed.college()
    leader = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=8)
    with pytest.raises(ParamValidateException):
        MidtermService.submit(db, MidtermCheckCreate(project_id=project.id), leader, False)


def test_college_admin_attachment_scope(seed, db):
    """[横切] 附件访问：学院管理员仅限本院业务文件，真超级管理员可访问全部。"""
    from app.api.routers.common_router import _ensure_biz_access

    c1, c2 = seed.college(), seed.college()
    leader = seed.user(1, c1.id)
    ca1 = seed.user(4, c1.id)   # 学院管理员（本院）
    super_admin = seed.user(4)  # 真超级管理员（无学院归属）
    p1 = seed.project(c1.id, leader.id, status=6)
    p2 = seed.project(c2.id, leader.id, status=6)
    a1 = seed.attachment("project", p1.id, leader.id)
    a2 = seed.attachment("project", p2.id, leader.id)

    # 学院管理员：本院放行
    _ensure_biz_access(db, "project", p1.id, ca1, allow_uploader_id=a1.uploader_id)
    # 学院管理员：他院拒绝
    with pytest.raises(PermissionDeniedException):
        _ensure_biz_access(db, "project", p2.id, ca1, allow_uploader_id=a2.uploader_id)
    # 真超级管理员：全校放行
    _ensure_biz_access(db, "project", p2.id, super_admin, allow_uploader_id=a2.uploader_id)


def test_operation_log_college_scope(seed, db):
    """[横切] 操作日志数据范围：学院管理员仅见本院用户日志，真超级管理员见全部。"""
    from app.core.deps import PaginationParams
    from app.schemas.user import OperationLogQueryParams
    from app.services.user_service import OperationLogService

    c1, c2 = seed.college(), seed.college()
    u1 = seed.user(1, c1.id)
    u2 = seed.user(1, c2.id)
    ca1 = seed.user(4, c1.id)
    super_admin = seed.user(4)
    for u, desc in ((u1, "c1操作"), (u2, "c2操作")):
        db.add(M.SysOperationLog(
            user_id=u.id, username=u.username, real_name=u.real_name, user_role=u.role,
            operation_type="query", module_name="test", operation_desc=desc,
            request_method="GET", request_url="/api/test", operation_time=datetime.now(),
        ))
    db.commit()

    pager = PaginationParams()
    ca_items, _ = OperationLogService.paginate(db, pager, OperationLogQueryParams(), ca1)
    assert {i.operation_desc for i in ca_items} == {"c1操作"}

    all_items, _ = OperationLogService.paginate(db, pager, OperationLogQueryParams(), super_admin)
    assert {"c1操作", "c2操作"}.issubset({i.operation_desc for i in all_items})