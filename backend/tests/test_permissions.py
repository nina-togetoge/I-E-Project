"""角色权限分级单元测试（纯逻辑，无需数据库）

验证超级管理员(ADMIN 且 college_id 为空) 与 学院管理员(ADMIN 且 college_id 非空) 的区分，
这是全部越权防护的逻辑基础。
"""
from app.core.security import RoleEnum, is_super_admin, is_college_admin


class _UserStub:
    def __init__(self, role, college_id):
        self.role = role
        self.college_id = college_id


def test_super_admin_requires_admin_without_college():
    assert is_super_admin(_UserStub(RoleEnum.ADMIN, None)) is True
    assert is_super_admin(_UserStub(RoleEnum.ADMIN, 1)) is False
    assert is_super_admin(_UserStub(RoleEnum.TEACHER, None)) is False


def test_college_admin_requires_admin_with_college():
    assert is_college_admin(_UserStub(RoleEnum.ADMIN, 1)) is True
    assert is_college_admin(_UserStub(RoleEnum.ADMIN, None)) is False
    assert is_college_admin(_UserStub(RoleEnum.STUDENT, 1)) is False


def test_none_user_is_not_admin():
    assert is_super_admin(None) is False
    assert is_college_admin(None) is False