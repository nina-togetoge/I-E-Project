# ====================================================================
# 基础数据域 ORM 模型（sys_* 前缀表）
# --------------------------------------------------------------------
# sys_college    学院主数据，是数据权限隔离的核心维度
# sys_user       统一用户表，role 1学生/2教师/3专家/4管理员；
#                超管 = role=4 且 college_id 为空；学院管理员 = role=4 且有 college_id
# sys_operation_log 操作审计日志，独立主键、不参与软删除，只增不改
# sys_dict       通用字典，驱动前端下拉与文案映射
# sys_attachment 附件元数据，实体文件存 Docker 卷，库中只存相对路径，
#                biz_type + biz_id 让一份附件表服务项目/成果/报销等多业务
# 数据生命周期：学院/用户/字典为软删除；日志为物理追加，按时间归档。
# ====================================================================
"""
用户与学院相关ORM模型
包含用户表、学院表、操作日志表、字典表等
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, BigInteger, SmallInteger, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.database.session import Base


class SysCollege(BaseModel):
    """
    学院表（sys_college）

    业务含义：学院主数据，项目申报、用户归属、数据权限（学院管理员）都以此为维度。
    关键约束：college_code 逻辑唯一（库中未建唯一索引），停用学院不可再分配给新用户。
    """
    __tablename__ = "sys_college"

    # 学院编码：与学校教务编码对齐，导入/对接时作为外部主键
    college_code: Mapped[str] = mapped_column(String(32), nullable=False, comment="学院编码")
    # 学院名称：下拉展示与报表分组名称
    college_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="学院名称")
    # 院长用户ID：仅作展示/联系用，不参与权限判断
    dean_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="院长用户ID")
    # 排序序号：前端下拉按此升序，数值小者靠前
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    # 状态: 0-停用 1-启用；停用后不再出现在可选学院列表
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态: 0-停用 1-启用")

    # 关联关系：一对多，学院下的用户；不设级联删除，学院软删除不影响历史用户
    users: Mapped[List["SysUser"]] = relationship(
        "SysUser",
        back_populates="college",
        foreign_keys="SysUser.college_id"
    )


class SysUser(BaseModel):
    """
    系统用户表（sys_user）

    业务含义：学生/教师/专家/管理员统一账号表，通过 role + college_id 区分权限层级：
      超管      = role=4 且 college_id 为空（跨学院全量数据）
      学院管理员 = role=4 且 college_id 有值（仅本院数据）
    关键约束：username 唯一（uk_username，登录账号不可重复）；
    密码只存哈希，任何情况下不得回传明文。
    """
    __tablename__ = "sys_user"

    # 登录账号：学号/工号/手机号/邮箱均可，全局唯一
    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="登录账号(学号/工号)")
    # 密码哈希：单向加密后存储，禁止落明文、禁止日志打印
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    # 真实姓名：证书、审批记录、报表展示
    real_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="真实姓名")
    # 邮箱/手机号：非必填，格式由 Schema 层严格校验（手机号 11 位中国大陆）
    email: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="邮箱")
    phone: Mapped[Optional[str]] = mapped_column(String(11), nullable=True, comment="手机号(严格11位中国格式)")
    # 角色: 1-学生 2-指导教师 3-评审专家 4-系统管理员
    role: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="角色")
    # 所属学院：管理员留空即超管，填值即学院管理员；学生/教师必填
    college_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("sys_college.id"),
        nullable=True,
        comment="所属学院ID"
    )
    # 学生专属：年级/专业，用于选题时成员信息自动带出
    grade: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="年级")
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="性别")
    major: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="专业(学生)")
    # 教师/专家专属：职称、研究方向；专家另有所属单位
    title: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="职称(教师/专家)")
    direction: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="研究方向(教师/专家)")
    organization: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="所属单位(专家)")
    # 头像：存 URL 或 base64，用 LONGTEXT 兼容 base64 体积
    avatar: Mapped[Optional[str]] = mapped_column(Text(length=2**32-1), nullable=True, comment="头像URL或base64")
    # 状态: 0-禁用 1-启用；禁用后登录直接拒绝
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态: 0-禁用 1-启用")
    # 首次登录强制改密: 0-否 1-是；管理员重置密码后置 1
    force_change_pwd: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="首次登录强制改密:0-否 1-是")
    # 最后登录时间/IP：安全审计与异常登录排查
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后登录时间")
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="最后登录IP")

    # 关联关系：多对一学院，反向由 SysCollege.users 维护
    college: Mapped[Optional["SysCollege"]] = relationship(
        "SysCollege",
        back_populates="users",
        foreign_keys=[college_id]
    )

    # 项目相关关联：同一用户既可能是负责人也可能是指导教师，两个方向都要显式 foreign_keys
    led_projects: Mapped[List["ProjProject"]] = relationship(
        "ProjProject",
        back_populates="leader",
        foreign_keys="ProjProject.leader_id"
    )
    taught_projects: Mapped[List["ProjProject"]] = relationship(
        "ProjProject",
        back_populates="teacher",
        foreign_keys="ProjProject.teacher_id"
    )

    # username 唯一；college/role/status 支撑登录后权限过滤与用户管理筛选
    __table_args__ = (
        Index("uk_username", "username", unique=True),
        Index("idx_college", "college_id"),
        Index("idx_role", "role"),
        Index("idx_status", "status"),
    )


class SysOperationLog(Base):
    """
    操作日志表（sys_operation_log）

    业务含义：记录管理端关键操作（增删改、审批、导入等）用于审计追溯。
    继承策略：刻意不继承 BaseModel——审计日志不应被软删除或 updated_at 改写，
    因此只保留独立主键与 operation_time，且只追加不更新。
    关键约束：无唯一键；user_id 不设外键，用户删除后日志仍需保留。
    """
    __tablename__ = "sys_operation_log"

    # 日志主键：独立自增，不参与业务语义
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    # 操作人信息快照：用户被删/改名后日志仍可读
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="操作用户ID")
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="操作账号")
    real_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="操作人姓名")
    # 操作人角色快照: 1学生 2教师 3专家 4管理员（用于按角色筛选审计）
    user_role: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True, comment="用户角色")
    # 操作类型（如 CREATE/UPDATE/DELETE/APPROVE/IMPORT）与模块名，用于统计与筛选
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="操作类型")
    module_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="模块名称")
    # 人类可读的操作说明：列表直接展示
    operation_desc: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="操作描述")
    # 请求上下文：方法/URL/参数（脱敏后的 JSON）/状态码
    request_method: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="请求方法")
    request_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="请求URL")
    request_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="请求参数(JSON)")
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="响应状态码")
    # 客户端信息：IP/UA/耗时，用于安全排查与性能分析
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="操作IP")
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="客户端UA")
    cost_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="耗时(毫秒)")
    # 操作时间：数据库默认值填充，不支持人工回填
    operation_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        comment="操作时间"
    )

    # 按用户、按操作类型+模块、按时间三个维度检索日志
    __table_args__ = (
        Index("idx_user", "user_id"),
        Index("idx_operation", "operation_type", "module_name"),
        Index("idx_time", "operation_time"),
    )


class SysDict(Base):
    """
    系统字典表（sys_dict）

    业务含义：维护可配置的下拉项与文案映射（如项目类型、职称、性别等），
    减少硬编码枚举；区别于代码内的 Python 常量映射。
    继承策略：不继承 BaseModel，字典是配置数据，删除即物理删除，
    避免"软删除后唯一索引冲突"导致同编码无法重建。
    关键约束：(dict_type, dict_code) 唯一。
    """
    __tablename__ = "sys_dict"

    # 独立主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="字典ID")
    # 字典类型：一组字典的分组键（如 project_type）
    dict_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="字典类型")
    # 字典编码：组内唯一，通常与业务数值/英文标识对应
    dict_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="字典编码")
    # 字典标签：前端展示的中文文案
    dict_label: Mapped[str] = mapped_column(String(255), nullable=False, comment="字典标签")
    # 字典值：可选附加值（如颜色、简称），非必填
    dict_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="字典值")
    # 排序序号：同类型内升序展示
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    # 状态: 0-禁用 1-启用；禁用项不出现在下拉
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态: 0-禁用 1-启用")
    # 备注：说明该字典项的适用场景
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="备注")
    # 创建时间：数据库默认值
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        comment="创建时间"
    )

    # 类型+编码唯一防止重复项；idx_type 支撑按类型批量取下拉
    __table_args__ = (
        Index("uk_type_code", "dict_type", "dict_code", unique=True),
        Index("idx_type", "dict_type"),
    )


class SysAttachment(BaseModel):
    """
    附件元数据表（sys_attachment）

    业务含义：全平台附件统一登记，实体文件落在 Docker 卷，数据库只保存相对路径，
    因此库可迁移、备份轻量；通过 biz_type + biz_id 实现多业务复用
    （如 project / achievement / expense / midterm / final / certificate）。
    关键约束：无唯一键，同一业务可挂多个附件；
    上传时 biz_id=0 表示临时附件，业务创建成功后再回填真实 ID。
    """
    __tablename__ = "sys_attachment"

    # 业务类型：与 biz_id 组成逻辑外键，如 project/achievement/expense
    biz_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="业务类型")
    # 业务记录ID：0 表示尚未绑定业务的临时附件
    biz_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="业务记录ID")
    # 原始文件名：下载时还原给用户，不用于磁盘定位
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    # 存储相对路径：相对于 Docker 卷挂载根目录，禁止存绝对路径
    file_path: Mapped[str] = mapped_column(String(500), nullable=False, comment="存储路径")
    # 文件大小（字节）：前端限制上传体积与展示用
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小(字节)")
    # MIME 类型与扩展名：下载响应头与预览判断
    file_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="文件MIME类型")
    file_ext: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="文件扩展名")
    # 上传人快照：权限校验与审计
    uploader_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="上传人ID")
    uploader_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="上传人姓名(冗余)")
    # 下载次数：热门附件统计
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="下载次数")

    # (biz_type, biz_id) 联合索引是附件查询主路径；uploader 支撑"我上传的文件"
    __table_args__ = (
        Index("idx_biz", "biz_type", "biz_id"),
        Index("idx_uploader", "uploader_id"),
    )
