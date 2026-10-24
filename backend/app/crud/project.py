"""
项目申报与审核 数据访问层(CRUD)

职责：
    封装项目主表（proj_project）及其从属表（团队成员、预算、成果）的查询与写入，
    并把 DataScope（角色 + 学院 + 本人）翻译成 SQL 过滤条件。

调用方：
    app/services/project_service.py、review_service.py 等业务服务；
    路由层不直接使用本类，统一经服务层转调，便于事务控制。

关键设计：
    - 所有查询默认带 is_deleted == 0，软删除行对业务完全不可见；
    - 列表查询用 outer join 关联负责人/教师/学院，避免内连接把「未指定指导教师」的项目漏掉；
    - 详情查询用 joinedload 预加载关联对象，防止序列化阶段反复查库（N+1）；
    - 排序字段走白名单，避免前端传来的 order_by 直接拼进 SQL。
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
    """项目主表 CRUD。

    仅负责数据访问：不做业务状态机判断（如「草稿才能提交」），
    状态流转与权限校验由 service 层完成，本类只保证 SQL 条件正确。
    """

    PROJECT_TYPE_NAME = {1: "创新训练", 2: "创业训练", 3: "创业实践"}
    PROJECT_LEVEL_NAME = {1: "院级", 2: "校级", 3: "省级", 4: "国家级"}
    # 状态名称统一引用 schemas 中的定义，避免多处漂移（含状态 12 待指导教师确认）
    STATUS_NAME = PROJECT_STATUS_NAME

    # ========== 查询 ==========
    @staticmethod
    def get_by_id(db: Session, project_id: int) -> Optional[ProjProject]:
        """按主键取项目详情，并预加载详情页需要的关联数据。

        :param db: 当前请求的数据库会话（事务由调用方提交/回滚）
        :param project_id: 项目主键
        :return: 项目对象；不存在或已软删除时返回 None
        :side effect: 只读，不修改会话状态

        使用 joinedload 一次性把团队成员、预算、负责人、指导教师取出：
        详情接口随后要序列化这些对象，若延迟加载会在循环里逐条查库（N+1）。
        """
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
        """分页查询项目列表，并在 SQL 层完成数据权限过滤。

        :param offset: 跳过条数（由 PaginationParams 计算，已做上限保护）
        :param limit: 本页条数
        :param keyword: 关键字，匹配项目名/编号/简介/负责人姓名/教师姓名/成果标题
        :param project_type: 项目类型 1创新训练/2创业训练/3创业实践
        :param project_level: 项目级别 1院级/2校级/3省级/4国家级
        :param college_id: 指定学院（学院管理员通常由 DataScope 注入，而非前端传参）
        :param leader_id: 指定负责人
        :param teacher_id: 指定指导教师
        :param status: 精确状态；status_in: 状态集合（用于「待办」「归档」等多状态页签）
        :param start_year/end_year: 按创建年份区间过滤（统计/归档按届查看）
        :param data_scope: 行级权限；为空表示调用方已自行保证范围（如内部任务）
        :param order_by: 排序字段，仅白名单内生效，其余回退 created_at
        :param order_dir: desc / asc
        :return: (当前页项目列表, 满足条件的总条数)，总数与分页使用同一套过滤条件

        :side effect: 只读。负责人/教师/学院 join 用于关键字检索与排序展示，
        故用 outer join；若改成 inner join，未指定指导教师的项目会被整批漏掉。
        """
        # 同一张 sys_user 表要同时关联负责人和教师，必须起别名，
        # 否则两个 join 会指向同一张表、条件互相覆盖。
        LeaderUser = aliased(SysUser)
        TeacherUser = aliased(SysUser)
        # 列表永远排除软删除行
        q = db.query(ProjProject).join(
            LeaderUser, LeaderUser.id == ProjProject.leader_id, isouter=True
        ).join(
            TeacherUser, TeacherUser.id == ProjProject.teacher_id, isouter=True
        ).join(
            SysCollege, SysCollege.id == ProjProject.college_id, isouter=True
        ).filter(ProjProject.is_deleted == 0)

        # ---- 数据权限 ----
        # DataScope.scope 由 core/deps.py 按角色计算：
        # all=True 为超管（role=4 且无学院），直接跳过所有行级过滤。
        if data_scope and not data_scope.scope.get("all"):
            scope = data_scope.scope
            # 学生：本人是负责人 OR 是团队成员
            # 团队成员关系不在 proj_project 上，先取 project_id 列表再 IN；
            # 空列表时用 False 生成恒假条件，避免 IN () 的语法歧义。
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
            # 两个条件取并集，因此用 or_ 而非连续 filter（连续 filter 是 AND）。
            elif scope.get("teacher_user_ids"):
                t_ids = scope["teacher_user_ids"]
                conds = []
                if t_ids:
                    conds.append(ProjProject.teacher_id.in_(t_ids))
                if scope.get("college_ids"):
                    conds.append(ProjProject.college_id.in_(scope["college_ids"]))
                if conds:
                    q = q.filter(or_(*conds))
            # 学院维度：学院管理员（role=4 且带 college_id）只看本院数据
            elif scope.get("college_ids"):
                q = q.filter(ProjProject.college_id.in_(scope["college_ids"]))
            # 专家：有有效专家评审记录的项目（已取消分配的记录不再授予可见性）
            # 专家与项目是多对多关系，只能经 proj_review 反查；
            # review_stage=3 表示专家评审阶段，is_deleted=0 排除被撤销的分配。
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
        # 原因：草稿是学生未提交的半成品，管理端/评审端不应看到未申报数据。
        if data_scope and data_scope.role != 1:
            q = q.filter(ProjProject.status != 0)

        # ---- 已驳回项目不在管理员项目列表中展示 ----
        # 管理员管理页只关注在办项目；已驳回项目由学生修改重提、指导教师继续指导
        if data_scope and data_scope.role == 4:
            q = q.filter(ProjProject.status != 10)

        # ---- 筛选 ----
        if keyword:
            # 两侧都补 %，即 contains 语义；MySQL 下 like 对大小写不敏感。
            kw = f"%{keyword}%"
            # 成果标题也纳入关键词检索（归档页标注支持按「成果」搜索）
            # 用子查询而非 join，避免一个项目有多条成果时把主查询行数放大、
            # 导致分页条数重复（count 虽用 distinct，但分页数据会重复）。
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
        # 以下为精确等值筛选，均先判 None：0 是合法枚举值（草稿），不能用真值判断。
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
        # 年份用 SQL 的 extract 下推到数据库，避免把 created_at 取回 Python 再过滤；
        # 缺点是无法命中 created_at 索引（函数索引除外），仅用于统计/归档等低频查询。
        if start_year:
            q = q.filter(extract("year", ProjProject.created_at) >= start_year)
        if end_year:
            q = q.filter(extract("year", ProjProject.created_at) <= end_year)

        # 先算总数再取当页数据：同一 q 对象追加 order/offset/limit 会影响 count，
        # 因此 count 在排序分页之前执行；distinct 防止 join 产生重复行时总数虚高。
        total = q.with_entities(func.count(func.distinct(ProjProject.id))).scalar() or 0

        # 排序字段白名单：getattr 只能取到模型列，杜绝 SQL 注入；
        # 非法字段静默回退 created_at，保证接口不因前端乱传参数而 500。
        allowed_orders = {"id", "project_name", "project_type", "project_level",
                          "status", "created_at", "updated_at", "submit_time", "budget_amount"}
        order_col = getattr(ProjProject, order_by) if order_by in allowed_orders else ProjProject.created_at
        order_expr = order_col.desc() if order_dir == "desc" else order_col.asc()
        # 列表展示需要负责人/教师姓名，这里再次 joinedload，
        # 让一页 N 条项目的关联用户随主查询一起取出，避免逐行懒加载（N+1）。
        items = q.options(
            joinedload(ProjProject.leader),
            joinedload(ProjProject.teacher),
        ).order_by(order_expr).offset(offset).limit(limit).all()
        return items, total

    # ========== 增 / 改 ==========
    @staticmethod
    def create(db: Session, data: Dict[str, Any]) -> ProjProject:
        """新建项目，并同步写入团队成员与预算明细。

        :param data: 已通过 schema 校验的项目字段；其中 team_members / budgets
                     为嵌套列表，attachment_ids 由附件服务单独处理
        :return: 已 flush（拿到主键）但未 commit 的项目对象
        :side effect: 会修改传入的 data（pop 掉嵌套字段与 attachment_ids），
                      调用方不应复用该字典

        先 add + flush 拿到 project_id，再写子表；预算总额由明细累加后回填，
        保证列表页的 budget_amount 与明细一致。
        """
        # 嵌套数据与附件不落本项目表，先摘除，剩余字段才能直接展开为模型参数。
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
        """更新项目字段，并按需替换团队成员、增量维护预算明细。

        :param obj: 已加载且通过权限校验的项目对象
        :param data: 待更新字段；team_members / budgets 为 None 表示「不改动」
        :return: 已 flush 的项目对象
        :side effect: 会 pop 传入的 data；子表增删改都在当前事务内完成，
                      由调用方统一 commit / rollback

        注意：团队成员是整表替换，预算则是「按科目就地更新」，
        两者策略不同，原因见下方预算处理处的注释。
        """
        team_members_data = data.pop("team_members", None)
        budgets_data = data.pop("budgets", None)
        # 允许显式置空的字段：调用方传入 None 时清空；
        # 其余字段传 None 视为未填写，跳过以免触发非空约束。
        # 这份白名单对应业务上「可以没有」的可选字段（教师、竞赛、日期、驳回原因等）。
        nullable_fields = {
            "teacher_id", "competition_id", "competition_session",
            "start_date", "end_date", "project_summary",
            "innovation_points", "expected_results", "reject_reason",
        }
        # hasattr + 排除 id：防止外部字典带入未定义属性或改写主键。
        for f, v in data.items():
            if hasattr(obj, f) and f != "id" and (v is not None or f in nullable_fields):
                setattr(obj, f, v)
        # 替换团队成员
        # 成员没有外部引用（报销/评审都不外键指向成员行），因此可以安全地删旧建新；
        # synchronize_session=False 表示不走 ORM 身份映射同步，靠 flush 后重新查询取新值。
        if team_members_data is not None:
            db.query(ProjTeamMember).filter(ProjTeamMember.project_id == obj.id).delete(
                synchronize_session=False
            )
            for tm in team_members_data:
                db.add(ProjTeamMember(project_id=obj.id, **tm))
        # 更新预算：同名科目就地更新（保留行 id 与已使用金额），新科目新增，消失科目删除。
        # 原实现"整表删除重建"会重置 used_amount 并使报销单 budget_item_id 悬空。
        # existing 以「科目名 -> 行列表」建索引，支持同名科目出现多行时按顺序取用。
        if budgets_data is not None:
            existing: Dict[str, List[ProjBudget]] = {}
            for b in db.query(ProjBudget).filter(ProjBudget.project_id == obj.id).all():
                existing.setdefault(b.budget_item, []).append(b)
            total_budget = Decimal("0")
            leftover: List[ProjBudget] = []
            for bg in budgets_data:
                total_budget += Decimal(str(bg.get("budget_amount") or 0))
                rows = existing.get(bg.get("budget_item")) or []
                if rows:
                    # 命中已有科目：只改金额与备注，保留 used_amount 及行主键
                    b = rows.pop(0)
                    b.budget_amount = bg.get("budget_amount") or 0
                    b.remark = bg.get("remark")
                else:
                    db.add(ProjBudget(project_id=obj.id, **bg))
            # 提交后仍未被消费的行，说明前端删除了该科目
            for rows in existing.values():
                for b in rows:
                    leftover.append(b)
            # 被历史报销单引用的科目不能物理删除（否则 ProjExpense.budget_item_id 悬空），
            # 保留行并清空预算金额；未被引用的科目正常删除。
            # 这里只查 budget_item_id 一列，避免把报销单整行加载进会话。
            leftover_ids = [b.id for b in leftover]
            referenced_ids = set()
            if leftover_ids:
                referenced_ids = {
                    bid for (bid,) in db.query(ProjExpense.budget_item_id)
                    .filter(ProjExpense.budget_item_id.in_(leftover_ids))
                    .all()
                }
            for b in leftover:
                if b.id in referenced_ids:
                    b.budget_amount = 0
                else:
                    db.delete(b)
            obj.budget_amount = total_budget
        db.flush()
        return obj

    @staticmethod
    def generate_project_no(db: Session, year: int) -> str:
        """生成项目编号：IE{year}{6位自增序号}
        基于当年最大编号 +1；并发写入可能撞唯一键，调用方需配合重试（见 bump_project_no）

        :param year: 项目届别年份，直接拼在前缀里，保证编号跨年可读
        :return: 形如 IE2026000001 的编号字符串
        :side effect: 只读。注意「查询最大值 + 1」不是原子操作，
                      高并发下两个请求可能拿到同一编号，唯一索引会拦截其中一个，
                      因此调用方需要捕获冲突后用 bump_project_no 递增重试。
        """
        prefix = f"IE{year}"
        # 只统计同一年份前缀的编号；like 前缀匹配可利用 project_no 上的索引。
        max_no = db.query(func.max(ProjProject.project_no)).filter(
            ProjProject.project_no.like(f"{prefix}%")
        ).scalar()
        seq = 1
        # 编号长度不足（历史脏数据）或末 6 位非数字时，从 1 重新开始，避免抛异常。
        if max_no and len(max_no) >= len(prefix) + 6:
            try:
                seq = int(max_no[-6:]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}{seq:06d}"

    @staticmethod
    def bump_project_no(project_no: str, step: int = 1) -> str:
        """把项目编号末尾 6 位序号 +step，用于唯一键冲突后的重试

        :param project_no: 冲突的旧编号
        :param step: 本次要跳过的序号个数，重试次数越多可传越大以减少再次碰撞
        :return: 新编号；末 6 位无法解析时原样返回，交由调用方判断是否继续重试
        """
        prefix, seq = project_no[:-6], project_no[-6:]
        try:
            return f"{prefix}{int(seq) + step:06d}"
        except ValueError:
            return project_no


class AchievementCRUD:
    """项目成果 CRUD。

    成果是项目的从属数据，随项目一起做权限校验；
    本类只保证按项目查询、软删除，不负责附件与版本管理。
    """

    @staticmethod
    def list_by_project(db: Session, project_id: int) -> List[ProjAchievement]:
        """列出某项目下未删除的成果，按创建时间倒序（新成果优先展示）。

        :param project_id: 项目主键；调用方需已校验当前用户对该项目的可见性
        :return: 成果列表，无数据时返回空列表
        """
        return db.query(ProjAchievement).filter(
            ProjAchievement.project_id == project_id,
            ProjAchievement.is_deleted == 0
        ).order_by(ProjAchievement.created_at.desc()).all()

    @staticmethod
    def create(db: Session, data: Dict[str, Any]) -> ProjAchievement:
        """新增成果记录。

        :param data: 已校验的成果字段（project_id、title 等）
        :return: 已 flush、含主键的成果对象
        """
        obj = ProjAchievement(**data)
        db.add(obj)
        db.flush()
        return obj

    @staticmethod
    def delete(db: Session, pk: int) -> int:
        """软删除成果（置 is_deleted=1），保留历史数据以便审计与恢复。

        :param pk: 成果主键
        :return: 受影响行数；0 表示记录不存在或已删除
        :side effect: 批量 update 直接在数据库执行，会话中的旧对象可能仍是旧值，
                      调用方如需读取请先 expire/refresh。
        """
        rows = db.query(ProjAchievement).filter(
            ProjAchievement.id == pk, ProjAchievement.is_deleted == 0
        ).update({"is_deleted": 1}, synchronize_session=False)
        db.flush()
        return rows
