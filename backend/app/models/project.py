# ====================================================================
# 项目业务域 ORM 模型（proj_* 前缀表）
# --------------------------------------------------------------------
# 覆盖创新创业项目从申报到结题的全生命周期：
#   proj_project          项目主表，status 状态机驱动流程（0草稿 ... 13待分配专家 ...）
#   proj_team_member      团队成员（冗余姓名/学号，保证历史快照稳定）
#   proj_review           各阶段审核记录（教师确认/学院/校级/专家/结题）
#   proj_budget           预算科目明细，与报销按科目核销
#   proj_expense          经费报销单，导师→学院→财务多级审批
#   proj_achievement      成果登记（论文/专利/竞赛获奖等）
#   proj_achievement_review 成果认定，一成果至多一条记录
#   proj_midterm_check    中期检查，一项目至多一条
#   proj_change_request   变更/延期申请，按阶段限制提交次数
# 数据生命周期：项目软删除（is_deleted）后保留审核与经费流水，报表按口径过滤。
# 关联主线：ProjProject 1:N ProjTeamMember / ProjReview / ProjBudget / ProjExpense /
#           ProjAchievement / ProjChangeRequest；1:1 ProjMidtermCheck。
# ====================================================================
"""
项目相关ORM模型
包含项目、团队成员、审核记录、预算、报销、成果、中期检查、变更申请等模型
"""
from datetime import datetime, date
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import Column, String, BigInteger, SmallInteger, DateTime, Integer, Text, ForeignKey, Index, Date, Numeric, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ProjProject(BaseModel):
    """
    创新创业项目主表（proj_project）

    业务含义：一个项目从学生申报到结题验收的唯一主档，所有团队成员、审核、
    预算、报销、成果、中期检查、变更申请都挂在它下面。
    关键约束：
      - project_no 唯一（uk_project_no），草稿期可为空，提交时生成；
      - college_id / leader_id 非空，决定数据权限归属（学院管理员只能看本院）；
      - status 为流程状态机，与 review_stage 配合推进，禁止跨阶段跳转。
    """
    __tablename__ = "proj_project"

    # 对外可展示的业务编号（如 S2026-001），唯一；草稿阶段允许为空
    project_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="项目编号")
    # 项目名称，列表检索与报表的主标题
    project_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="项目名称")
    # 项目类型: 1-创新训练 2-创业训练 3-创业实践（用于申报书字段差异化）
    project_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="项目类型")
    # 项目级别: 1-院级 2-校级 3-省级 4-国家级（与成果 level 的 1校级/2省级/3国家级 含义不同）
    project_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="项目级别")
    # 申报学院：数据权限隔离的关键维度，学院管理员按此过滤
    college_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_college.id"), nullable=False, comment="申报学院ID")
    # 项目负责人（学生），一个项目只能有一位，决定成员管理与提交权限
    leader_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=False, comment="项目负责人ID")
    # 指导教师：由负责人选择，需教师确认后才进入学院初审
    teacher_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True, comment="指导教师ID")
    # 参赛比赛：仅"参赛类"项目有值，为空表示普通大创项目
    competition_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("biz_competition.id"), nullable=True, comment="参赛比赛ID")
    # 冗余届次文案：比赛主数据改名/改届次后，历史项目仍显示申报时的届次
    competition_session: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="参赛比赛届次(冗余,如 2026届)")
    # 立项执行期起止，用于中期/结题的进度判断
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="立项开始日期")
    # 计划结束日期，延期申请即调整此值
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="计划结束日期")
    # 预算总额：由预算明细汇总而来，报销余额核算的基准
    budget_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="预算总额(元)"
    )
    # 已使用金额：报销审批通过后累加，与预算总额比较得到可用余额
    used_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="已使用金额(元)"
    )
    # 项目简介：申报书正文，详情页展示
    project_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="项目简介")
    # 创新点：专家评审分项打分与答辩材料引用
    innovation_points: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="创新点")
    # 预期成果：立项时承诺的成果清单，结题时用作验收对照
    expected_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="预期成果")
    # 项目状态机: 0-草稿 1-待学院初审 2-学院初审通过(瞬时) 3-待校级复审 4-校级复审通过(瞬时)
    # 5-待专家评审 13-待分配评审专家 6-已立项 7-中期检查 8-待结题 9-已结题 10-已驳回 11-已撤销 12-待指导教师确认
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="项目状态")
    # 正式提交时间：草稿转待审核时写入，用于统计申报时效
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="正式提交时间")
    # 最终立项审批时间：走到"已立项"时写入，是立项年份统计的依据
    approval_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最终立项审批时间")
    # 当前审批人：待办列表按此字段精确投递，避免全量扫描状态
    current_approver_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="当前审批人ID")
    # 驳回原因：最近一次驳回的意见快照，便于负责人修改时回看
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="驳回原因")

    # ========== 关联关系 ==========
    # 负责人（多对一）：与 SysUser.led_projects 双向绑定；foreign_keys 必填，
    # 因为本表同时有两个指向 sys_user 的外键（leader_id / teacher_id），不指定会猜错。
    leader: Mapped["SysUser"] = relationship(
        "SysUser",
        back_populates="led_projects",
        foreign_keys=[leader_id]
    )
    # 指导教师（多对一，可空）：同上需显式 foreign_keys 区分
    teacher: Mapped[Optional["SysUser"]] = relationship(
        "SysUser",
        back_populates="taught_projects",
        foreign_keys=[teacher_id]
    )
    # 团队成员（一对多）：cascade delete-orphan 表示移除子对象时物理删子行，
    # 用于前端"整体替换成员列表"的更新语义；项目自身仍是软删除。
    team_members: Mapped[List["ProjTeamMember"]] = relationship(
        "ProjTeamMember",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjTeamMember.project_id"
    )
    # 审核记录（一对多）：含专家分配占位记录（review_result=99），随项目一起级联清理
    reviews: Mapped[List["ProjReview"]] = relationship(
        "ProjReview",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjReview.project_id"
    )
    # 预算明细（一对多）：随项目整体替换，级联删除
    budgets: Mapped[List["ProjBudget"]] = relationship(
        "ProjBudget",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjBudget.project_id"
    )
    # 报销单（一对多）：不设级联删除，经费流水属于审计数据，必须长期保留
    expenses: Mapped[List["ProjExpense"]] = relationship(
        "ProjExpense",
        back_populates="project",
        foreign_keys="ProjExpense.project_id"
    )
    # 成果（一对多）：删除项目时成果一并清理，但成果附件在 sys_attachment 中另有记录
    achievements: Mapped[List["ProjAchievement"]] = relationship(
        "ProjAchievement",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjAchievement.project_id"
    )
    # 中期检查（一对一）：uselist=False 表示单个对象；库表有 uk_project 唯一约束兜底
    midterm_check: Mapped[Optional["ProjMidtermCheck"]] = relationship(
        "ProjMidtermCheck",
        back_populates="project",
        uselist=False,
        foreign_keys="ProjMidtermCheck.project_id"
    )
    # 变更/延期申请（一对多）：不级联删除，历史申请用于配额统计与追责
    change_requests: Mapped[List["ProjChangeRequest"]] = relationship(
        "ProjChangeRequest",
        back_populates="project",
        foreign_keys="ProjChangeRequest.project_id"
    )
    # 所属学院（多对一，只读）：viewonly 仅用于查询展示，不做写回，避免与 users 关系冲突
    college: Mapped[Optional["SysCollege"]] = relationship(
        "SysCollege",
        foreign_keys=[college_id],
        viewonly=True,
    )
    # 参赛比赛（多对一，只读）：同样 viewonly，仅用于回显比赛名称/届次
    competition: Mapped[Optional["Competition"]] = relationship(
        "Competition",
        foreign_keys=[competition_id],
        viewonly=True,
    )

    # 索引设计：唯一编号防重复；学院/负责人/教师/状态支撑权限过滤与待办查询；
    # (type, level) 组合索引支撑分类统计；competition_id 支撑按赛事聚合
    __table_args__ = (
        Index("uk_project_no", "project_no", unique=True),
        Index("idx_college", "college_id"),
        Index("idx_leader", "leader_id"),
        Index("idx_teacher", "teacher_id"),
        Index("idx_status", "status"),
        Index("idx_type_level", "project_type", "project_level"),
        Index("idx_competition", "competition_id"),
    )


