"""经费报销三级审批链单元测试（纯逻辑，无需数据库）"""
from app.services.expense_service import _NEXT_STATUS
from app.schemas.project import (
    EXPENSE_STATUS_PENDING_ADVISOR,
    EXPENSE_STATUS_ADVISOR_APPROVED,
    EXPENSE_STATUS_PENDING_COLLEGE,
    EXPENSE_STATUS_COLLEGE_APPROVED,
    EXPENSE_STATUS_PENDING_FINANCE,
    EXPENSE_STATUS_COMPLETED,
    EXPENSE_STATUS_REJECTED,
)


def test_expense_chain_order():
    """审批链顺序：导师 -> 学院 -> 财务"""
    assert _NEXT_STATUS[EXPENSE_STATUS_PENDING_ADVISOR] == EXPENSE_STATUS_ADVISOR_APPROVED
    assert _NEXT_STATUS[EXPENSE_STATUS_ADVISOR_APPROVED] == EXPENSE_STATUS_PENDING_COLLEGE
    assert _NEXT_STATUS[EXPENSE_STATUS_PENDING_COLLEGE] == EXPENSE_STATUS_COLLEGE_APPROVED
    assert _NEXT_STATUS[EXPENSE_STATUS_COLLEGE_APPROVED] == EXPENSE_STATUS_PENDING_FINANCE
    assert _NEXT_STATUS[EXPENSE_STATUS_PENDING_FINANCE] == EXPENSE_STATUS_COMPLETED


def test_expense_chain_reaches_completed():
    """从待导师审批连续推进 5 步应到达已完成(终态)"""
    status = EXPENSE_STATUS_PENDING_ADVISOR
    for _ in range(5):
        status = _NEXT_STATUS[status]
    assert status == EXPENSE_STATUS_COMPLETED


def test_terminal_statuses_have_no_next():
    """已完成/已驳回为终态，不可再推进"""
    assert EXPENSE_STATUS_COMPLETED not in _NEXT_STATUS
    assert EXPENSE_STATUS_REJECTED not in _NEXT_STATUS