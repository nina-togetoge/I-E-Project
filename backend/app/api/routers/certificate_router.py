"""
获奖证书 API 路由层
"""
# ====================================================================
# 获奖证书路由
# ----------------------------------------------------------------------------
# 对外接口分组（前缀 /api/certificates）：
#   GET /my   当前登录学生的获奖证书分页列表
# 前端对应：个人中心「我的证书」页面（/my-certificates）。
# 依赖 Service：CertificateService.paginate_mine。
# 权限约束：仅登录用户；服务层强制按 user_id 匹配个人证书，
#           团队证书则按「本人负责或参与的项目」放开，用户看不到无关证书。
# 特殊业务规则：
#   - 证书由校级比赛生成获奖名单时签发（CompetitionService.generate_awards），
#     包含每个获奖项目 1 张团队证书 + 每位成员 1 张个人证书；
#   - cert_type 1=团队证书（user_id 为空，按项目成员关系可见）、2=个人证书；
#   - 证书 PDF 存于上传目录，数据库只登记 sys_attachment 相对路径；
#   - 列表附带 attachment_id，前端据此调用 /api/files/download/{id} 下载；
#     附件已软删的证书不会返回，避免出现无法下载的条目。
# ====================================================================
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams
from app.core.response import ResponseModel, PageResult, success
from app.core.security import require_login
from app.database.session import get_db
from app.models import SysUser
from app.schemas.certificate import CertificateItem
from app.services.certificate_service import CertificateService

router_certificate = APIRouter(prefix="/certificates", tags=["获奖证书"])


# --- 接口说明 ---
# GET /api/certificates/my：我的获奖证书（分页）。
# 谁可以调用：任意已登录用户（实际使用场景以学生为主）。
# 入参：page 页码（从 1 开始）、page_size 每页条数。
# 返回：PageResult[CertificateItem]，含证书编号、类型、持证人、比赛/项目名、
#       奖项、发证日期、附件 id、文件名、下载次数与是否已下载。
# 异常：无业务异常；无证书时返回空列表而非 404。
# 副作用：只读查询，不增加下载次数（下载走 /api/files/download 接口）。
@router_certificate.get(
    "/my",
    response_model=ResponseModel[PageResult[CertificateItem]],
    summary="我的获奖证书(分页)",
)
def api_my_certificates(
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 个人证书按 user_id 匹配；团队证书按本人负责/参与的项目匹配（见 Service 实现）
    items, total = CertificateService.paginate_mine(db, current_user.id, pager.page, pager.page_size)
    # 2. 统一分页包装，按发证日期倒序展示，最新证书在前
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))
