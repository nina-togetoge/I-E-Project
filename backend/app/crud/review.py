"""
项目审核模块 数据访问层(CRUD)

职责：
    封装 proj_review（学院初审/校级复审/专家评审/结题验收）、
    proj_midterm_check（中期检查）与 proj_change_request（变更延期）的查询与写入。

调用方：
    app/services/review_service.py、project_service.py 等业务服务，路由层不直接调用。

关键设计：
    - review_result=99 是「仅分配、未出结果」的占位记录，统计票数与判定「已评审」
      时必须显式排除（REVIEW_RESULT_PENDING），否则会出现「已评审但无分数」的错判；
    - 专家待办与已评审两个列表共用同一组子查询，且条件互为取反，保证同一项目
      不会同时出现在两个列表；
    - 审核、中期、变更记录均做软删除过滤（is_deleted=0）。
"""
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ProjReview, ProjProject, SysUser, ProjMidtermCheck, ProjChangeRequest,
)
from app.schemas.review import REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL

REVIEW_RESULT_PENDING = 99  # 仅分配、尚未出结果的占位记录


class ReviewCRUD:
    """审核记录 CRUD。

    一条记录 = 某项目在某阶段由某评审人给出（或待给出）的一次意见；
    同一阶段允许多位评审人各一条，票数统计需自行按 review_result 汇总。
    """

    @staticmethod
    def create(db: Session, data: Dict[str, Any]) -> ProjReview:
        """新增审核记录（正式意见或分配占位记录均走这里）。

        :param data: 审核字段；review_result 传 99 即占位记录
        :return: 已 flush、含主键的记录
        :side effect: 不校验重复；重复分配由调用方结合 exist_* 方法先行判断。
        """
        obj = ProjReview(**data)
        db.add(obj)
        db.flush()
        return obj

    @staticmethod
    def list_by_project(db: Session, project_id: int) -> List[ProjReview]:
        """列出某项目的全部有效审核记录，按阶段、评审时间升序。

        :param project_id: 项目主键
        :return: 记录列表；被软删除（如撤销分配）的记录不返回
        :side effect: 只读。排序先阶段后时间，便于详情页按 初审→复审→专家→结题
                      的时间线顺序展示；同一阶段内按评审时间保留先后。
        """
        return db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.is_deleted == 0,
        ).order_by(ProjReview.review_stage.asc(), ProjReview.review_time.asc()).all()

    @staticmethod
    def exist_by_project_stage_reviewer(db: Session, project_id: int, stage: int, reviewer_id: int) -> bool:
        """判断某阶段某评审人是否已有审核记录（含占位记录）

        用于分配去重：只要已分配过（哪怕还没打分）就不再重复插入，
        避免同一专家对同一项目出现多条待办。
        :return: 存在返回 True
        """
        # 只查 id 列并 first()，不加载整行，存在性判断开销最小。
        return db.query(ProjReview.id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == stage,
            ProjReview.reviewer_id == reviewer_id,
            ProjReview.is_deleted == 0,
        ).first() is not None

    @staticmethod
    def exist_real_review(db: Session, project_id: int, stage: int, reviewer_id: int) -> bool:
        """判断某阶段某评审人是否已正式评审过（排除占位记录 review_result=99）

        与 exist_by_project_stage_reviewer 的区别：本方法回答「是否已打分」，
        前者回答「是否已分配」。结题/评审进度判断必须用本方法。
        :return: 已出结果返回 True
        """
        return db.query(ProjReview.id).filter(
            ProjReview.project_id == project_id,
            ProjReview.review_stage == stage,
            ProjReview.reviewer_id == reviewer_id,
            ProjReview.review_result != 99,
            ProjReview.is_deleted == 0,
        ).first() is not None

    @staticmethod
    def paginate(
        db: Session, offset: int, limit: int,
        stage: Optional[int] = None, status: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> Tuple[List[ProjReview], int]:
        """分页查询审核记录（管理端审核流水页使用）。

        :param stage: 审核阶段；0 不是合法阶段，故用真值判断
        :param status: review_result 精确值。这里允许传 99 ，
                       管理端如需查看「未出结果」的分配记录可显式筛选
        :param keyword: 匹配项目名称或项目编号（需 join 项目表）
        :return: (当前页记录, 总数)
        :side effect: 只读。keyword 存在时才 join 项目表，避免无谓的连接开销。
        """
        # 审核记录可能因撤销分配被软删除，列表必须排除。
        q = db.query(ProjReview).filter(ProjReview.is_deleted == 0)
        if stage:
            q = q.filter(ProjReview.review_stage == stage)
        # status 用 is not None：review_result=0 也是合法值，不能按真值判断。
        if status is not None:
            q = q.filter(ProjReview.review_result == status)
        if keyword:
            # 项目名/编号不在审核表上，需 join；这里用 inner join，
            # 因为能匹配关键字的记录必然存在对应项目。
            kw = f"%{keyword}%"
            q = q.join(ProjProject, ProjReview.project_id == ProjProject.id).filter(
                or_(ProjProject.project_name.like(kw), ProjProject.project_no.like(kw))
            )
        # count 与列表使用同一过滤条件；若 join 导致重复（理论上不会）可再加 distinct。
        total = q.with_entities(func.count(ProjReview.id)).scalar() or 0
        # 审核流水按创建时间倒序，最新操作排在最前。
        items = q.order_by(ProjReview.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def _expert_stage_subqueries(db: Session, expert_id: int):
        """专家相关的项目ID子查询，供"待评审"与"已评审"两个列表共用，
        以保证两者口径一致，避免同一项目同时出现在两个列表。

        返回 (assigned, expert_scored, final_scored)：
          - assigned：该专家被分配的项目（stage=3 存在记录）
          - expert_scored：该专家本人已出专家评审结果（排除 result=99 占位）
          - final_scored：该专家本人已出结题验收结果（排除 result=99 占位）

        :side effect: 只读；返回的是 Query 对象而非结果集，可被外层 in_/not in 复用，
                      避免为三个判断各写一遍 SQL（也保证三处口径完全一致）。
        """
        # 分配记录：不管是否已打分都要取，用于限定「该专家可见的项目集合」。
        assigned_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.is_deleted == 0,
        ).distinct()
        # 已打分：排除 99 占位，否则刚分配就被当成「已评审」。
        expert_scored_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == REVIEW_STAGE_EXPERT,
            ProjReview.review_result != REVIEW_RESULT_PENDING,
            ProjReview.is_deleted == 0,
        ).distinct()
        # 结题验收同理；阶段不同，不能与专家评审结果混用。
        final_scored_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == REVIEW_STAGE_FINAL,
            ProjReview.review_result != REVIEW_RESULT_PENDING,
            ProjReview.is_deleted == 0,
        ).distinct()
        return assigned_q, expert_scored_q, final_scored_q

    @staticmethod
    def _expert_still_pending_clause(expert_scored_q, final_scored_q):
        """该专家仍待操作的项目条件（待专家评审未打分 / 待结题未验收），
        待办列表取它、已评审列表取它的取反，两者互斥。

        :side effect: 只读，返回 SQLAlchemy 条件表达式，供外层 filter/取反使用。
        """
        return or_(
            # 待专家评审(5)：仅当该专家本人尚未打分时才算待办
            # 用 ~in_ 生成 NOT IN：只要本人出过结果，项目就不再挂在他的待办里，
            # 但其他专家未打分不影响本项目对他的判定，因此按 reviewer_id 隔离。
            and_(ProjProject.status == 5, ~ProjProject.id.in_(expert_scored_q)),
            # 待结题(8)：仅当该专家本人尚未提交结题验收时才算待办
            and_(ProjProject.status == 8, ~ProjProject.id.in_(final_scored_q)),
        )

    @staticmethod
    def expert_pending_projects(db: Session, expert_id: int, offset: int, limit: int,
                                keyword: Optional[str] = None) -> Tuple[List[ProjProject], int]:
        """
        查询专家"待办"项目列表：
        规则：该专家已被分配(proj_review.stage=3, reviewer_id=expert_id)，
              且项目当前仍处于需要该专家操作的阶段：
                - 待专家评审(5)：需打分评审
                - 待结题(8)：需结题验收
        说明：已立项(6)/中期(7)/已结题(9)/驳回(10)等已决项目不再进入该列表，
              否则专家端会出现"有行但无操作按钮"的空按钮行。

        :param keyword: 项目名/编号模糊匹配，仅作用于本专家待办范围
        :return: (当前页项目, 总数)
        :side effect: 只读。三个子查询都是「本人维度」，不会泄露其他专家的评审情况。
        """
        # 复用子查询保证与 expert_reviewed_projects 口径一致（互斥）。
        assigned_q, expert_scored_q, final_scored_q = ReviewCRUD._expert_stage_subqueries(db, expert_id)
        q = db.query(ProjProject).filter(
            # 排除已删除项目；且必须先被分配给该专家
            ProjProject.is_deleted == 0,
            ProjProject.id.in_(assigned_q),
            ReviewCRUD._expert_still_pending_clause(expert_scored_q, final_scored_q),
        )
        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(or_(
                ProjProject.project_name.like(kw),
                ProjProject.project_no.like(kw),
            ))
        total = q.with_entities(func.count(ProjProject.id)).scalar() or 0
        # 按提交时间倒序：新提交的项目优先处理；未提交时间为空的项目排在后面。
        items = q.order_by(ProjProject.submit_time.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def expert_reviewed_projects(db: Session, expert_id: int, offset: int, limit: int,
                                 keyword: Optional[str] = None) -> Tuple[List[ProjProject], int]:
        """
        查询专家"已评审"历史项目列表（与待办列表互斥，供回看）：
        规则：该专家本人已对项目出过结果记录（专家评审已打分 / 结题验收已提交），
              且项目当前不再需要该专家操作。
        说明：用 _expert_still_pending_clause 取反，确保仍待该专家打分或结题验收的
              项目只出现在"待评审"列表，不会同时出现在"已评审"里。
        不限制项目当前状态，因此已立项/已结题/被驳回的历史项目均可回看。

        :param keyword: 项目名/编号模糊匹配
        :return: (当前页项目, 总数)
        :side effect: 只读。
        """
        _, expert_scored_q, final_scored_q = ReviewCRUD._expert_stage_subqueries(db, expert_id)
        # 历史范围：两个阶段中任一已出结果即可（此处不区分是评审还是结题）。
        reviewed_q = db.query(ProjReview.project_id).filter(
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage.in_((REVIEW_STAGE_EXPERT, REVIEW_STAGE_FINAL)),
            ProjReview.review_result != REVIEW_RESULT_PENDING,
            ProjReview.is_deleted == 0,
        ).distinct()
        q = db.query(ProjProject).filter(
            ProjProject.is_deleted == 0,
            ProjProject.id.in_(reviewed_q),
            # 取反：排除仍待本人操作的项目，保证与待办列表无交集。
            ~ReviewCRUD._expert_still_pending_clause(expert_scored_q, final_scored_q),
        )
        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(or_(
                ProjProject.project_name.like(kw),
                ProjProject.project_no.like(kw),
            ))
        total = q.with_entities(func.count(ProjProject.id)).scalar() or 0
        items = q.order_by(ProjProject.submit_time.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def get_expert_score(db: Session, project_id: int, expert_id: int) -> Optional[ProjReview]:
        """取某专家对某项目的专家评审记录（可能仍是 99 占位记录）。

        :return: 记录或 None；调用方需自行判断 review_result 是否仍为 99
        :side effect: 只读。这里硬编码 stage=3（专家评审），结题验收需另行查询。
        """
        return db.query(ProjReview).filter(
            ProjReview.project_id == project_id,
            ProjReview.reviewer_id == expert_id,
            ProjReview.review_stage == 3,
            ProjReview.is_deleted == 0,
        ).first()


class MidtermCRUD:
    """中期检查 CRUD。

    一个项目原则上只有一份有效中期检查记录，因此提供 create_or_update 幂等写入。
    """

    @staticmethod
    def get_by_project(db: Session, project_id: int) -> Optional[ProjMidtermCheck]:
        """按项目取中期检查记录（单一记录语义）。

        :return: 记录或 None；已软删除的记录不返回
        """
        return db.query(ProjMidtermCheck).filter(
            ProjMidtermCheck.project_id == project_id,
            ProjMidtermCheck.is_deleted == 0,
        ).first()

    @staticmethod
    def get_by_id(db: Session, pk: int) -> Optional[ProjMidtermCheck]:
        """按主键取中期检查记录，用于详情/审核页回显。"""
        return db.query(ProjMidtermCheck).filter(
            ProjMidtermCheck.id == pk, ProjMidtermCheck.is_deleted == 0
        ).first()

    @staticmethod
    def create_or_update(db: Session, data: Dict[str, Any]) -> ProjMidtermCheck:
        """按 project_id 幂等写入中期检查：存在则更新，不存在则新建。

        :param data: 必须含 project_id；其余为检查内容字段
        :return: 新增或更新后的记录
        :side effect: 更新时只覆盖非 None 字段，保留未提交的旧内容；
                      因此调用方无法通过本方法把字段清空。
        """
        obj = MidtermCRUD.get_by_project(db, data["project_id"])
        if obj:
            for f, v in data.items():
                if v is not None and hasattr(obj, f):
                    setattr(obj, f, v)
            db.flush()
            return obj
        obj = ProjMidtermCheck(**data)
        db.add(obj)
        db.flush()
        return obj


class ChangeCRUD:
    """变更/延期申请 CRUD。

    变更申请随项目走权限：调用方先算好「当前用户可见的项目 ID 列表」，
    再作为 project_ids 传入，本类不直接依赖 DataScope，便于复用。
    """

    @staticmethod
    def create(db: Session, data: Dict[str, Any]) -> ProjChangeRequest:
        """新建变更/延期申请，初始状态由调用方指定（通常为待审核）。"""
        obj = ProjChangeRequest(**data)
        db.add(obj)
        db.flush()
        return obj

    @staticmethod
    def paginate(
        db: Session, offset: int, limit: int,
        project_id: Optional[int] = None, change_type: Optional[int] = None,
        status: Optional[int] = None, applicant_id: Optional[int] = None,
        project_ids: Optional[List[int]] = None,
    ) -> Tuple[List[ProjChangeRequest], int]:
        """分页查询变更/延期申请。

        :param change_type: 变更类型（延期/成员变更等），0 非法故用真值判断
        :param status: 审核状态；0（待审核）是合法值，必须用 is not None
        :param project_ids: 数据权限产物。None 表示不限制（超管/内部调用）；
                            空列表表示当前用户没有任何可见项目，应直接返回空，
                            不能退化成「不加条件」而泄露全部数据。
        :return: (当前页申请, 总数)
        :side effect: 只读。
        """
        # 变更记录可被撤销，软删除行不参与展示与统计。
        q = db.query(ProjChangeRequest).filter(ProjChangeRequest.is_deleted == 0)
        if project_id:
            q = q.filter(ProjChangeRequest.project_id == project_id)
        if change_type:
            q = q.filter(ProjChangeRequest.change_type == change_type)
        if status is not None:
            q = q.filter(ProjChangeRequest.status == status)
        if applicant_id:
            q = q.filter(ProjChangeRequest.applicant_id == applicant_id)
        # 数据权限：按可见项目范围过滤（None=不限制；空列表=无可见项目）
        # 空列表提前返回，既省一次数据库往返，也避免 IN () 的语义歧义。
        if project_ids is not None:
            if len(project_ids) == 0:
                return [], 0
            q = q.filter(ProjChangeRequest.project_id.in_(project_ids))
        total = q.with_entities(func.count(ProjChangeRequest.id)).scalar() or 0
        # 申请按创建时间倒序，待处理的最新申请置顶。
        items = q.order_by(ProjChangeRequest.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def get_by_id(db: Session, pk: int) -> Optional[ProjChangeRequest]:
        """按主键取变更申请；已删除返回 None，调用方需另行做项目级权限校验。"""
        return db.query(ProjChangeRequest).filter(
            ProjChangeRequest.id == pk, ProjChangeRequest.is_deleted == 0
        ).first()
