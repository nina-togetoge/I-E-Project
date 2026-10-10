"""服务层行为测试（真实 ORM + 临时 SQLite，覆盖上一轮修复的核心业务规则）。

覆盖：
- ReviewService.do_expert_review：多数评审须等待全部已分配专家完成后才判定；
  多数通过(含平票) → 已立项(6)，多数驳回 → 已驳回(10)。
- ExpenseService.create：非负责人提交 403；超剩余预算 400；attachment_ids 仅绑定本人上传的临时附件。
"""
from decimal import Decimal

import pytest

import app.models as M
from app.core.exceptions import BizException, PermissionDeniedException
from app.schemas.review import ExpertReviewCreateRequest
from app.schemas.project import ExpenseCreate, EXPENSE_STATUS_PENDING_ADVISOR
from app.services.review_service import ReviewService
from app.services.expense_service import ExpenseService


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
    ReviewService.do_expert_review(db, _expert_req(project.id, 90, 1, "通过"), e1)
    assert seed.reload(M.ProjProject, project.id).status == 5

    # 全部完成且全部通过 -> 已立项(6)
    ReviewService.do_expert_review(db, _expert_req(project.id, 80, 1, "通过"), e2)
    assert seed.reload(M.ProjProject, project.id).status == 6


def test_expert_review_majority_reject_flow(seed, db):
    """3 位专家中多数驳回（2 驳回 1 通过）-> 已驳回(10)，不得卡死在待专家评审。"""
    college = seed.college()
    leader = seed.user(1, college.id)
    experts = [seed.user(3, college.id) for _ in range(3)]
    project = seed.project(college.id, leader.id, status=5)
    for e in experts:
        seed.assign_expert(project.id, e.id, stage=3)

    ReviewService.do_expert_review(db, _expert_req(project.id, 95, 1, "通过"), experts[0])
    ReviewService.do_expert_review(db, _expert_req(project.id, 40, 2, "驳回"), experts[1])
    assert seed.reload(M.ProjProject, project.id).status == 5  # 仍有专家未评
    ReviewService.do_expert_review(db, _expert_req(project.id, 30, 2, "驳回"), experts[2])

    proj = seed.reload(M.ProjProject, project.id)
    assert proj.status == 10
    assert "多数专家驳回" in (proj.reject_reason or "")


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