class ProjTeamMember(BaseModel):
    """
    项目团队成员表（proj_team_member）

    业务含义：记录项目参与学生，含负责人以外的成员；成员数据在申报时点固化，
    便于证书发放与历史追溯。
    关键约束：(project_id, student_id) 唯一，同一学生不能重复加入同一项目。
    """
    __tablename__ = "proj_team_member"

    # 所属项目：团队列表按此字段整体查询/替换
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 学生用户ID：未建外键约束，保持成员快照不随用户删除失效
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="学生用户ID")
    # 成员姓名快照：用户改名后历史申报书仍保持原样
    student_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="学生姓名(冗余)")
    # 学号快照：证书与报表直接引用，避免联表
    student_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="学号(冗余)")
    # 专业/年级：申报书展示用，选题团队成员时可自动带出
    major: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="专业")
    grade: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="年级")
    # 团队角色（如 负责人/技术/财务），纯文本不强制枚举
    role_in_team: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="团队内角色")
    # 分工描述：评审时考察团队协作合理性
    task_desc: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="分工描述")
    # 加入时间：由数据库默认值填充，用于成员变更留痕
    join_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        comment="加入时间"
    )

    # 关联关系：多对一，反向由 ProjProject.team_members 维护
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="team_members")

    # 唯一约束防止成员重复；两个单列索引分别支撑按项目、按学生反查
    __table_args__ = (
        Index("uk_project_student", "project_id", "student_id", unique=True),
        Index("idx_project", "project_id"),
        Index("idx_student", "student_id"),
    )


