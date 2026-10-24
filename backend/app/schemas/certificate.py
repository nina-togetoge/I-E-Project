# ====================================================================
# 证书模块 Schema
# --------------------------------------------------------------------
# 分组说明：
#   CertificateItem：证书列表/详情响应，面向"我的证书"接口；
#   证书生成在 Service 内部完成，不对外暴露创建 Schema。
# 可见性：团队证书（cert_type=1，user_id 为空）按项目成员关系对全员展示；
#         个人证书（cert_type=2）按 user_id 归属到人。
# ====================================================================
"""
获奖证书 数据模型（Pydantic Schema）
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class CertificateItem(BaseModel):
    """我的证书列表项"""

    # 证书记录主键与唯一编号
    id: int = Field(description="证书记录ID")
    cert_no: str = Field(description="证书编号")
    # 1-团队（user_id 空，全员可见） / 2-个人（按 user_id 归属）
    cert_type: int = Field(description="证书类型: 1-团队 2-个人")
    # 证书正文快照字段
    holder_name: str = Field(description="持证人/团队成员姓名")
    competition_name: str = Field(description="比赛名称")
    project_name: str = Field(description="项目名称")
    award_level: str = Field(description="奖项等级")
    organizer: Optional[str] = Field(default=None, description="主办单位")
    issue_date: date = Field(description="发证日期")
    # 证书 PDF：附件ID + 下载展示用文件名
    attachment_id: int = Field(description="证书PDF附件ID")
    file_name: str = Field(description="证书文件名")
    # 下载次数与当前用户是否已下载（领取标记）
    download_count: int = Field(default=0, description="下载次数")
    downloaded: bool = Field(default=False, description="是否已领取(下载过)")
