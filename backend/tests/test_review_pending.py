"""审核待办列表 + 各阶段审核权限 的 API 级回归测试。

覆盖：
1. 专家待办列表只返回"仍需专家操作"的项目(待专家评审5 / 待结题8)，
   不再混入已立项(6)/中期(7)/已结题(9) 等已决项目（否则会出现"有行但无按钮"）；
2. 教师待办列表只含自己指导的"待指导教师确认"项目，不含任何学院初审项目；
3. 学院初审仅限本院学院管理员（或超级管理员）：
   - 本院学院管理员 → 通过并流转到 3(待校级复审)；
   - 指导教师（即使同学院）→ 403；
   - 外院学院管理员 → 403。
"""
import app.models as M


def _items(resp):
    body = resp.json()
    assert body["code"] == 200, body
    return body["data"]["items"]


def test_expert_pending_only_actionable(client, seed, auth_headers):
    """专家待办列表只含待专家评审(5)/待结题(8)，排除已决项目"""
    college = seed.college()
    leader = seed.user(1, college.id)
    expert = seed.user(3, college.id)

    p_review = seed.project(college.id, leader.id, status=5, name="待专家评审项目")
    p_final = seed.project(college.id, leader.id, status=8, name="待结题验收项目")
    p_done6 = seed.project(college.id, leader.id, status=6, name="已立项目")
    p_done7 = seed.project(college.id, leader.id, status=7, name="中期项目")
    p_done9 = seed.project(college.id, leader.id, status=9, name="已结题项目")

    for p in (p_review, p_final, p_done6, p_done7, p_done9):
        seed.assign_expert(p.id, expert.id)

    ids = {it["project_id"] for it in _items(
        client.get("/api/reviews/expert-tasks", headers=auth_headers(expert)))}
    assert p_review.id in ids
    assert p_final.id in ids
    assert p_done6.id not in ids
    assert p_done7.id not in ids
    assert p_done9.id not in ids


def test_teacher_pending_only_own_teacher_confirm(client, seed, auth_headers):
    """教师待办只含自己指导的"待指导教师确认"项目；不含任何学院初审项目"""
    college_a = seed.college("学院A")
    college_b = seed.college("学院B")
    teacher = seed.user(2, college_a.id)
    leader_a = seed.user(1, college_a.id)
    leader_b = seed.user(1, college_b.id)

    mine_confirm = seed.project(college_a.id, leader_a.id, teacher_id=teacher.id,
                                status=12, name="待我确认")
    my_college = seed.project(college_a.id, leader_a.id, status=1, name="本院待学院初审")
    other_college = seed.project(college_b.id, leader_b.id, status=1, name="外院待学院初审")

    ids = {it["id"] for it in _items(
        client.get("/api/reviews", headers=auth_headers(teacher)))}
    assert mine_confirm.id in ids
    assert my_college.id not in ids
    assert other_college.id not in ids


def test_college_admin_can_do_college_review(client, seed, auth_headers):
    """本院学院管理员执行学院初审：应通过并流转到 3(待校级复审)"""
    college = seed.college()
    admin = seed.user(4, college.id)
    leader = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=1)

    r = client.post("/api/reviews", headers=auth_headers(admin), json={
        "project_id": project.id, "review_stage": 1, "review_result": 1,
        "review_comment": "同意，进入校级复审",
    })
    assert r.json()["code"] == 200, r.json()
    assert seed.reload(M.ProjProject, project.id).status == 3


def test_teacher_cannot_do_college_review(client, seed, auth_headers):
    """指导教师（即使与项目同学院）不得执行学院初审"""
    college = seed.college()
    teacher = seed.user(2, college.id)
    leader = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=1)

    r = client.post("/api/reviews", headers=auth_headers(teacher), json={
        "project_id": project.id, "review_stage": 1, "review_result": 1,
        "review_comment": "越权尝试",
    })
    assert r.json()["code"] == 403


def test_other_college_admin_cannot_do_college_review(client, seed, auth_headers):
    """外院学院管理员不得执行本院项目的学院初审"""
    college_a = seed.college("学院A")
    college_b = seed.college("学院B")
    admin_b = seed.user(4, college_b.id)
    leader = seed.user(1, college_a.id)
    project = seed.project(college_a.id, leader.id, status=1)

    r = client.post("/api/reviews", headers=auth_headers(admin_b), json={
        "project_id": project.id, "review_stage": 1, "review_result": 1,
        "review_comment": "越权尝试",
    })
    assert r.json()["code"] == 403