class ProjReview(BaseModel):
    """
    项目审核记录表（proj_review）

    业务含义：留痕每一次审核动作，覆盖教师确认/学院/校级/专家/结题五个阶段，
    是审核流程回放与专家票数统计的唯一数据源。
    关键约束：同一项目同一阶段可有多条记录（多位专家各一条）；
    专家分配时写入 review_result=99 的占位记录，表示"已分配未评审"，
    占位记录不计入通过/驳回票数。
    """
    __tablename__ = "proj_review"

    # 被审核项目：流程详情页按项目聚合全部记录
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 审核阶段: 0-教师确认 1-学院初审 2-校级复审 3-专家评审 4-结题验收
    review_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="审核阶段")
    # 审核人：教师/学院管理员/校级管理员/专家，按阶段身份不同
    reviewer_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="审核人ID")
    # 审核人姓名快照：避免用户改名后历史记录失真
    reviewer_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="审核人姓名(冗余)")
    # 审核结果: 1-通过 2-驳回 3-修改后重提；99-已分配未评审占位（也存于本字段）
    review_result: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="审核结果")
    # 评分（百分制）：仅专家评审阶段有值，用于平均分与排名
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True, comment="评分(百分制)")
    # 分项评分：JSON 结构存创新性/可行性/团队/应用价值，便于前端雷达图
    dim_scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="分项评分明细(JSON:创新性/可行性/团队/应用价值)")
    # 评审意见：驳回时必填（由 Schema 层校验），通过时专家需≥10字
    review_comment: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, comment="评审意见")
    # 审核时间：默认当前时间，用于流程时效分析与审计
    review_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        comment="审核时间"
    )

    # 关联关系：多对一，反向由 ProjProject.reviews 维护
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="reviews")

    # idx_project_stage 支撑"某项目某阶段"的票数与占位查询（专家指派/评审汇总高频使用）
    __table_args__ = (
        Index("idx_project", "project_id"),
        Index("idx_reviewer", "reviewer_id"),
        Index("idx_stage", "review_stage"),
        Index("idx_project_stage", "project_id", "review_stage"),
    )


class ProjBudget(BaseModel):
    """
    项目预算明细表（proj_budget）

    业务含义：按科目拆解项目预算（设备费/材料费/差旅费等），
    报销单通过 budget_item_id 关联到具体科目并累计 used_amount。
    关键约束：同一项目下科目可自定义，无唯一约束，由业务层保证科目不重复。
    """
    __tablename__ = "proj_budget"

    # 所属项目：项目详情页按项目批量加载预算明细
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 预算科目名称，前端下拉/自定义输入
    budget_item: Mapped[str] = mapped_column(String(128), nullable=False, comment="预算科目")
    # 该科目预算金额：各科目之和应等于 ProjProject.budget_amount
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="预算金额")
    # 该科目已报销金额：报销审批通过后回写，用于科目余额校验
    used_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="已使用金额")
    # 备注：说明测算依据，评审时供专家参考
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="备注说明")

    # 关联关系：多对一，反向由 ProjProject.budgets 维护
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="budgets")

    # 按项目查询是最主要的访问路径
    __table_args__ = (
        Index("idx_project", "project_id"),
    )


