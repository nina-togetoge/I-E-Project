"""P2 功能测试：成果认定、站内通知、结项归档导出。"""
import io
import zipfile

import app.models as M


# ====================================================================
# 成果认定
# ====================================================================
def _project_with_achievement(seed, status=7):
    college = seed.college()
    leader = seed.user(1, college.id)
    teacher = seed.user(2, college.id)
    project = seed.project(college.id, leader.id, teacher_id=teacher.id, status=status)
    ach = seed.achievement(project.id)
    return college, leader, teacher, project, ach


def test_teacher_review_achievement_pass_and_notify(client, seed, auth_headers, db):
    _, leader, teacher, project, ach = _project_with_achievement(seed)

    r = client.post(f"/api/achievements/{ach.id}/review",
                    json={"result": 1}, headers=auth_headers(teacher))
    body = r.json()
    assert body["code"] == 200
    assert body["data"]["review_status"] == 1
    assert body["data"]["review_status_name"] == "已认定"

    # 负责人收到认定通知
    notices = db.query(M.SysNotification).filter(
        M.SysNotification.user_id == leader.id,
        M.SysNotification.biz_type == "achievement",
    ).all()
    assert len(notices) == 1
    assert notices[0].level == 3
    assert notices[0].link == f"/projects/{project.id}/achievements"


def test_reject_requires_comment(client, seed, auth_headers):
    _, _, teacher, _, ach = _project_with_achievement(seed)

    r = client.post(f"/api/achievements/{ach.id}/review",
                    json={"result": 2}, headers=auth_headers(teacher))
    assert r.json()["code"] == 400

    r = client.post(f"/api/achievements/{ach.id}/review",
                    json={"result": 2, "comment": "材料不足"}, headers=auth_headers(teacher))
    body = r.json()
    assert body["code"] == 200
    assert body["data"]["review_status"] == 2
    assert body["data"]["review_comment"] == "材料不足"


def test_leader_cannot_review_own_achievement(client, seed, auth_headers):
    _, leader, _, _, ach = _project_with_achievement(seed)

    r = client.post(f"/api/achievements/{ach.id}/review",
                    json={"result": 1}, headers=auth_headers(leader))
    assert r.json()["code"] == 403


def test_edit_after_review_resets_to_pending(client, seed, auth_headers):
    _, leader, teacher, _, ach = _project_with_achievement(seed)
    client.post(f"/api/achievements/{ach.id}/review",
                json={"result": 1}, headers=auth_headers(teacher))

    r = client.put(f"/api/achievements/{ach.id}",
                   json={"title": "修改后的成果"}, headers=auth_headers(leader))
    body = r.json()
    assert body["code"] == 200
    assert body["data"]["review_status"] == 0
    assert body["data"]["review_status_name"] == "待认定"


# ====================================================================
# 站内通知
# ====================================================================
def test_notification_list_and_mark_read(client, seed, auth_headers, db):
    college = seed.college()
    user = seed.user(1, college.id)
    s = seed.sf()
    try:
        s.add(M.SysNotification(user_id=user.id, title="测试通知", content="正文", level=1))
        s.commit()
    finally:
        s.close()

    r = client.get("/api/notifications", headers=auth_headers(user))
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["title"] == "测试通知"

    r = client.get("/api/notifications/unread-count", headers=auth_headers(user))
    assert r.json()["data"]["count"] == 1

    r = client.post(f"/api/notifications/{data['items'][0]['id']}/read",
                    headers=auth_headers(user))
    assert r.json()["code"] == 200

    r = client.get("/api/notifications/unread-count", headers=auth_headers(user))
    assert r.json()["data"]["count"] == 0


# ====================================================================
# 结项归档导出
# ====================================================================
def test_archive_export_finished_project(client, seed, auth_headers, tmp_path):
    college = seed.college()
    leader = seed.user(1, college.id)
    teacher = seed.user(2, college.id)
    project = seed.project(college.id, leader.id, teacher_id=teacher.id, status=9)
    ach = seed.achievement(project.id, title="归档成果")
    seed.budget(project.id)

    # 真实存在的附件应被打包
    f = tmp_path / "证明.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    seed.attachment("achievement", ach.id, leader.id, file_path=str(f), file_name="证明.pdf")

    r = client.get(f"/api/projects/{project.id}/archive", headers=auth_headers(leader))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert "项目归档信息.xlsx" in names
        assert any(n.startswith("附件/") for n in names)
        assert any(n.endswith("证明.pdf") for n in names)


def test_archive_export_rejected_for_unfinished_project(client, seed, auth_headers):
    college = seed.college()
    leader = seed.user(1, college.id)
    project = seed.project(college.id, leader.id, status=7)

    r = client.get(f"/api/projects/{project.id}/archive", headers=auth_headers(leader))
    assert r.json()["code"] == 400
