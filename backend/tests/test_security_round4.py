"""第四轮漏洞修复回归测试（FastAPI TestClient）。

断言针对响应体的业务 ``code``（全局异常处理器统一包装为 HTTP 200 + code）。
覆盖：
  - 专家 / 未绑定学院教师 拉取全校用户 PII 的越权（UserService.paginate）
  - 学院管理员越权新增 / 修改学院（CollegeService.create/update）
  - 项目撤回缺少管理员学院归属校验（ProjectService.withdraw）
"""
import pytest

import app.models as M


# ====================================================================
# 严重：专家 / 无学院教师不得拉取全校用户列表（PII）
# ====================================================================
def test_expert_cannot_list_users(client, seed, auth_headers):
    college = seed.college()
    expert = seed.user(3, college.id)
    seed.user(1, college.id)
    seed.user(2, college.id)

    r = client.get("/api/users", headers=auth_headers(expert))
    assert r.json()["code"] == 403


def test_teacher_without_college_cannot_list_users(client, seed, auth_headers):
    teacher = seed.user(2, None)  # 未绑定学院 -> 数据范围为空，必须拒绝
    seed.user(1, None)

    r = client.get("/api/users", headers=auth_headers(teacher))
    assert r.json()["code"] == 403


def test_teacher_with_college_can_list_same_college(client, seed, auth_headers):
    """回归：绑定学院的教师仍可查询用户（数据范围正常，不被过度封锁）。"""
    college = seed.college()
    teacher = seed.user(2, college.id)
    seed.user(1, college.id)

    r = client.get("/api/users", headers=auth_headers(teacher))
    assert r.json()["code"] == 200


# ====================================================================
# 中等：学院管理员不得新增 / 修改学院
# ====================================================================
def test_college_admin_cannot_create_college(client, seed, auth_headers):
    college = seed.college()
    admin = seed.user(4, college.id)

    r = client.post("/api/colleges",
                    json={"college_code": "NEW01", "college_name": "非法新增学院"},
                    headers=auth_headers(admin))
    assert r.json()["code"] == 403


def test_college_admin_cannot_update_college(client, seed, auth_headers):
    college = seed.college(name="本院")
    other_college = seed.college(name="他院")
    admin = seed.user(4, college.id)

    r = client.put(f"/api/colleges/{other_college.id}",
                   json={"college_name": "被篡改"},
                   headers=auth_headers(admin))
    assert r.json()["code"] == 403
    assert seed.reload(M.SysCollege, other_college.id).college_name == "他院"


def test_super_admin_can_update_college(client, seed, auth_headers):
    college = seed.college(name="原名称")
    super_admin = seed.user(4, None)

    r = client.put(f"/api/colleges/{college.id}",
                   json={"college_name": "新名称"},
                   headers=auth_headers(super_admin))
    assert r.json()["code"] == 200
    assert seed.reload(M.SysCollege, college.id).college_name == "新名称"


# ====================================================================
# 轻微：项目撤回的管理员学院归属校验
# ====================================================================
def test_college_admin_cannot_withdraw_other_college(client, seed, auth_headers):
    ca = seed.college(name="A学院")
    cb = seed.college(name="B学院")
    admin = seed.user(4, ca.id)      # A 学院管理员
    leader = seed.user(1, cb.id)
    proj = seed.project(college_id=cb.id, leader_id=leader.id, status=1)  # 待学院初审

    r = client.post(f"/api/projects/{proj.id}/withdraw", headers=auth_headers(admin))
    assert r.json()["code"] == 403
    assert seed.reload(M.ProjProject, proj.id).status == 1


def test_college_admin_can_withdraw_same_college(client, seed, auth_headers):
    ca = seed.college(name="A学院")
    admin = seed.user(4, ca.id)
    leader = seed.user(1, ca.id)
    # 仅「待指导教师确认」(12) 阶段可撤回
    proj = seed.project(college_id=ca.id, leader_id=leader.id, status=12)

    r = client.post(f"/api/projects/{proj.id}/withdraw", headers=auth_headers(admin))
    assert r.json()["code"] == 200
    assert seed.reload(M.ProjProject, proj.id).status == 0


def test_student_cannot_withdraw_others_project(client, seed, auth_headers):
    college = seed.college()
    leader = seed.user(1, college.id)
    other_student = seed.user(1, college.id)
    proj = seed.project(college_id=college.id, leader_id=leader.id, status=1)

    r = client.post(f"/api/projects/{proj.id}/withdraw", headers=auth_headers(other_student))
    assert r.json()["code"] == 403