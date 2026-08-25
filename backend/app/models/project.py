"""
项目相关ORM模型
包含项目、团队成员、审核记录、预算、报销、成果、中期检查、变更申请等模型
"""
from datetime import datetime, date
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import Column, String, BigInteger, SmallInteger, DateTime, Integer, Text, ForeignKey, Index, Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ProjProject(BaseModel):
    """创新创业项目ORM模型"""
    __tablename__ = "proj_project"

    project_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="项目编号")
    project_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="项目名称")
    # 项目类型: 1-创新训练 2-创业训练 3-创业实践
    project_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="项目类型")
    # 项目级别: 1-校级 2-省级 3-国家级
    project_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="项目级别")
    college_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_college.id"), nullable=False, comment="申报学院ID")
    leader_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=False, comment="项目负责人ID")
    teacher_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True, comment="指导教师ID")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="立项开始日期")
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="计划结束日期")
    budget_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="预算总额(元)"
    )
    used_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="已使用金额(元)"
    )
    project_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="项目简介")
    innovation_points: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="创新点")
    expected_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="预期成果")
    # 项目状态机: 0-草稿 1-待学院初审 2-学院初审通过 3-待校级复审 4-校级复审通过
    # 5-待专家评审 6-已立项 7-中期检查 8-待结题 9-已结题 10-已驳回 11-已撤销
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="项目状态")
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="正式提交时间")
    approval_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最终立项审批时间")
    current_approver_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="当前审批人ID")
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="驳回原因")

    # ========== 关联关系 ==========
    leader: Mapped["SysUser"] = relationship(
        "SysUser",
        back_populates="led_projects",
        foreign_keys=[leader_id]
    )
    teacher: Mapped[Optional["SysUser"]] = relationship(
        "SysUser",
        back_populates="taught_projects",
        foreign_keys=[teacher_id]
    )
    team_members: Mapped[List["ProjTeamMember"]] = relationship(
        "ProjTeamMember",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjTeamMember.project_id"
    )
    reviews: Mapped[List["ProjReview"]] = relationship(
        "ProjReview",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjReview.project_id"
    )
    budgets: Mapped[List["ProjBudget"]] = relationship(
        "ProjBudget",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjBudget.project_id"
    )
    expenses: Mapped[List["ProjExpense"]] = relationship(
        "ProjExpense",
        back_populates="project",
        foreign_keys="ProjExpense.project_id"
    )
    achievements: Mapped[List["ProjAchievement"]] = relationship(
        "ProjAchievement",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjAchievement.project_id"
    )
    midterm_check: Mapped[Optional["ProjMidtermCheck"]] = relationship(
        "ProjMidtermCheck",
        back_populates="project",
        uselist=False,
        foreign_keys="ProjMidtermCheck.project_id"
    )
    change_requests: Mapped[List["ProjChangeRequest"]] = relationship(
        "ProjChangeRequest",
        back_populates="project",
        foreign_keys="ProjChangeRequest.project_id"
    )
    college: Mapped[Optional["SysCollege"]] = relationship(
        "SysCollege",
        foreign_keys=[college_id],
        viewonly=True,
    )

    __table_args__ = (
        Index("uk_project_no", "project_no", unique=True),
        Index("idx_college", "college_id"),
        Index("idx_leader", "leader_id"),
        Index("idx_teacher", "teacher_id"),
        Index("idx_status", "status"),
        Index("idx_type_level", "project_type", "project_level"),
    )


class ProjTeamMember(BaseModel):
    """项目团队成员ORM模型"""
    __tablename__ = "proj_team_member"

    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="学生用户ID")
    student_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="学生姓名(冗余)")
    student_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="学号(冗余)")
    major: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="专业")
    grade: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="年级")
    role_in_team: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="团队内角色")
    task_desc: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="分工描述")
    join_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        comment="加入时间"
    )

    # 关联关系
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="team_members")

    __table_args__ = (
        Index("uk_project_student", "project_id", "student_id", unique=True),
        Index("idx_project", "project_id"),
        Index("idx_student", "student_id"),
    )


