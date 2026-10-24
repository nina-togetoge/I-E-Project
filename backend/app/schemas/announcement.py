# ====================================================================
# 公告模块 Schema
# --------------------------------------------------------------------
# 分组说明：
#   1. 常量：类型/状态/优先级三组 NAME 映射；
#   2. 写入：AnnouncementCreate（title/content 必填）、AnnouncementUpdate（全可选）；
#   3. 读取：AnnouncementListItem（列表）、AnnouncementDetail（详情，含正文）。
# 可见性：前台只读取 status=1 已发布且未过期的公告，由 Service 过滤。
# ====================================================================
"""
公告 Pydantic 数据模型
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ====================================================================
# 常量
# ====================================================================
# 公告类型映射：1 系统通知 / 2 申报通知 / 3 结果公示 / 4 其他
ANNOUNCEMENT_TYPE_NAME = {1: "系统通知", 2: "申报通知", 3: "结果公示", 4: "其他"}
# 公告状态映射：0 草稿 / 1 已发布 / 2 已下线
ANNOUNCEMENT_STATUS_NAME = {0: "草稿", 1: "已发布", 2: "已下线"}
# 优先级映射：1 普通 / 2 重要 / 3 紧急
ANNOUNCEMENT_PRIORITY_NAME = {1: "普通", 2: "重要", 3: "紧急"}


# ====================================================================
# 创建 / 更新
# ====================================================================
class AnnouncementCreate(BaseModel):
    """创建公告请求：标题与正文必填，类型/状态/优先级有默认值"""
    # 标题：上限 255
    title: str = Field(..., max_length=255, description="公告标题")
    # 正文：必填，无长度上限（Text 字段）
    content: str = Field(..., description="公告内容")
    # 类型 1-4 / 状态 0-2 / 优先级 1-3
    announcement_type: int = Field(1, ge=1, le=4, description="公告类型:1系统通知 2申报通知 3结果公示 4其他")
    status: int = Field(0, ge=0, le=2, description="状态:0草稿 1已发布 2已下线")
    priority: int = Field(1, ge=1, le=3, description="优先级:1普通 2重要 3紧急")
    # 到期时间：为空表示永久有效
    expire_time: Optional[datetime] = Field(None, description="到期时间，到期后自动下线")


class AnnouncementUpdate(BaseModel):
    """更新公告请求：全部可选，支持只改状态（发布/下线）"""
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = None
    announcement_type: Optional[int] = Field(None, ge=1, le=4)
    status: Optional[int] = Field(None, ge=0, le=2)
    priority: Optional[int] = Field(None, ge=1, le=3)
    expire_time: Optional[datetime] = Field(None, description="到期时间，到期后自动下线")


# ====================================================================
# 列表项 / 详情
# ====================================================================
class AnnouncementListItem(BaseModel):
    """公告列表项响应：*_name 与 creator_name 由 Service 回填"""
    model_config = ConfigDict(from_attributes=True)

    # 主键与标题；content 默认空串，列表可按需截断返回
    id: int
    title: str
    content: str = ""
    # 类型/状态/优先级及文案
    announcement_type: int
    announcement_type_name: str = ""
    status: int
    status_name: str = ""
    priority: int
    priority_name: str = ""
    # 发布与到期时间
    publish_time: Optional[datetime] = None
    expire_time: Optional[datetime] = None
    # 浏览量与创建人
    view_count: int = 0
    created_by: Optional[int] = None
    creator_name: Optional[str] = None
    created_at: datetime


class AnnouncementDetail(AnnouncementListItem):
    """公告详情响应：content 返回完整正文"""
    content: str = ""
