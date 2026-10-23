"""
获奖证书 数据模型（Pydantic Schema）
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class CertificateItem(BaseModel):
    """我的证书列表项"""

    id: int = Field(description="证书记录ID")
    cert_no: str = Field(description="证书编号")
    cert_type: int = Field(description="证书类型: 1-团队 2-个人")
    holder_name: str = Field(description="持证人/团队成员姓名")
    competition_name: str = Field(description="比赛名称")
    project_name: str = Field(description="项目名称")
    award_level: str = Field(description="奖项等级")
    organizer: Optional[str] = Field(default=None, description="主办单位")
    issue_date: date = Field(description="发证日期")
    attachment_id: int = Field(description="证书PDF附件ID")
    file_name: str = Field(description="证书文件名")
    download_count: int = Field(default=0, description="下载次数")
    downloaded: bool = Field(default=False, description="是否已领取(下载过)")
