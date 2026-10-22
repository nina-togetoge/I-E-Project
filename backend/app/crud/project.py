"""
项目申报与审核 数据访问层(CRUD)
"""
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_, and_, func, extract, desc, asc
from sqlalchemy.orm import Session, aliased, joinedload

from app.models import (
    ProjProject, ProjTeamMember, ProjReview, ProjBudget,
    ProjExpense, ProjAchievement, ProjMidtermCheck, ProjChangeRequest,
    SysUser, SysCollege,
)
from app.core.deps import DataScope
from app.schemas.project import PROJECT_STATUS_NAME


class ProjectCRUD:
    """项目CRUD封装"""

    PROJECT_TYPE_NAME = {1: "创新训练", 2: "创业训练", 3: "创业实践"}
    PROJECT_LEVEL_NAME = {1: "院级", 2: "校级", 3: "省级", 4: "国家级"}
    # 状态名称统一引用 schemas 中的定义，避免多处漂移（含状态 12 待指导教师确认）
    STATUS_NAME = PROJECT_STATUS_NAME

    # ========== 查询 ==========
    @staticmethod
    def get_by_id(db: Session, project_id: int) -> Optional[ProjProject]:
        return db.query(ProjProject).options(
            joinedload(ProjProject.team_members),
            joinedload(ProjProject.budgets),
            joinedload(ProjProject.leader),
            joinedload(ProjProject.teacher),
        ).filter(ProjProject.id == project_id, ProjProject.is_deleted == 0).first()

    @staticmethod
    def paginate(
        db: Session,
        *,
        offset: int,
        limit: int,
        keyword: Optional[str] = None,
        project_type: Optional[int] = None,
        project_level: Optional[int] = None,
        college_id: Optional[int] = None,
        leader_id: Optional[int] = None,
        teacher_id: Optional[int] = None,
        status: Optional[int] = None,
        status_in: Optional[List[int]] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        data_scope: Optional[DataScope] = None,
        order_by: str = "created_at",
        order_dir: str = "desc",
    ) -> Tuple[List[ProjProject], int]:
        """分页查询项目 + 数据权限过滤"""
        LeaderUser = aliased(SysUser)
        TeacherUser = aliased(SysUser)
        q = db.query(ProjProject).join(
            LeaderUser, LeaderUser.id == ProjProject.leader_id, isouter=True
        ).join(
            TeacherUser, TeacherUser.id == ProjProject.teacher_id, isouter=True
        ).join(
            SysCollege, SysCollege.id == ProjProject.college_id, isouter=True
        ).filter(ProjProject.is_deleted == 0)

        # ---- 数据权限 ----
        if data_scope and not data_scope.scope.get("all"):
            scope = data_scope.scope
            # 学生：本人是负责人 OR 是团队成员
            if scope.get("is_student"):
                member_project_ids = db.query(ProjTeamMember.project_id).filter(
                    ProjTeamMember.student_id == data_scope.user_id
                ).all()
                member_ids = [r.project_id for r in member_project_ids]
                q = q.filter(or_(
                    ProjProject.leader_id == data_scope.user_id,
                    ProjProject.id.in_(member_ids) if member_ids else False,
                ))
            # 指导教师：自己指导的项目 + 本院项目（与详情页可见范围保持一致）
            elif scope.get("teacher_user_ids"):
                t_ids = scope["teacher_user_ids"]
                conds = []
                if t_ids:
                    conds.append(ProjProject.teacher_id.in_(t_ids))
                if scope.get("college_ids"):
                    conds.append(ProjProject.college_id.in_(scope["college_ids"]))
                if conds:
                    q = q.filter(or_(*conds))
            # 学院维度
            elif scope.get("college_ids"):
                q = q.filter(ProjProject.college_id.in_(scope["college_ids"]))
            # 专家：有有效专家评审记录的项目（已取消分配的记录不再授予可见性）
            elif scope.get("expert_user_id"):
                expert_pids = db.query(ProjReview.project_id).filter(
                    ProjReview.reviewer_id == scope["expert_user_id"],
                    ProjReview.review_stage == 3,  # REVIEW_STAGE_EXPERT
                    ProjReview.is_deleted == 0,
                ).all()
                pids = [r.project_id for r in expert_pids]
                q = q.filter(ProjProject.id.in_(pids) if pids else False)

        # ---- 草稿项目仅学生可见 ----
        # 非学生角色（管理员、教师、专家等）不可见草稿状态项目
        if data_scope and data_scope.role != 1:
            q = q.filter(ProjProject.status != 0)

        # ---- 已驳回项目不在管理员项目列表中展示 ----
        # 管理员管理页只关注在办项目；已驳回项目由学生修改重提、指导教师继续指导
        if data_scope and data_scope.role == 4:
            q = q.filter(ProjProject.status != 10)

        # ---- 筛选 ----
        if keyword:
            kw = f"%{keyword}%"
            # 成果标题也纳入关键词检索（归档页标注支持按「成果」搜索）
            achievement_pids = db.query(ProjAchievement.project_id).filter(
                ProjAchievement.is_deleted == 0,
                ProjAchievement.title.like(kw),
            )
            q = q.filter(or_(
                ProjProject.project_name.like(kw),
                ProjProject.project_no.like(kw),
                ProjProject.project_summary.like(kw),
                LeaderUser.real_name.like(kw),
                TeacherUser.real_name.like(kw),
                ProjProject.id.in_(achievement_pids),
            ))
        if project_type is not None:
            q = q.filter(ProjProject.project_type == project_type)
        if project_level is not None:
            q = q.filter(ProjProject.project_level == project_level)
        if college_id is not None:
            q = q.filter(ProjProject.college_id == college_id)
        if leader_id is not None:
            q = q.filter(ProjProject.leader_id == leader_id)
        if teacher_id is not None:
            q = q.filter(ProjProject.teacher_id == teacher_id)
        if status is not None:
            q = q.filter(ProjProject.status == status)
        if status_in:
            q = q.filter(ProjProject.status.in_(status_in))
        if start_year:
            q = q.filter(extract("year", ProjProject.created_at) >= start_year)
        if end_year:
            q = q.filter(extract("year", ProjProject.created_at) <= end_year)

        total = q.with_entities(func.count(func.distinct(ProjProject.id))).scalar() or 0

        allowed_orders = {"id", "project_name", "project_type", "project_level",
                          "status", "created_at", "updated_at", "submit_time", "budget_amount"}
        order_col = getattr(ProjProject, order_by) if order_by in allowed_orders else ProjProject.created_at
        order_expr = order_col.desc() if order_dir == "desc" else order_col.asc()
        items = q.options(
            joinedload(ProjProject.leader),
            joinedload(ProjProject.teacher),
        ).order_by(order_expr).offset(offset).limit(limit).all()
        return items, total

    # ========== 增 / 改 ==========
    @staticmethod
    def create(db: Session, data: Dict[str, Any]) -> ProjProject:
        team_members_data = data.pop("team_members", [])
        budgets_data = data.pop("budgets", [])
        data.pop("attachment_ids", None)
        obj = ProjProject(**data)
        db.add(obj)
        db.flush()
        # 写团队成员
        for tm in team_members_data:
            db.add(ProjTeamMember(project_id=obj.id, **tm))
        # 写预算（金额用 Decimal 累加，避免 float 精度误差）
        total_budget = Decimal("0")
        for bg in budgets_data:
            total_budget += Decimal(str(bg.get("budget_amount") or 0))
            db.add(ProjBudget(project_id=obj.id, **bg))
        obj.budget_amount = total_budget
        db.flush()
        return obj

    @staticmethod
    def update(db: Session, obj: ProjProject, data: Dict[str, Any]) -> ProjProject:
        team_members_data = data.pop("team_members", None)
        budgets_data = data.pop("budgets", None)
        # 允许显式置空的字段：调用方传入 None 时清空；
        # 其余字段传 None 视为未填写，跳过以免触发非空约束。
        nullable_fields = {
            "teacher_id", "competition_id", "competition_session",
            "start_date", "end_date", "project_summary",
            "innovation_points", "expected_results", "reject_reason",
        }
        for f, v in data.items():
            if hasattr(obj, f) and f != "id" and (v is not None or f in nullable_fields):
                setattr(obj, f, v)
        # 替换团队成员
        if team_members_data is not None:
            db.query(ProjTeamMember).filter(ProjTeamMember.project_id == obj.id).delete(
                synchronize_session=False
            )
            for tm in team_members_data:
                db.add(ProjTeamMember(project_id=obj.id, **tm))
        # 更新预算：同名科目就地更新（保留行 id 与已使用金额），新科目新增，消失科目删除。
        # 原实现"整表删除重建"会重置 used_amount 并使报销单 budget_item_id 悬空。
        if budgets_data is not None:
            existing: Dict[str, List[ProjBudget]] = {}
            for b in db.query(ProjBudget).filter(ProjBudget.project_id == obj.id).all():
                existing.setdefault(b.budget_item, []).append(b)
            total_budget = Decimal("0")
            for bg in budgets_data:
                total_budget += Decimal(str(bg.get("budget_amount") or 0))
                rows = existing.get(bg.get("budget_item")) or []
                if rows:
                    b = rows.pop(0)
                    b.budget_amount = bg.get("budget_amount") or 0
                    b.remark = bg.get("remark")
                else:
                    db.add(ProjBudget(project_id=obj.id, **bg))
            for rows in existing.values():
                for b in rows:
                    db.delete(b)
            obj.budget_amount = total_budget
        db.flush()
        return obj

    @staticmethod
    def generate_project_no(db: Session, year: int) -> str:
        """生成项目编号：IE{year}{6位自增序号}
        基于当年最大编号 +1；并发写入可能撞唯一键，调用方需配合重试（见 bump_project_no）"""
        prefix = f"IE{year}"
        max_no = db.query(func.max(ProjProject.project_no)).filter(
            ProjProject.project_no.like(f"{prefix}%")
        ).scalar()
        seq = 1
        if max_no and len(max_no) >= len(prefix) + 6:
            try:
                seq = int(max_no[-6:]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}{seq:06d}"

    @staticmethod
    def bump_project_no(project_no: str, step: int = 1) -> str:
        """把项目编号末尾 6 位序号 +step，用于唯一键冲突后的重试"""
        prefix, seq = project_no[:-6], project_no[-6:]
        try:
            return f"{prefix}{int(seq) + step:06d}"
        except ValueError:
            return project_no


class AchievementCRUD:
    """项目成果CRUD"""

    @staticmethod
    def list_by_project(db: Session, project_id: int) -> List[ProjAchievement]:
        return db.query(ProjAchievement).filter(
            ProjAchievement.project_id == project_id,
            ProjAchievement.is_deleted == 0
        ).order_by(ProjAchievement.created_at.desc()).all()

    @staticmethod
    def create(db: Session, data: Dict[str, Any]) -> ProjAchievement:
        obj = ProjAchievement(**data)
        db.add(obj)
        db.flush()
        return obj

    @staticmethod
    def delete(db: Session, pk: int) -> int:
        rows = db.query(ProjAchievement).filter(
            ProjAchievement.id == pk, ProjAchievement.is_deleted == 0
        ).update({"is_deleted": 1}, synchronize_session=False)
        db.flush()
        return rows