class ProjExpense(BaseModel):
    """
    经费报销单表（proj_expense）

    业务含义：项目成员提交的经费报销申请，走"导师→学院→财务"三级审批；
    审批通过后累加 ProjProject.used_amount 与 ProjBudget.used_amount。
    关键约束：expense_no 唯一；金额必须大于 0（由 Schema 层校验）。
    数据生命周期：报销流水长期保留，不随项目软删除清理。
    """
    __tablename__ = "proj_expense"

    # 报销单号：对外唯一标识，提交时生成
    expense_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="报销单号")
    # 所属项目：报销必须挂在已立项项目下，余额按项目核算
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 申请人（项目成员）：决定"我的报销"列表可见范围
    applicant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="申请人ID")
    # 申请人姓名快照：列表直接展示，不做联表
    applicant_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="申请人姓名(冗余)")
    # 报销金额：必须 ≤ 该项目/科目剩余预算
    expense_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="报销金额")
    # 对应预算科目：可为空（未指定科目时只校验项目总额）
    budget_item_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="对应预算科目ID")
    # 费用说明：审批人判断合理性的核心依据
    expense_desc: Mapped[str] = mapped_column(String(500), nullable=False, comment="费用说明")
    # 发票号码：财务复核防重复报销，非强制
    invoice_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="发票号码")
    # 审批状态: 0-草稿 1-待导师审批 2-导师审批通过 3-待学院审批 4-学院审批通过 5-待财务审批 6-已完成 7-已驳回
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="审批状态")
    # 驳回原因：驳回后申请人可修改重提，需展示原因
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="驳回原因")
    # 提交时间 / 最终审批时间：用于流程时效统计
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="提交时间")
    approval_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最终审批时间")

    # 关联关系：多对一；未设置级联删除以保护审计数据
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="expenses")

    # 单号唯一；项目/申请人/状态索引支撑列表筛选与待办聚合
    __table_args__ = (
        Index("uk_expense_no", "expense_no", unique=True),
        Index("idx_project", "project_id"),
        Index("idx_applicant", "applicant_id"),
        Index("idx_status", "status"),
    )


class ProjAchievement(BaseModel):
    """
    项目成果表（proj_achievement）

    业务含义：登记项目产出的论文/专利/软著/竞赛获奖等成果，
    结题验收时按成果清单逐项核对；竞赛获奖成果还用于自动生成证书。
    关键约束：无唯一键，同一项目可登记多条；证明材料存于 sys_attachment。
    """
    __tablename__ = "proj_achievement"

    # 所属项目：成果必须挂在项目下，结题时按项目汇总
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 成果类型: 1-论文 2-专利 3-软件著作权 4-竞赛获奖 5-创业成果 6-其他
    achievement_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="成果类型")
    # 成果标题/名称：列表主字段
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="成果标题/名称")
    # 作者/发明人：文本记录，不做成员关联（校外合作者也可填）
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="作者/发明人")
    # 发表/授权日期：认定与统计的时间依据
    publish_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="发表/授权日期")
    # 发表刊物/授权机构
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="发表刊物/授权机构")
    # 成果编号（专利号/软著登记号/论文DOI等）
    achievement_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="编号")
    # 成果级别: 1-校级 2-省级 3-国家级（注意与项目 level 的 1院级/2校级/3省级/4国家级 不同）
    level: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True, comment="级别")
    # 获奖等级（一等奖/二等奖等），仅竞赛获奖类成果有值
    award_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="获奖等级")
    # 成果简介：认定专家阅读的补充说明
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="成果简介")

    # 关联关系：多对一，反向由 ProjProject.achievements 维护
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="achievements")

    # 按项目汇总成果、按类型筛选（如统计竞赛获奖数）
    __table_args__ = (
        Index("idx_project", "project_id"),
        Index("idx_type", "achievement_type"),
    )


