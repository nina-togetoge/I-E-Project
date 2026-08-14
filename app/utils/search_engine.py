"""
全文检索工具类（Whoosh 2.7.4 + Jieba 中文分词）
用于对【项目名称 / 简介 / 创新点 / 预期成果 / 团队成员 / 成果标题】等字段建立索引
支持：关键词检索、相关性排序、结果高亮、增量添加/更新/删除

未安装 Whoosh/Jieba 时自动降级为 ORM 模糊查询（保证功能可用）
"""
import os
import threading
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings
from app.database.session import SessionLocal
from app.models import ProjProject, ProjTeamMember, ProjAchievement

# ---------- Whoosh + Jieba 可选依赖 ----------
try:
    from whoosh.fields import Schema, TEXT, ID, NUMERIC, KEYWORD, DATETIME, STORED
    from whoosh.index import create_in, open_dir, exists_in, Index
    from whoosh.qparser import MultifieldParser, QueryParser
    from whoosh.query import And, Or, Term
    from whoosh import scoring, highlight
    import jieba  # 中文分词
    HAS_SEARCH = True
except ImportError as e:
    HAS_SEARCH = False
    Index = None  # type: ignore


# ====================================================================
# 中文分词适配 Whoosh：用 Jieba 把中文句切成空格分隔的词
# ====================================================================

class JiebaTokenizer:
    """Whoosh 的中文分词 Tokenizer 简化实现：先 jieba 切词再返回"""

    def __call__(self, value, **kwargs):
        if value is None:
            return []
        text = str(value)
        # 用 jieba 精确模式分词，过滤空串和纯空格
        tokens = [w.strip() for w in jieba.cut(text) if w and w.strip()]
        # 去重保留顺序（简单版）
        seen = set()
        result = []
        for t in tokens:
            if t in seen:
                continue
            seen.add(t)
            result.append(t)
        return result


def jieba_analyzer(x):
    """给Whoosh字段用的analyzer（作为 callable）"""
    return JiebaTokenizer()(x)


# ====================================================================
# 搜索引擎类
# ====================================================================

