"""审核流程状态机单元测试（纯逻辑，无需数据库）

覆盖：指导教师确认 -> 学院初审 -> 校级复审 -> 专家评审 -> 立项 / 结题验收 的状态流转，
并验证学院初审通过后不会停留在瞬时中间态(2)。
"""
from app.services.review_service import ReviewService
from app.schemas.review import (
    REVIEW_STAGE_TEACHER, REVIEW_STAGE_COLLEGE, REVIEW_STAGE_UNIVERSITY,
    REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL,
)


def test_next_status_after_pass_mapping():
    """各审核阶段通过后应流转到正确的目标状态"""
    assert ReviewService._next_status_after_pass(12, REVIEW_STAGE_TEACHER) == 1
    assert ReviewService._next_status_after_pass(1, REVIEW_STAGE_COLLEGE) == 3
    assert ReviewService._next_status_after_pass(3, REVIEW_STAGE_UNIVERSITY) == 5
    assert ReviewService._next_status_after_pass(5, REVIEW_STAGE_EXPERT) == 6
    assert ReviewService._next_status_after_pass(8, REVIEW_STAGE_FINAL) == 9


def test_college_review_skips_transient_status():
    """学院初审通过不得停留在瞬态 2(学院初审通过)，必须直接进入 3(待校级复审)"""
    assert ReviewService._next_status_after_pass(1, REVIEW_STAGE_COLLEGE) == 3


def test_get_stage_from_status():
    """项目状态应能反推出所处审核阶段"""
    assert ReviewService._get_stage_from_status(12) == REVIEW_STAGE_TEACHER
    assert ReviewService._get_stage_from_status(1) == REVIEW_STAGE_COLLEGE
    assert ReviewService._get_stage_from_status(3) == REVIEW_STAGE_UNIVERSITY
    assert ReviewService._get_stage_from_status(5) == REVIEW_STAGE_EXPERT
    assert ReviewService._get_stage_from_status(8) == REVIEW_STAGE_FINAL


def test_non_flow_status_has_no_stage():
    """驳回(10)/撤销(11)等非流程态不应落入任何审核阶段"""
    assert ReviewService._get_stage_from_status(10) == 0
    assert ReviewService._get_stage_from_status(11) == 0