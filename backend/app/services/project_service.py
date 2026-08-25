"""
项目申报与审核 业务逻辑层(Service)
"""
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.core.security import RoleEnum, ROLE_NAME_MAP
from app.core.exceptions import (
    PermissionDeniedException, ResourceNotFoundException, ParamValidateException,
    DataConflictException,
)
from app.core.deps import PaginationParams, DataScope
from app.crud.user import CollegeCRUD, UserCRUD
from app.crud.project import ProjectCRUD, AchievementCRUD
from app.crud.review import ReviewCRUD
from app.schemas.review import REVIEW_STAGE_COLLEGE
from app.models import (
    ProjProject, SysUser, ProjAchievement,
)
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectQueryParams,
    ProjectListItem, ProjectDetailResponse, ProjectSubmitResponse,
    AchievementCreate, AchievementResponse, ProjectStatisticsResponse,
    StatisticsTrendItem, PROJECT_STATUS_DRAFT, PROJECT_STATUS_PENDING_COLLEGE,
    PROJECT_STATUS_NAME,
)


class ProjectService:
    """项目申报业务服务"""

    @staticmethod
    def _to_list_item(obj: ProjProject) -> ProjectListItem:
        """ORM -> Pydantic列表项"""
        item = ProjectListItem.model_validate(obj)
        item.project_type_name = ProjectCRUD.PROJECT_TYPE_NAME.get(item.project_type, "")
        item.project_level_name = ProjectCRUD.PROJECT_LEVEL_NAME.get(item.project_level, "")
        item.status_name = ProjectCRUD.STATUS_NAME.get(item.status, "")
        if obj.leader:
            item.leader_name = obj.leader.real_name
        if obj.teacher:
            item.teacher_name = obj.teacher.real_name
        if obj.college_id:
            college = CollegeCRUD.get_by_id(obj._sa_instance_state.session, obj.college_id) \
                if hasattr(obj, "_sa_instance_state") and obj._sa_instance_state.session else None
            if college:
                item.college_name = college.college_name
        return item

    @staticmethod
    def _to_detail(db: Session, obj: ProjProject) -> ProjectDetailResponse:
        """ORM -> Pydantic详情（含团队/预算等子表）"""
        item = ProjectDetailResponse.model_validate(obj)
        item.project_type_name = ProjectCRUD.PROJECT_TYPE_NAME.get(item.project_type, "")
        item.project_level_name = ProjectCRUD.PROJECT_LEVEL_NAME.get(item.project_level, "")
        item.status_name = ProjectCRUD.STATUS_NAME.get(item.status, "")
        if obj.leader:
            item.leader_name = obj.leader.real_name
        if obj.teacher:
            item.teacher_name = obj.teacher.real_name
        college = CollegeCRUD.get_by_id(db, obj.college_id)
        if college:
            item.college_name = college.college_name
        return item

    @staticmethod
    def _check_edit_permission(project: ProjProject, operator: SysUser) -> None:
        """编辑权限：草稿状态下，负责人/指导教师可编辑；管理员可编辑"""
        if operator.role == RoleEnum.ADMIN:
            return
        if project.status not in (PROJECT_STATUS_DRAFT, 10):  # 草稿或已驳回可修改
            raise PermissionDeniedException(message="当前状态不可修改，如有需要请先撤回")
        if operator.role == RoleEnum.STUDENT:
            if project.leader_id != operator.id:
                raise PermissionDeniedException(message="仅项目负责人可编辑本项目")
        elif operator.role == RoleEnum.TEACHER:
            if project.teacher_id != operator.id and project.leader_id != operator.id:
                raise PermissionDeniedException(message="仅指导教师或负责人可编辑")

    # ========== 列表 / 详情 ==========
    @staticmethod
    def paginate(db: Session, pager: PaginationParams, params: ProjectQueryParams,
                 data_scope: DataScope) -> Tuple[List[ProjectListItem], int]:
        items, total = ProjectCRUD.paginate(
            db,
            offset=pager.offset,
            limit=pager.limit,
            keyword=params.keyword,
            project_type=params.project_type,
            project_level=params.project_level,
            college_id=params.college_id,
            leader_id=params.leader_id,
            teacher_id=params.teacher_id,
            status=params.status,
            start_year=params.start_year,
            end_year=params.end_year,
            data_scope=data_scope,
            order_by=pager.order_by or "created_at",
            order_dir=pager.order_dir,
        )
        # 批量查学院名称（避免N+1）
        college_ids = list({i.college_id for i in items if i.college_id})
        college_map = {}
        if college_ids:
            from app.models import SysCollege
            colleges = db.query(SysCollege).filter(SysCollege.id.in_(college_ids)).all()
            college_map = {c.id: c.college_name for c in colleges}
        result = []
        for obj in items:
            it = ProjectService._to_list_item(obj)
            if it.college_id and college_map.get(it.college_id):
                it.college_name = college_map[it.college_id]
            result.append(it)
        return result, total

    @staticmethod
    def get_detail(db: Session, project_id: int, operator: SysUser) -> ProjectDetailResponse:
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 数据权限
        scope = DataScope.__new__(DataScope)
        scope.user = operator
        scope.db = db
        scope.role = operator.role
        scope.college_id = operator.college_id
        scope.user_id = operator.id
        scope.scope = scope._compute_scope()
        ok = False
        if scope.scope.get("all"):
            ok = True
        elif scope.scope.get("is_student"):
            if obj.leader_id == operator.id:
                ok = True
            else:
                from app.models import ProjTeamMember
                m = db.query(ProjTeamMember).filter(
                    ProjTeamMember.project_id == project_id,
                    ProjTeamMember.student_id == operator.id
                ).first()
                ok = m is not None
        elif scope.scope.get("teacher_user_ids"):
            ok = obj.teacher_id == operator.id or \
                 (scope.scope.get("college_ids") and obj.college_id in scope.scope["college_ids"])
        elif scope.scope.get("college_ids"):
            ok = obj.college_id in scope.scope["college_ids"]
        elif scope.scope.get("expert_user_id"):
            from app.models import ProjReview
            ok = db.query(ProjReview).filter(
                ProjReview.project_id == project_id,
                ProjReview.reviewer_id == operator.id
            ).first() is not None
        if not ok:
            raise PermissionDeniedException(message="无权查看该项目")
        return ProjectService._to_detail(db, obj)

    # ========== 创建 / 修改 / 删除 ==========
    @staticmethod
    def create(db: Session, req: ProjectCreate, operator: SysUser,
               as_draft: bool = True) -> ProjectDetailResponse:
        """创建项目：负责人=当前学生；草稿保存 or 直接提交"""
        if operator.role == RoleEnum.STUDENT:
            pass  # OK
        elif operator.role not in (RoleEnum.ADMIN,):
            raise PermissionDeniedException(message="学生身份方可创建申报项目")

        # 校验学院存在
        if not CollegeCRUD.get_by_id(db, req.college_id):
            raise ParamValidateException(message="所选学院不存在")
        # 校验指导教师存在且为教师角色
        if req.teacher_id:
            t = UserCRUD.get_by_id(db, req.teacher_id)
            if not t:
                raise ParamValidateException(message="指导教师不存在")
            if t.role not in (RoleEnum.TEACHER, RoleEnum.ADMIN):
                raise ParamValidateException(message="所选用户不是指导教师")

        data = req.model_dump()
        # 学生身份 => 默认自己是负责人
        if operator.role == RoleEnum.STUDENT:
            data["leader_id"] = operator.id
            data["college_id"] = operator.college_id or data["college_id"]
        elif "leader_id" not in data or not data.get("leader_id"):
            raise ParamValidateException(message="管理员创建需额外指定负责人（通过扩展字段，此示例暂不支持）")

        # 直接提交时，必须先校验必填项（与 submit 方法保持一致）
        if not as_draft:
            missing = []
            if not req.project_name:
                missing.append("项目名称")
            if not req.teacher_id:
                missing.append("指导教师")
            if not req.team_members or len(req.team_members) == 0:
                missing.append("团队成员(至少1人)")
            if not req.budgets or len(req.budgets) == 0:
                missing.append("预算明细")
            if missing:
                raise ParamValidateException(message="提交前请完善以下必填项：" + "、".join(missing))

        data["status"] = PROJECT_STATUS_DRAFT if as_draft else PROJECT_STATUS_PENDING_COLLEGE
        if not as_draft:
            data["submit_time"] = datetime.now()

        obj = ProjectCRUD.create(db, data)
        # 提交时自动生成编号
        if not as_draft:
            year = date.today().year
            obj.project_no = ProjectCRUD.generate_project_no(db, year)
            db.flush()

        # 4. 关联临时附件（biz_id=0 的附件）到新项目
        if req.attachment_ids:
            from app.models.user import SysAttachment
            db.query(SysAttachment).filter(
                SysAttachment.id.in_(req.attachment_ids),
                SysAttachment.biz_type == "project",
                SysAttachment.biz_id == 0,
            ).update({SysAttachment.biz_id: obj.id}, synchronize_session=False)

        db.commit()
        db.refresh(obj)
        return ProjectService._to_detail(db, obj)

    @staticmethod
    def update(db: Session, project_id: int, req: ProjectUpdate, operator: SysUser) -> ProjectDetailResponse:
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        ProjectService._check_edit_permission(obj, operator)
        data = req.model_dump(exclude_unset=True)
        # 如果包含 teacher_id，校验
        if req.teacher_id:
            t = UserCRUD.get_by_id(db, req.teacher_id)
            if not t or t.role not in (RoleEnum.TEACHER, RoleEnum.ADMIN):
                raise ParamValidateException(message="指导教师无效")
        obj = ProjectCRUD.update(db, obj, data)
        db.commit()
        db.refresh(obj)
        return ProjectService._to_detail(db, obj)

    @staticmethod
    def submit(db: Session, project_id: int, operator: SysUser) -> ProjectSubmitResponse:
        """草稿 -> 提交进入学院初审"""
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        ProjectService._check_edit_permission(obj, operator)
        if obj.status != PROJECT_STATUS_DRAFT and obj.status != 10:
            raise ParamValidateException(message="当前项目状态不可提交审核")
        # 必填校验
        missing = []
        if not obj.project_name:
            missing.append("项目名称")
        if not obj.teacher_id:
            missing.append("指导教师")
        if not obj.team_members or len(obj.team_members) == 0:
            missing.append("团队成员(至少1人)")
        if not obj.budgets or len(obj.budgets) == 0:
            missing.append("预算明细")
        if missing:
            raise ParamValidateException(message="提交前请完善以下必填项：" + "、".join(missing))

        obj.status = PROJECT_STATUS_PENDING_COLLEGE
        obj.submit_time = datetime.now()
        if not obj.project_no:
            year = date.today().year
            obj.project_no = ProjectCRUD.generate_project_no(db, year)
        db.flush()

        # 创建学院初审占位审核记录，使指导教师在待审核列表中看到该项目
        if obj.teacher_id and not ReviewCRUD.exist_by_project_stage_reviewer(
            db, obj.id, REVIEW_STAGE_COLLEGE, obj.teacher_id
        ):
            teacher = UserCRUD.get_by_id(db, obj.teacher_id)
            ReviewCRUD.create(db, {
                "project_id": obj.id,
                "review_stage": REVIEW_STAGE_COLLEGE,
                "reviewer_id": obj.teacher_id,
                "reviewer_name": teacher.real_name if teacher else "",
                "review_result": 99,  # 占位=待评审
                "review_comment": None,
                "review_time": datetime.now(),
            })

        db.commit()
        return ProjectSubmitResponse(
            project_id=obj.id,
            status=obj.status,
            status_name=PROJECT_STATUS_NAME.get(obj.status, ""),
            message=f"已提交学院初审，项目编号：{obj.project_no}"
        )

    @staticmethod
    def withdraw(db: Session, project_id: int, operator: SysUser) -> None:
        """学生/负责人撤回项目（状态->草稿）"""
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        if operator.role == RoleEnum.STUDENT and obj.leader_id != operator.id:
            raise PermissionDeniedException(message="仅负责人可撤回")
        if obj.status not in (PROJECT_STATUS_PENDING_COLLEGE, 2, 3):
            raise ParamValidateException(message="仅待审核/学院通过状态可撤回")
        obj.status = PROJECT_STATUS_DRAFT
        db.commit()

    @staticmethod
    def delete(db: Session, project_id: int, operator: SysUser) -> None:
        """软删除项目（仅草稿或管理员）"""
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        if operator.role != RoleEnum.ADMIN:
            if obj.status != PROJECT_STATUS_DRAFT:
                raise PermissionDeniedException(message="仅草稿状态可删除，其他状态请联系管理员")
            if obj.leader_id != operator.id:
                raise PermissionDeniedException(message="仅负责人可删除草稿")
        obj.is_deleted = 1
        db.commit()

    # ========== 统计分析 ==========
    @staticmethod
    def statistics_overview(db: Session, data_scope: DataScope,
                            college_id: Optional[int] = None,
                            project_type: Optional[int] = None,
                            start_year: Optional[int] = None,
                            end_year: Optional[int] = None,
                            ) -> ProjectStatisticsResponse:
        """项目概览统计（支持按学院/类型/立项年份过滤）"""
        from app.models import ProjProject
        q = db.query(func.count(ProjProject.id)).filter(ProjProject.is_deleted == 0)
        q_pending = q.filter(ProjProject.status.in_([1, 2, 3, 4, 5]))
        q_approved = q.filter(ProjProject.status.in_([6, 7, 8, 9]))
        q_finished = q.filter(ProjProject.status == 9)

        def apply_filters_and_scope(query):
            # 1) 用户前端 UI 显式选中的筛选条件
            if college_id is not None:
                query = query.filter(ProjProject.college_id == college_id)
            if project_type is not None:
                query = query.filter(ProjProject.project_type == project_type)
            if start_year is not None:
                # created_at 年份 >= start_year
                query = query.filter(extract("year", ProjProject.created_at) >= start_year)
            if end_year is not None:
                query = query.filter(extract("year", ProjProject.created_at) <= end_year)
            # 2) 角色数据权限范围
            if data_scope.scope.get("all"):
                return query
            if data_scope.scope.get("college_ids"):
                return query.filter(ProjProject.college_id.in_(data_scope.scope["college_ids"]))
            if data_scope.scope.get("is_student"):
                return query.filter(ProjProject.leader_id == data_scope.user_id)
            if data_scope.scope.get("teacher_user_ids"):
                return query.filter(ProjProject.teacher_id.in_(data_scope.scope["teacher_user_ids"]))
            return query

        total = apply_filters_and_scope(q.with_entities(func.count(ProjProject.id))).scalar() or 0
        pending = apply_filters_and_scope(q_pending.with_entities(func.count(ProjProject.id))).scalar() or 0
        approved = apply_filters_and_scope(q_approved.with_entities(func.count(ProjProject.id))).scalar() or 0
        finished = apply_filters_and_scope(q_finished.with_entities(func.count(ProjProject.id))).scalar() or 0
        total_budget = apply_filters_and_scope(db.query(func.coalesce(func.sum(ProjProject.budget_amount), 0))).scalar() or 0
        total_used = apply_filters_and_scope(db.query(func.coalesce(func.sum(ProjProject.used_amount), 0))).scalar() or 0

        rate = 0.0
        # 立项率：在相同过滤范围下，已立项及以上 / (已立项及以上 + 已驳回)
        denied = apply_filters_and_scope(db.query(func.count(ProjProject.id))
                                         .filter(ProjProject.status == 10)).scalar() or 0
        rate = round((approved / (approved + denied) * 100.0), 2) if (approved + denied) > 0 else 0.0

        return ProjectStatisticsResponse(
            total_projects=total,
            pending_review=pending,
            approved_projects=approved,
            finished_projects=finished,
            total_budget=Decimal(str(total_budget)),
            total_used=Decimal(str(total_used)),
            approval_rate=rate,
        )

    @staticmethod
    def trend_by_month(db: Session, start_year: int, end_year: int,
                       data_scope: DataScope) -> List[StatisticsTrendItem]:
        """按月统计申报/立项趋势（ECharts适配）"""
        from app.models import ProjProject
        q = db.query(
            extract("year", ProjProject.created_at).label("y"),
            extract("month", ProjProject.created_at).label("m"),
            func.count(ProjProject.id).label("apply_count"),
            func.sum(func.IF(ProjProject.status.in_([6, 7, 8, 9]), 1, 0)).label("approved_count"),
        ).filter(
            ProjProject.is_deleted == 0,
            extract("year", ProjProject.created_at).between(start_year, end_year),
        )
        if not data_scope.scope.get("all"):
            if data_scope.scope.get("college_ids"):
                q = q.filter(ProjProject.college_id.in_(data_scope.scope["college_ids"]))
            elif data_scope.scope.get("is_student"):
                q = q.filter(ProjProject.leader_id == data_scope.user_id)
        q = q.group_by("y", "m").order_by("y", "m")
        rows = q.all()
        return [
            StatisticsTrendItem(
                period=f"{int(r.y):04d}-{int(r.m):02d}",
                apply_count=int(r.apply_count or 0),
                approved_count=int(r.approved_count or 0),
            )
            for r in rows
        ]


