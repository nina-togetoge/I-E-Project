"""API 层行为测试（FastAPI TestClient）。

断言针对响应体的业务 ``code``：全局异常处理器把业务/校验异常包装为 HTTP 200 + code。
覆盖：附件下载/预览/列表/上传权限、自助改密旁路、邮箱校验、
     通用审核 expert 阶段旁路修复、审核流程可见性、中期/变更负责人校验、结项-专家验收状态流转。
"""
import os

import pytest

import app.models as M
from app.core.config import settings


# ====================================================================
# 1. 附件下载/预览：无关用户 403，负责人 200
# ====================================================================
def test_attachment_download_and_preview_permission(client, seed, auth_headers, tmp_path):
    college = seed.college()
    leader = seed.user(1, college.id)
    outsider = seed.user(1, college.id)          # 同学院但非成员
    project = seed.project(college.id, leader.id, status=1)

    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 test content")
    att = seed.attachment("project", project.id, uploader_id=leader.id, file_path=str(f))

    # 无关用户：拒绝
    r = client.get(f"/api/files/download/{att.id}", headers=auth_headers(outsider))
    assert r.json()["code"] == 403
    r = client.get(f"/api/files/preview/{att.id}", headers=auth_headers(outsider))
    assert r.json()["code"] == 403

    # 负责人：放行
    r = client.get(f"/api/files/download/{att.id}", headers=auth_headers(leader))
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    r = client.get(f"/api/files/preview/{att.id}", headers=auth_headers(leader))
    assert r.status_code == 200


# ====================================================================
# 3. 附件列表 biz_id=0：只返回本人上传
# ====================================================================
def test_attachment_list_temp_only_own(client, seed, auth_headers, tmp_path):
    college = seed.college()
    ua = seed.user(1, college.id)
    ub = seed.user(1, college.id)
    fa = tmp_path / "a.pdf"; fa.write_bytes(b"a")
    fb = tmp_path / "b.pdf"; fb.write_bytes(b"b")
    own = seed.attachment("project", 0, uploader_id=ua.id, file_path=str(fa), file_name="a.pdf")
    other = seed.attachment("project", 0, uploader_id=ub.id, file_path=str(fb), file_name="b.pdf")

    r = client.get("/api/files/list/project/0", headers=auth_headers(ua))
    body = r.json()
    assert body["code"] == 200
    ids = {it["id"] for it in body["data"]}
    assert own.id in ids
    assert other.id not in ids
    assert len(body["data"]) == 1


# ====================================================================
# 4. 上传到他人项目：403 且磁盘无残留
# ====================================================================
def test_upload_to_others_project_forbidden_no_residue(client, seed, auth_headers):
    college = seed.college()
    owner = seed.user(1, college.id)
    outsider = seed.user(1, college.id)
    project = seed.project(college.id, owner.id, status=1)

    upload_dir = os.path.join(os.getcwd(), settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    before = len(os.listdir(upload_dir))

    r = client.post(
        "/api/files/upload",
        data={"biz_type": "project", "biz_id": str(project.id)},
        files={"file": ("proof.pdf", b"%PDF-1.4 data", "application/pdf")},
        headers=auth_headers(outsider),
    )
    assert r.json()["code"] == 403
    after = len(os.listdir(upload_dir))
    assert after == before

    # 未产生该用户的附件记录
    s = seed.sf()
    try:
        cnt = s.query(M.SysAttachment).filter(M.SysAttachment.uploader_id == outsider.id).count()
    finally:
        s.close()
    assert cnt == 0


# ====================================================================
# 5. PUT /api/users/{自己} 携带 password：403
# ====================================================================
def test_self_update_password_forbidden(client, seed, auth_headers):
    college = seed.college()
    user = seed.user(1, college.id)
    r = client.put(f"/api/users/{user.id}", json={"password": "123456"},
                   headers=auth_headers(user))
    assert r.json()["code"] == 403


# ====================================================================
# 6. 学生自助注册功能已移除：接口不再暴露，应返回 404
# ====================================================================
def test_register_endpoint_removed(client, seed):
    r = client.post("/api/auth/register", json={
        "username": "reg_stu_01", "password": "123456", "real_name": "注册学生",
        "college_id": 1,
    })
    assert r.status_code == 404


def test_profile_update_invalid_email_422(client, seed, auth_headers):
    college = seed.college()
    user = seed.user(1, college.id)
    r = client.patch("/api/users/me/profile", json={"email": "a@b"},
                     headers=auth_headers(user))
    assert r.json()["code"] == 422


# ====================================================================
# 7. POST /api/reviews stage=3（专家）应被拒绝走专家接口，返回 400
# ====================================================================
def test_generic_review_expert_stage_rejected(client, seed, auth_headers):
    college = seed.college()
    leader = seed.user(1, college.id)
    expert = seed.user(3, college.id)
    project = seed.project(college.id, leader.id, status=5)
    seed.assign_expert(project.id, expert.id, stage=3)

    r = client.post("/api/reviews",
                    json={"project_id": project.id, "review_stage": 3, "review_result": 1},
                    headers=auth_headers(expert))
    assert r.json()["code"] == 400
    # 未因旁路直接立项
    assert seed.reload(M.ProjProject, project.id).status == 5


# ====================================================================
# 8. GET /api/reviews/flow/{id}：无关用户 403
# ====================================================================
def test_review_flow_unrelated_forbidden(client, seed, auth_headers):
    college = seed.college()
    leader = seed.user(1, college.id)
    outsider = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=1)

    r = client.get(f"/api/reviews/flow/{project.id}", headers=auth_headers(outsider))
    assert r.json()["code"] == 403

    # 负责人可查看
    r = client.get(f"/api/reviews/flow/{project.id}", headers=auth_headers(leader))
    assert r.json()["code"] == 200