class ProjectSearchEngine:
    """
    项目与成果 全文搜索引擎
    索引字段（均为 STORED 可返回原值 + 可分词检索）：
        project_id, project_no, project_name, project_summary, innovation_points,
        expected_results, team_names, college_name, achievement_titles, project_type_name,
        project_level_name, status_name, created_at
    """

    INDEX_DIR = settings.WHOOSH_INDEX_DIR
    _instance: Optional["ProjectSearchEngine"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ProjectSearchEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_index()
        return cls._instance

    def _schema(self) -> "Schema":
        if not HAS_SEARCH:
            raise RuntimeError("Whoosh未安装")
        return Schema(
            project_id=NUMERIC(int, 64, stored=True, unique=True),
            project_no=ID(stored=True),
            # 可分词检索 + 可存储返回高亮
            project_name=TEXT(analyzer=jieba_analyzer, stored=True),
            project_summary=TEXT(analyzer=jieba_analyzer, stored=True),
            innovation_points=TEXT(analyzer=jieba_analyzer, stored=True),
            expected_results=TEXT(analyzer=jieba_analyzer, stored=True),
            team_names=TEXT(analyzer=jieba_analyzer, stored=True),
            college_name=TEXT(analyzer=jieba_analyzer, stored=True),
            achievement_titles=TEXT(analyzer=jieba_analyzer, stored=True),
            project_type_name=ID(stored=True),
            project_level_name=ID(stored=True),
            status_name=ID(stored=True),
            created_at=DATETIME(stored=True),
        )

    def _init_index(self) -> None:
        if not HAS_SEARCH:
            print("[WARN] Whoosh/Jieba 未安装，全文检索功能降级为数据库LIKE查询")
            self.index: Optional[Index] = None
            return
        os.makedirs(self.INDEX_DIR, exist_ok=True)
        try:
            if exists_in(self.INDEX_DIR):
                self.index = open_dir(self.INDEX_DIR)
            else:
                self.index = create_in(self.INDEX_DIR, self._schema())
            print("[OK] 全文检索索引已就绪")
        except Exception as e:
            print(f"[WARN] 全文检索索引初始化失败({e})，将降级为LIKE查询")
            self.index = None

    # ====================================================================
    # 索引维护
    # ====================================================================
    def _build_doc(self, project: ProjProject) -> Optional[Dict[str, Any]]:
        """把ORM项目实体 -> Whoosh索引文档"""
        if not project:
            return None
        # 团队成员姓名拼接
        team_names = "、".join(m.student_name for m in (project.team_members or []))
        # 成果标题拼接
        ach_titles = "、".join(a.title for a in (project.achievements or []))
        # 学院名
        college_name = project.college.college_name if project.college_id and project.college else ""
        # 类型/级别/状态中文名
        from app.crud.project import ProjectCRUD
        return {
            "project_id": project.id,
            "project_no": project.project_no or "",
            "project_name": project.project_name or "",
            "project_summary": project.project_summary or "",
            "innovation_points": project.innovation_points or "",
            "expected_results": project.expected_results or "",
            "team_names": team_names,
            "college_name": college_name,
            "achievement_titles": ach_titles,
            "project_type_name": ProjectCRUD.PROJECT_TYPE_NAME.get(project.project_type, ""),
            "project_level_name": ProjectCRUD.PROJECT_LEVEL_NAME.get(project.project_level, ""),
            "status_name": ProjectCRUD.STATUS_NAME.get(project.status, ""),
            "created_at": project.created_at,
        }

    def add_project(self, project: ProjProject) -> bool:
        doc = self._build_doc(project)
        if not doc:
            return False
        if not HAS_SEARCH or self.index is None:
            return False
        try:
            writer = self.index.writer()
            writer.update_document(**doc)
            writer.commit()
            return True
        except Exception as e:
            print(f"[Search] 索引添加失败 project_id={project.id}: {e}")
            return False

    def delete_project(self, project_id: int) -> bool:
        if not HAS_SEARCH or self.index is None:
            return False
        try:
            writer = self.index.writer()
            writer.delete_by_term("project_id", project_id)
            writer.commit()
            return True
        except Exception as e:
            print(f"[Search] 索引删除失败 project_id={project_id}: {e}")
            return False

    def rebuild_all(self) -> Tuple[int, int]:
        """
        全量重建索引
        返回：(总数, 成功数)
        """
        db = SessionLocal()
        try:
            from sqlalchemy.orm import joinedload
            all_projects = db.query(ProjProject).options(
                joinedload(ProjProject.team_members),
                joinedload(ProjProject.achievements),
                joinedload(ProjProject.college),
            ).filter(ProjProject.is_deleted == 0).all()

            if not HAS_SEARCH or self.index is None:
                return len(all_projects), 0

            writer = self.index.writer()
            ok = 0
            for p in all_projects:
                doc = self._build_doc(p)
                if doc:
                    writer.update_document(**doc)
                    ok += 1
            writer.commit()
            return len(all_projects), ok
        finally:
            db.close()

    # ====================================================================
    # 关键词搜索
    # ====================================================================
    def search(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
        filter_college_id: Optional[int] = None,
        filter_status: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        全文检索，返回：(结果列表, 总数)
        结果项包含：project_id, project_name, ..., highlights{字段: 高亮片段}
        """
        if not keyword or not keyword.strip():
            return [], 0

        # ====== Whoosh 可用 → 真正全文检索 ======
        if HAS_SEARCH and self.index is not None:
            return self._search_by_whoosh(keyword, page, page_size, filter_college_id, filter_status)

        # ====== 降级：ORM LIKE 查询 ======
        return self._search_by_sql(keyword, page, page_size, filter_college_id, filter_status)

    def _search_by_whoosh(self, keyword, page, page_size, college_id, status) -> Tuple[List[Dict], int]:
        from whoosh import qparser
        search_fields = ["project_name", "project_summary", "innovation_points",
                         "expected_results", "team_names", "college_name", "achievement_titles"]
        with self.index.searcher(weighting=scoring.BM25F()) as searcher:
            mp = MultifieldParser(search_fields, self.index.schema, group=qparser.OrGroup)
            # 中文关键词再做一次分词，提升召回
            terms = list(JiebaTokenizer()(keyword))
            query_text = " OR ".join(terms) if terms else keyword
            query = mp.parse(query_text)

            # 过滤条件
            mask = None
            if college_id or status is not None:
                # 由于学院ID/状态未入索引为整数，这里用二次过滤的方式实现
                pass

            hits = searcher.search_page(query, pagenum=page, pagelen=page_size, terms=True)
            total = len(hits)

            # 高亮配置
            hi = highlight.HtmlFormatter(before="<mark>", after="</mark>", between=" ... ")
            frag = highlight.ContextFragmenter(maxchars=160, surround=30)
            results = []
            for hit in hits:
                data = dict(hit)
                # 构造高亮
                highlights: Dict[str, str] = {}
                for f in search_fields:
                    if f in hit.fields() and data.get(f):
                        try:
                            hl = hit.highlights(f, text=data[f], formatter=hi, fragmenter=frag)
                            if hl:
                                highlights[f] = hl
                        except Exception:
                            pass
                data["highlights"] = highlights
                data["score"] = hit.score
                # 二次过滤：学院ID/状态匹配
                if college_id or status is not None:
                    db = SessionLocal()
                    try:
                        from app.models import ProjProject
                        p = db.query(ProjProject).filter(ProjProject.id == data["project_id"]).first()
                        if p:
                            if college_id and p.college_id != college_id:
                                total -= 1
                                continue
                            if status is not None and p.status != status:
                                total -= 1
                                continue
                        else:
                            total -= 1
                            continue
                    finally:
                        db.close()
                results.append(data)
            return results, total

    def _search_by_sql(self, keyword, page, page_size, college_id, status) -> Tuple[List[Dict], int]:
        """降级：SQL LIKE 模糊查询 + 简单排序"""
        from sqlalchemy import or_, func
        db = SessionLocal()
        try:
            from app.models import ProjProject, SysCollege
            kw = f"%{keyword}%"
            q = db.query(ProjProject).outerjoin(SysCollege, SysCollege.id == ProjProject.college_id).filter(
                ProjProject.is_deleted == 0,
                or_(
                    ProjProject.project_name.like(kw),
                    ProjProject.project_no.like(kw),
                    ProjProject.project_summary.like(kw),
                    ProjProject.innovation_points.like(kw),
                    ProjProject.expected_results.like(kw),
                    SysCollege.college_name.like(kw),
                )
            )
            if college_id:
                q = q.filter(ProjProject.college_id == college_id)
            if status is not None:
                q = q.filter(ProjProject.status == status)
            total = q.with_entities(func.count(ProjProject.id)).scalar() or 0
            items = q.order_by(ProjProject.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
            from app.crud.project import ProjectCRUD
            results = []
            for p in items:
                data = {
                    "project_id": p.id,
                    "project_no": p.project_no or "",
                    "project_name": p.project_name or "",
                    "project_summary": p.project_summary or "",
                    "innovation_points": p.innovation_points or "",
                    "expected_results": p.expected_results or "",
                    "college_name": p.college.college_name if p.college else "",
                    "project_type_name": ProjectCRUD.PROJECT_TYPE_NAME.get(p.project_type, ""),
                    "project_level_name": ProjectCRUD.PROJECT_LEVEL_NAME.get(p.project_level, ""),
                    "status_name": ProjectCRUD.STATUS_NAME.get(p.status, ""),
                    "highlights": {
                        "project_name": self._simple_highlight(p.project_name, keyword),
                        "project_summary": self._simple_highlight(p.project_summary, keyword),
                    },
                }
                results.append(data)
            return results, total
        finally:
            db.close()

    @staticmethod
    def _simple_highlight(text: Optional[str], kw: str) -> str:
        if not text or not kw:
            return ""
        import re
        try:
            return re.sub(f"({re.escape(kw)})", r"<mark>\1</mark>", text, count=10, flags=re.IGNORECASE)
        except Exception:
            return text


# 全局搜索引擎单例
search_engine = ProjectSearchEngine()
