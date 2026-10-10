"""FastAPI API / 服务层测试公共夹具。

设计要点（不改动业务代码）：
- 使用**临时文件型 SQLite**：保证 get_db 与全文检索引擎各自新建会话时，都能看到同一份已提交数据。
- 建表前对全局 ``Base.metadata`` 做两处仅在测试进程生效的适配：
  1) SQLite 索引名全局唯一 —— 把跨表同名索引加上"表名_"前缀（MySQL 索引名按表隔离，SQLite 全局隔离）；
  2) BigInteger 列在 SQLite 下改用 Integer —— 否则 ``BIGINT PRIMARY KEY`` 不是 rowid 别名，无法自增。
- 断言针对响应体的业务 ``code``：本项目全局异常处理器把业务异常/参数校验异常统一包装成
  ``HTTP 200 + {code, message, data}``，因此 401/403/400/422 体现在 body 的 code 字段。
- 应用用 ``TestClient(app)`` 构造（**不用** ``with``），避免触发 lifespan（Whoosh/Redis 初始化）。
"""
import os
import tempfile
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import BigInteger, Integer, create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import app.models as M  # noqa: F401  触发所有 ORM 模型注册
from app.database.session import Base, get_db
from app.core.security import create_access_token, hash_password
from app.utils.redis_cache import TokenBlacklist


# ====================================================================
# SQLite 适配（一次性，仅影响测试进程内的 metadata）
# ====================================================================
_bigint_sqlite = BigInteger().with_variant(Integer, "sqlite")
for _table in Base.metadata.tables.values():
    for _idx in _table.indexes:
        if _idx.name and not _idx.name.startswith(_table.name + "_"):
            _idx.name = f"{_table.name}_{_idx.name}"
    for _col in _table.columns:
        if isinstance(_col.type, BigInteger):
            _col.type = _bigint_sqlite


