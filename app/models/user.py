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
    """学院ORM模型"""
    __tablename__ = "sys_college"

    college_code: Mapped[str] = mapped_column(String(32), nullable=False, comment="学院编码")
    college_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="学院名称")
    dean_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="院长用户ID")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态: 0-停用 1-启用")

    # 关联关系
    users: Mapped[List["SysUser"]] = relationship(
        "SysUser",
        back_populates="college",
        foreign_keys="SysUser.college_id"
    )


class SysUser(BaseModel):
    """系统用户ORM模型"""
    __tablename__ = "sys_user"

    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="登录账号(学号/工号)")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    real_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="真实姓名")
    email: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="邮箱")
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="手机号")
    # 角色: 1-学生 2-指导教师 3-评审专家 4-系统管理员
    role: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="角色")
    college_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("sys_college.id"),
        nullable=True,
        comment="所属学院ID"
    )
    avatar: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="头像URL")
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态: 0-禁用 1-启用")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后登录时间")
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="最后登录IP")

    # 关联关系
    college: Mapped[Optional["SysCollege"]] = relationship(
        "SysCollege",
        back_populates="users",
        foreign_keys=[college_id]
    )

    # 项目相关关联
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

    __table_args__ = (
        Index("uk_username", "username", unique=True),
        Index("idx_college", "college_id"),
        Index("idx_role", "role"),
        Index("idx_status", "status"),
    )


class SysOperationLog(Base):
    """
    操作日志ORM模型（不继承BaseModel，避免被软删除影响）
    单独使用独立主键和时间字段
    """
    __tablename__ = "sys_operation_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="操作用户ID")
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="操作账号")
    real_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="操作人姓名")
    user_role: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True, comment="用户角色")
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="操作类型")
    module_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="模块名称")
    operation_desc: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="操作描述")
    request_method: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="请求方法")
    request_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="请求URL")
    request_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="请求参数(JSON)")
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="响应状态码")
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="操作IP")
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="客户端UA")
    cost_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="耗时(毫秒)")
    operation_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        comment="操作时间"
    )

    __table_args__ = (
        Index("idx_user", "user_id"),
        Index("idx_operation", "operation_type", "module_name"),
        Index("idx_time", "operation_time"),
    )


class SysDict(Base):
    """系统字典ORM模型"""
    __tablename__ = "sys_dict"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="字典ID")
    dict_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="字典类型")
    dict_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="字典编码")
    dict_label: Mapped[str] = mapped_column(String(255), nullable=False, comment="字典标签")
    dict_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="字典值")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态: 0-禁用 1-启用")
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
        comment="创建时间"
    )

    __table_args__ = (
        Index("uk_type_code", "dict_type", "dict_code", unique=True),
        Index("idx_type", "dict_type"),
    )


class SysAttachment(BaseModel):
    """附件文件ORM模型"""
    __tablename__ = "sys_attachment"

    biz_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="业务类型")
    biz_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="业务记录ID")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_path: Mapped[str] = mapped_column(String(500), nullable=False, comment="存储路径")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小(字节)")
    file_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="文件MIME类型")
    file_ext: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="文件扩展名")
    uploader_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="上传人ID")
    uploader_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="上传人姓名(冗余)")
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="下载次数")

    __table_args__ = (
        Index("idx_biz", "biz_type", "biz_id"),
        Index("idx_uploader", "uploader_id"),
    )