class ProjReview(BaseModel):
    """项目审核记录ORM模型"""
    __tablename__ = "proj_review"

    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 审核阶段: 1-学院初审 2-校级复审 3-专家评审 4-结题验收
    review_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="审核阶段")
    reviewer_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="审核人ID")
    reviewer_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="审核人姓名(冗余)")
    # 审核结果: 1-通过 2-驳回 3-修改后重提
    review_result: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="审核结果")
    score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True, comment="评分(百分制)")
    review_comment: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, comment="评审意见")
    review_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        comment="审核时间"
    )

    # 关联关系
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="reviews")

    __table_args__ = (
        Index("idx_project", "project_id"),
        Index("idx_reviewer", "reviewer_id"),
        Index("idx_stage", "review_stage"),
        Index("idx_project_stage", "project_id", "review_stage"),
    )


class ProjBudget(BaseModel):
    """项目预算ORM模型"""
    __tablename__ = "proj_budget"

    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    budget_item: Mapped[str] = mapped_column(String(128), nullable=False, comment="预算科目")
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="预算金额")
    used_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"), comment="已使用金额")
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="备注说明")

    # 关联关系
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="budgets")

    __table_args__ = (
        Index("idx_project", "project_id"),
    )


class ProjExpense(BaseModel):
    """经费报销申请ORM模型"""
    __tablename__ = "proj_expense"

    expense_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="报销单号")
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    applicant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="申请人ID")
    applicant_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="申请人姓名(冗余)")
    expense_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="报销金额")
    budget_item_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="对应预算科目ID")
    expense_desc: Mapped[str] = mapped_column(String(500), nullable=False, comment="费用说明")
    invoice_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="发票号码")
    # 审批状态: 0-草稿 1-待导师审批 2-导师审批通过 3-待学院审批 4-学院审批通过 5-待财务审批 6-已完成 7-已驳回
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="审批状态")
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="驳回原因")
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="提交时间")
    approval_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最终审批时间")

    # 关联关系
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="expenses")

    __table_args__ = (
        Index("uk_expense_no", "expense_no", unique=True),
        Index("idx_project", "project_id"),
        Index("idx_applicant", "applicant_id"),
        Index("idx_status", "status"),
    )


class ProjAchievement(BaseModel):
    """项目成果ORM模型"""
    __tablename__ = "proj_achievement"

    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 成果类型: 1-论文 2-专利 3-软件著作权 4-竞赛获奖 5-创业成果 6-其他
    achievement_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="成果类型")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="成果标题/名称")
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="作者/发明人")
    publish_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="发表/授权日期")
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="发表刊物/授权机构")
    achievement_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="编号")
    # 级别: 1-校级 2-省级 3-国家级 4-国际级
    level: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True, comment="级别")
    award_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="获奖等级")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="成果简介")

    # 关联关系
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="achievements")

    __table_args__ = (
        Index("idx_project", "project_id"),
        Index("idx_type", "achievement_type"),
    )


class ProjMidtermCheck(BaseModel):
    """项目中期检查ORM模型"""
    __tablename__ = "proj_midterm_check"

    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    progress_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="当前进展描述")
    completed_tasks: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="已完成任务")
    remaining_tasks: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="剩余任务计划")
    problems: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="存在问题")
    next_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="下一步计划")
    budget_usage: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True, comment="已使用经费")
    # 状态: 0-草稿 1-待审核 2-审核通过 3-需修改 4-已驳回
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="状态")
    reviewer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="审核人ID")
    review_comment: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, comment="审核意见")
    review_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="审核时间")
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="提交时间")

    # 关联关系
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="midterm_check")

    __table_args__ = (
        Index("uk_project", "project_id", unique=True),
        Index("idx_status", "status"),
    )


class ProjChangeRequest(BaseModel):
    """项目变更/延期申请ORM模型"""
    __tablename__ = "proj_change_request"

    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proj_project.id"), nullable=False, comment="项目ID")
    # 变更类型: 1-延期 2-人员变更 3-内容变更 4-预算调整 5-其他
    change_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="变更类型")
    change_reason: Mapped[str] = mapped_column(String(1000), nullable=False, comment="变更原因")
    original_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="原内容")
    new_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="变更后内容")
    applicant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="申请人ID")
    # 状态: 0-待审核 1-导师同意 2-学院同意 3-校级同意 4-已驳回
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="状态")
    reject_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="驳回原因")
    submit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="提交时间")
    approval_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="审批时间")

    # 关联关系
    project: Mapped["ProjProject"] = relationship("ProjProject", back_populates="change_requests")

    __table_args__ = (
        Index("idx_project", "project_id"),
        Index("idx_type_status", "change_type", "status"),
    )
