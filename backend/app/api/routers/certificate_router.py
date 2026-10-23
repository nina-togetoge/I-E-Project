"""
获奖证书 API 路由层
"""
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
    items, total = CertificateService.paginate_mine(db, current_user.id, pager.page, pager.page_size)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))
