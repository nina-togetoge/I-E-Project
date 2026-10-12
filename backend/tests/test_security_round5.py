"""第 5 轮修复回归测试：Refresh Token 轮换吊销。

覆盖点：
- 刷新成功后，旧 Refresh Token 立即加入黑名单，二次使用应被拒绝（防重放）。
- conftest 默认把 TokenBlacklist.is_blacklisted 打桩为恒 False，本用例改用真实内存黑名单。
"""
import pytest

from app.utils.redis_cache import TokenBlacklist


@pytest.fixture()
def _memory_blacklist(monkeypatch):
    """用真实的内存集合替代 Redis 黑名单，使 add/is_blacklisted 形成闭环。"""
    store = set()

    def _add(cls, token_type, jti, ttl_seconds):
        if jti:
            store.add(f"{token_type}:{jti}")

    def _is_blacklisted(cls, token_type, jti):
        return f"{token_type}:{jti}" in store

    monkeypatch.setattr(TokenBlacklist, "add", classmethod(_add), raising=False)
    monkeypatch.setattr(TokenBlacklist, "is_blacklisted", classmethod(_is_blacklisted), raising=False)
    return store


def test_refresh_token_rotation_invalidates_old_token(client, seed, _memory_blacklist):
    """旧 Refresh Token 刷新一次后即失效，无法重放。"""
    college = seed.college()
    seed.user(1, college.id, username="rot_user", password="123456")

    login = client.post("/api/auth/login", json={"username": "rot_user", "password": "123456"})
    login_body = login.json()
    assert login_body["code"] == 200, login_body
    old_refresh = login_body["data"]["refresh_token"]

    # 第一次刷新成功，并返回新的 refresh token
    r1 = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    b1 = r1.json()
    assert b1["code"] == 200, b1
    new_refresh = b1["data"]["refresh_token"]
    assert new_refresh != old_refresh

    # 旧 refresh token 已被吊销，二次使用必须失败
    r2 = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.json()["code"] == 401, r2.json()

    # 新 refresh token 仍可正常使用
    r3 = client.post("/api/auth/refresh", json={"refresh_token": new_refresh})
    assert r3.json()["code"] == 200, r3.json()