class ProjAchievementReview(BaseModel):
    """
    项目成果认定记录表（proj_achievement_review）

    业务含义：管理员/学院对成果真实性做认定，认定通过才计入结题成果与证书生成。
    关键约束：achievement_id 唯一（uk_achievement_review），一条成果至多一条认定记录；
    历史数据缺失认定记录时，展示层按"已认定"兜底。
    """
    __tablename__ = "proj_achievement_review"

    # 被认定的成果：与 ProjAchievement 一对一
    achievement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proj_achievement.id"), nullable=False, comment="成果ID"
    )
    # 状态: 0-待认定 1-已认定 2-不通过（不通过的成果不计入结题条件）
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="认定状态")
    # 认定人：可为空，表示系统自动认定或管理员批量处理
    reviewer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="认定人ID")
    # 认定人姓名快照
    reviewer_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="认定人姓名")
    # 认定意见：不通过时必须说明理由
    review_comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="认定意见")
    # 认定时间 / 提交认定时间：认定时效统计
    review_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="认定时间")
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="提交认定时间")

    # 唯一约束保证一成果一认定；状态索引支撑"待认定"待办查询
    __table_args__ = (
        Index("uk_achievement_review", "achievement_id", unique=True),
        Index("idx_achievement_review_status", "status"),
    )


class ProjMidtermCheck(BaseModel):
    """
    项目中期检查表（proj_midterm_check）

    业务含义：项目立项后到中期节点提交的进展报告，状态 1 时可被审核，
    审核通过后项目进入"待结题"；一份项目仅一条中期记录。
    关键约束：project_id 唯一（uk_project）。
    """
    __tablename__ = "proj_midterm_check"

    # 所属项目：一对一
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 当前进展描述：中期报告主体内容
    progress_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="当前进展描述")
    # 已完成任务 / 剩余任务 / 存在问题 / 下一步计划：结构化汇报项
    completed_tasks: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="已完成任务")
    remaining_tasks: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="剩余任务计划")
    problems: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="存在问题")
    next_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="下一步计划")
    # 中期报告正文：纯文本，附件另存 sys_attachment
    report: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="中期报告")
    # 已使用经费：报告时点的经费消耗快照，与报销流水核对
    budget_usage: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True, comment="已使用经费")
    # 状态: 0-草稿 1-待审核 2-审核通过 3-需修改 4-已驳回（5-已作废在 Schema 常量中定义）
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="状态")
    # 审核人 / 审核意见 / 审核时间
    reviewer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="审核人ID")
    review_comment: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, comment="审核意见")
    review_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="审核时间")
    # 提交时间：草稿转待审核的时间
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="提交时间")

    # 关联关系：一对一，反向 ProjProject.midterm_check
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="midterm_check")

    # 唯一约束保证一项目一条；状态索引支撑中期审核待办
    __table_args__ = (
        Index("uk_project", "project_id", unique=True),
        Index("idx_status", "status"),
    )


class ProjChangeRequest(BaseModel):
    """
    项目变更/延期申请表（proj_change_request）

    业务含义：项目执行过程中对延期、成员、内容、预算的调整申请，
    同一项目累计最多提交 2 次（Schema 常量 CHANGE_MAX_TIMES）。
    关键约束：每阶段配额由 project_status_at_submit + 状态统计实现，库层无唯一约束。
    """
    __tablename__ = "proj_change_request"

    # 所属项目
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 变更类型: 1-延期 2-人员变更 3-内容变更 4-预算调整 5-其他
    change_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="变更类型")
    # 变更原因：审批人判断合理性的依据，必填
    change_reason: Mapped[str] = mapped_column(String(1000), nullable=False, comment="变更原因")
    # 变更前后内容对照，便于留痕与审批
    original_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="原内容")
    new_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="变更后内容")
    # 申请人（通常为项目负责人）
    applicant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="申请人ID")
    # 状态: 0-待审核 3-已通过 4-已驳回 5-已撤回 6-已作废（1/2 为历史多级审批遗留，当前为单级审批）
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="状态")
    # 驳回原因 / 审批意见
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="驳回原因")
    # 提交与审批时间
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="提交时间")
    approval_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="审批时间")
    # 提交时项目所处状态：用于「每阶段限 1 次」配额（待学院初审/待校级复审各 1 次，累计 2 次）
    # 不直接引用当前 status，避免审批期间项目状态变化导致配额被重复计算
    project_status_at_submit: Mapped[Optional[int]] = mapped_column(
        SmallInteger, nullable=True, comment="提交时项目状态")

    # 关联关系：多对一；不级联删除，历史申请用于配额与追责
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="change_requests")

    # 按项目查询申请历史；(type, status) 支撑按类型统计与待办筛选
    __table_args__ = (
        Index("idx_project", "project_id"),
        Index("idx_type_status", "change_type", "status"),
    )