# ====================================================================
# 数据库会话夹具
# ====================================================================
@pytest.fixture()
def engine():
    """每个用例一个独立的临时 SQLite 文件库。"""
    d = tempfile.mkdtemp(prefix="ie_test_")
    eng = create_engine(
        "sqlite:///" + os.path.join(d, "test.db"),
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def SessionFactory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture()
def db(SessionFactory):
    """供服务层用例直接使用的会话（应用层通过 client 内的 override 使用独立会话）。"""
    s = SessionFactory()
    yield s
    s.close()


@pytest.fixture()
def client(SessionFactory, monkeypatch):
    """FastAPI TestClient：注入测试库、隔离 Redis 与真实 MySQL。"""
    import app.core.middleware as mw
    import app.utils.search_engine as se
    from main import app

    # 1) 免 Redis：token 黑名单恒为未拉黑
    monkeypatch.setattr(TokenBlacklist, "is_blacklisted", classmethod(lambda cls, t, j: False))
    # 2) 免真实 MySQL：操作日志落库改为空操作（后台线程写入直连 SessionLocal）
    monkeypatch.setattr(mw, "_write_operation_log_sync", lambda data: None)
    # 3) 全文检索：会话指向测试库，并强制走 SQL 降级路径，保证结果由测试数据决定
    monkeypatch.setattr(se, "SessionLocal", SessionFactory)
    monkeypatch.setattr(se.search_engine, "index", None)

    def _override_get_db():
        s = SessionFactory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    c = TestClient(app)  # 不使用 with：跳过 lifespan 启动事件
    yield c
    app.dependency_overrides.clear()


# ====================================================================
# 造数工厂
# ====================================================================
class Seeder:
    """可复用 seed 工厂：每个方法使用独立短会话并提交，避免残留事务导致 SQLite 锁。"""

    def __init__(self, session_factory):
        self.sf = session_factory
        self._seq = 0
        self._by_role = {}

    def _name(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}_{uuid.uuid4().hex[:6]}"

    def _add(self, obj):
        s = self.sf()
        try:
            s.add(obj)
            s.commit()
            s.refresh(obj)
            s.expunge(obj)
        finally:
            s.close()
        return obj

    # ---------- 实体 ----------
    def college(self, name=None):
        return self._add(M.SysCollege(
            college_code=self._name("C"), college_name=name or "测试学院",
            sort_order=0, status=1,
        ))

    def user(self, role, college_id=None, real_name=None, password="123456", username=None):
        u = M.SysUser(
            username=username or self._name("u"),
            password_hash=hash_password(password),
            real_name=real_name or f"用户{int(role)}",
            role=int(role), college_id=college_id, status=1, force_change_pwd=0,
        )
        self._add(u)
        self._by_role.setdefault(int(role), []).append(u)
        return u

    def project(self, college_id, leader_id, teacher_id=None, status=0, name=None,
                budget="10000.00", used="0.00", project_no=None):
        return self._add(M.ProjProject(
            project_name=name or self._name("项目"),
            project_type=1, project_level=1,
            college_id=college_id, leader_id=leader_id, teacher_id=teacher_id,
            status=status, budget_amount=Decimal(budget), used_amount=Decimal(used),
            project_no=project_no, submit_time=datetime.now(),
        ))

    def assign_expert(self, project_id, expert_id, stage=3):
        return self._add(M.ProjReview(
            project_id=project_id, review_stage=stage, reviewer_id=expert_id,
            reviewer_name="评审专家", review_result=99,
            review_time=datetime.now(), review_comment=None, score=None,
        ))

    def midterm(self, project_id, status=2):
        return self._add(M.ProjMidtermCheck(
            project_id=project_id, status=status,
            progress_desc="进展", submit_time=datetime.now(),
        ))

    def achievement(self, project_id, title="成果A"):
        return self._add(M.ProjAchievement(
            project_id=project_id, achievement_type=1, title=title,
        ))

    def expense(self, project_id, applicant_id, amount, status=6, applicant_name="申请人",
                budget_item_id=None):
        return self._add(M.ProjExpense(
            expense_no=self._name("EXP"), project_id=project_id,
            applicant_id=applicant_id, applicant_name=applicant_name,
            expense_amount=Decimal(amount), expense_desc="费用说明",
            status=status, submit_time=datetime.now(), budget_item_id=budget_item_id,
        ))

    def budget(self, project_id, item="设备费", amount="10000.00", used="0.00"):
        return self._add(M.ProjBudget(
            project_id=project_id, budget_item=item,
            budget_amount=Decimal(amount), used_amount=Decimal(used),
        ))

    def change(self, project_id, applicant_id, change_type=1, status=0, reason="延期申请"):
        return self._add(M.ProjChangeRequest(
            project_id=project_id, change_type=change_type, change_reason=reason,
            applicant_id=applicant_id, status=status, submit_time=datetime.now(),
        ))

    def announcement(self, title="测试公告", status=1, created_by=None):
        return self._add(M.Announcement(
            title=title, content="公告正文", announcement_type=1, status=status,
            priority=1, created_by=created_by,
        ))

    def competition(self, title="测试比赛", status=1, created_by=None):
        return self._add(M.Competition(
            title=title, competition_type=1, level=1, status=status,
            organizer="主办方", created_by=created_by,
        ))

    def attachment(self, biz_type, biz_id, uploader_id, file_path=None, file_name="a.pdf"):
        return self._add(M.SysAttachment(
            biz_type=biz_type, biz_id=biz_id, file_name=file_name,
            file_path=file_path or os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}.pdf"),
            file_size=8, file_type="application/pdf", file_ext="pdf",
            uploader_id=uploader_id, uploader_name="上传者", download_count=0,
        ))

    # ---------- 只读辅助（新会话读取，避免残留事务） ----------
    def first_by_role(self, role):
        return self._by_role[int(role)][0]

    def reload(self, model, pk):
        s = self.sf()
        try:
            obj = s.get(model, pk)
            if obj is not None:
                s.expunge(obj)
            return obj
        finally:
            s.close()

    def count_reviews(self, project_id, stage=None, result=None):
        s = self.sf()
        try:
            q = s.query(M.ProjReview).filter(M.ProjReview.project_id == project_id)
            if stage is not None:
                q = q.filter(M.ProjReview.review_stage == stage)
            if result is not None:
                q = q.filter(M.ProjReview.review_result == result)
            return q.count()
        finally:
            s.close()


@pytest.fixture()
def seed(SessionFactory):
    return Seeder(SessionFactory)


@pytest.fixture()
def auth_headers(seed):
    """构造鉴权头：入参可为 SysUser 对象，或角色 int（取该角色首个 seed 用户）。"""
    def _make(subject):
        user = seed.first_by_role(subject) if isinstance(subject, int) else subject
        return {"Authorization": f"Bearer {create_access_token(user)}"}
    return _make