# ====================================================================
# 10. 中期检查 / 变更申请：非负责人提交 403
# ====================================================================
def test_midterm_submit_non_leader_forbidden(client, seed, auth_headers):
    college = seed.college()
    leader = seed.user(1, college.id)
    teacher = seed.user(2, college.id)
    project = seed.project(college.id, leader.id, teacher_id=teacher.id, status=6)

    r = client.post("/api/midterm/submit", json={"project_id": project.id},
                    headers=auth_headers(teacher))
    assert r.json()["code"] == 403


def test_change_create_non_leader_forbidden(client, seed, auth_headers):
    college = seed.college()
    leader = seed.user(1, college.id)
    expert = seed.user(3, college.id)
    project = seed.project(college.id, leader.id, status=6)

    r = client.post("/api/changes",
                    json={"project_id": project.id, "change_type": 1, "change_reason": "工期顺延"},
                    headers=auth_headers(expert))
    assert r.json()["code"] == 403


# ====================================================================
# 11. 结项：提交后状态仍为 8（有占位结题记录）；专家验收通过后转 9
# ====================================================================
def test_submit_final_keeps_status_then_expert_finalizes(client, seed, auth_headers):
    college = seed.college()
    leader = seed.user(1, college.id)
    expert = seed.user(3, college.id)
    project = seed.project(college.id, leader.id, status=8)
    # 结项三条件：中期已批 + 成果≥1 + 报销已结清
    seed.midterm(project.id, status=2)
    seed.achievement(project.id)
    seed.expense(project.id, leader.id, "100.00", status=6)
    seed.assign_expert(project.id, expert.id, stage=3)

    # 提交结项验收报告
    r = client.post(f"/api/projects/{project.id}/submit-final",
                    json={"final_report": "结项验收报告正文"},
                    headers=auth_headers(leader))
    body = r.json()
    assert body["code"] == 200
    assert body["data"]["status"] == 8
    assert seed.reload(M.ProjProject, project.id).status == 8
    # 存在占位结题记录（stage=4, result=99）
    assert seed.count_reviews(project.id, stage=4, result=99) == 1

    # 被分配专家走通用审核接口 stage=4 通过 -> 已结题
    r = client.post("/api/reviews",
                    json={"project_id": project.id, "review_stage": 4, "review_result": 1},
                    headers=auth_headers(expert))
    assert r.json()["code"] == 200
    assert seed.reload(M.ProjProject, project.id).status == 9


# ====================================================================
# 12. 附件删除：非上传者 403；上传者 200 且软删除后不可下载
# ====================================================================
def test_attachment_delete_permission_and_soft_delete(client, seed, auth_headers, tmp_path):
    college = seed.college()
    leader = seed.user(1, college.id)
    outsider = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=0)  # 草稿，可编辑

    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 test content")
    att = seed.attachment("project", project.id, uploader_id=leader.id, file_path=str(f))

    # 非上传者：拒绝
    r = client.delete(f"/api/files/{att.id}", headers=auth_headers(outsider))
    assert r.json()["code"] == 403

    # 上传者：成功
    r = client.delete(f"/api/files/{att.id}", headers=auth_headers(leader))
    body = r.json()
    assert body["code"] == 200
    assert body["data"]["id"] == att.id

    # 软删除后：不可下载/预览
    r = client.get(f"/api/files/download/{att.id}", headers=auth_headers(leader))
    assert r.json()["code"] == 404


# ====================================================================
# 13. 附件删除：项目处于不可编辑状态时被拦截
# ====================================================================
def test_attachment_delete_blocked_when_project_not_editable(client, seed, auth_headers, tmp_path):
    college = seed.college()
    leader = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=1)  # 待学院初审，不可编辑

    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 test content")
    att = seed.attachment("project", project.id, uploader_id=leader.id, file_path=str(f))

    r = client.delete(f"/api/files/{att.id}", headers=auth_headers(leader))
    body = r.json()
    assert body["code"] != 200
    assert "不可删除" in body["message"]
    # 记录未被软删除
    assert seed.reload(M.SysAttachment, att.id).is_deleted == 0