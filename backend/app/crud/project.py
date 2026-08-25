"""
项目申报与审核 数据访问层(CRUD)
"""
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime

from sqlalchemy import or_, and_, func, extract, desc, asc
from sqlalchemy.orm import Session, aliased, joinedload

from app.models import (
    ProjProject, ProjTeamMember, ProjReview, ProjBudget,
    ProjExpense, ProjAchievement, ProjMidtermCheck, ProjChangeRequest,
    SysUser, SysCollege,
)
from app.core.deps import DataScope


class ProjectCRUD:
    """项目CRUD封装"""

    PROJECT_TYPE_NAME = {1: "创新训练", 2: "创业训练", 3: "创业实践"}
    PROJECT_LEVEL_NAME = {1: "校级", 2: "省级", 3: "国家级"}
    STATUS_NAME = {
        0: "草稿", 1: "待学院初审", 2: "学院初审通过", 3: "待校级复审",
        4: "校级复审通过", 5: "待专家评审", 6: "已立项", 7: "中期检查",
        8: "待结题", 9: "已结题", 10: "已驳回", 11: "已撤销",
    }

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
            # 指导教师：自己是指导老师
            elif scope.get("teacher_user_ids"):
                t_ids = scope["teacher_user_ids"]
                if t_ids:
                    q = q.filter(ProjProject.teacher_id.in_(t_ids))
                if scope.get("college_ids"):
                    q = q.filter(ProjProject.college_id.in_(scope["college_ids"]))
            # 学院维度
            elif scope.get("college_ids"):
                q = q.filter(ProjProject.college_id.in_(scope["college_ids"]))
            # 专家：有评审记录的项目
            elif scope.get("expert_user_id"):
                expert_pids = db.query(ProjReview.project_id).filter(
                    ProjReview.reviewer_id == scope["expert_user_id"]
                ).all()
                pids = [r.project_id for r in expert_pids]
                q = q.filter(ProjProject.id.in_(pids) if pids else False)

        # ---- 筛选 ----
        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(or_(
                ProjProject.project_name.like(kw),
                ProjProject.project_no.like(kw),
                ProjProject.project_summary.like(kw),
                LeaderUser.real_name.like(kw),
                TeacherUser.real_name.like(kw),
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
        # 写预算
        total_budget = 0
        for bg in budgets_data:
            total_budget += float(bg.get("budget_amount", 0) or 0)
            db.add(ProjBudget(project_id=obj.id, **bg))
        obj.budget_amount = total_budget
        db.flush()
        return obj

    @staticmethod
    def update(db: Session, obj: ProjProject, data: Dict[str, Any]) -> ProjProject:
        team_members_data = data.pop("team_members", None)
        budgets_data = data.pop("budgets", None)
        for f, v in data.items():
            if v is not None and hasattr(obj, f) and f != "id":
                setattr(obj, f, v)
        # 替换团队成员
        if team_members_data is not None:
            db.query(ProjTeamMember).filter(ProjTeamMember.project_id == obj.id).delete(
                synchronize_session=False
            )
            for tm in team_members_data:
                db.add(ProjTeamMember(project_id=obj.id, **tm))
        # 替换预算
        if budgets_data is not None:
            db.query(ProjBudget).filter(ProjBudget.project_id == obj.id).delete(
                synchronize_session=False
            )
            total_budget = 0
            for bg in budgets_data:
                total_budget += float(bg.get("budget_amount", 0) or 0)
                db.add(ProjBudget(project_id=obj.id, **bg))
            obj.budget_amount = total_budget
        db.flush()
        return obj

    @staticmethod
    def generate_project_no(db: Session, year: int) -> str:
        """生成项目编号：IE{year}{6位自增序号}"""
        prefix = f"IE{year}"
        max_no = db.query(func.max(ProjProject.project_no)).filter(
            ProjProject.project_no.like(f"{prefix}%")
        ).scalar()
        seq = 1
        if max_no and len(max_no) >= 12:
            try:
                seq = int(max_no[-6:]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}{seq:06d}"


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