class AchievementService:
    """项目成果业务服务"""

    @staticmethod
    def list_by_project(db: Session, project_id: int, operator: SysUser) -> List[AchievementResponse]:
        obj = ProjectCRUD.get_by_id(db, project_id)
        if not obj:
            raise ResourceNotFoundException(message="项目不存在")
        # 简化：登录用户可查看项目下成果；严格场景应复用项目详情权限
        items = AchievementCRUD.list_by_project(db, project_id)
        return [AchievementResponse.model_validate(i) for i in items]

    @staticmethod
    def create(db: Session, req: AchievementCreate, operator: SysUser) -> AchievementResponse:
        obj = ProjectCRUD.get_by_id(db, req.project_id)
        if not obj:
            raise ResourceNotFoundException(message="所属项目不存在")
        if operator.role not in (RoleEnum.ADMIN, RoleEnum.TEACHER) and obj.leader_id != operator.id:
            raise PermissionDeniedException(message="仅负责人、指导教师或管理员可登记成果")
        ach = AchievementCRUD.create(db, req.model_dump())
        db.commit()
        db.refresh(ach)
        return AchievementResponse.model_validate(ach)

    @staticmethod
    def delete(db: Session, pk: int, operator: SysUser) -> None:
        from app.models import ProjAchievement
        ach = db.query(ProjAchievement).filter(ProjAchievement.id == pk).first()
        if not ach:
            raise ResourceNotFoundException(message="成果不存在")
        if operator.role != RoleEnum.ADMIN:
            obj = ProjectCRUD.get_by_id(db, ach.project_id)
            if obj and obj.leader_id != operator.id:
                raise PermissionDeniedException(message="仅负责人或管理员可删除成果")
        ach.is_deleted = 1
        db.commit()
