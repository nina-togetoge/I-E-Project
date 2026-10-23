"""
通用接口路由：附件上传/下载、Excel导入导出模板、字典、健康检查
"""
import os
import uuid
import zipfile
import hashlib
import hmac
import mimetypes
from datetime import datetime
from html import escape as _html_escape
from typing import Optional
from urllib.parse import quote as _url_quote
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import PaginationParams, OperationContext, DataScope
from app.core.security import (
    get_current_user, require_login, require_admin, RequireRole, RoleEnum, ROLE_NAME_MAP,
    is_super_admin,
)
from app.core.response import ResponseModel, success, PageResult
from app.core.exceptions import ResourceNotFoundException, ParamValidateException, PermissionDeniedException
from app.database.session import get_db
from app.models import SysUser, SysAttachment, ProjProject

from app.utils.excel_helper import (
    ExcelHelper, ExportTemplates, USER_IMPORT_COLUMNS, PROJECT_IMPORT_COLUMNS,
)
from app.utils.redis_cache import redis_client, CacheKeys
from app.crud.user import CollegeCRUD, UserCRUD, OperationLogCRUD
from app.crud.project import ProjectCRUD
from app.services.project_service import ProjectService
from app.services.user_service import ImportResultResponse, UserService
from app.schemas.project import ProjectQueryParams

router_common = APIRouter(prefix="/common", tags=["通用工具"])
router_upload = APIRouter(prefix="/files", tags=["附件管理"])
router_excel = APIRouter(prefix="/excel", tags=["Excel导入导出"])
router_health = APIRouter(tags=["系统"])


def _attachment_header(filename: str) -> dict:
    """生成兼容中文文件名的 Content-Disposition 头(RFC 6266)。

    HTTP 头只能用 latin-1 编码，直接放中文文件名会触发
    UnicodeEncodeError。这里同时给出 ASCII fallback 与 UTF-8 编码版本。
    """
    encoded = _url_quote(filename, safe="")
    return {"Content-Disposition": f"attachment; filename=\"{encoded}\"; filename*=UTF-8''{encoded}"}


# ====================================================================
# 健康检查
# ====================================================================
@router_health.get("/api/health", summary="健康检查")
@router_health.get("/health", include_in_schema=False)
def api_health():
    return success(data={
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
    })


# ====================================================================
# 系统字典 + 学院缓存查询
# ====================================================================
@router_common.get("/dict/{dict_type}", response_model=ResponseModel, summary="按类型查询系统字典")
def api_get_dict(dict_type: str, db: Session = Depends(get_db)):
    """优先Redis缓存，未命中则查库并写入缓存"""
    try:
        cache_key = CacheKeys.DICT_BY_TYPE.format(dict_type=dict_type)
        cached = redis_client.get_json(cache_key)
        if cached is not None:
            return success(data=cached)
    except Exception:
        pass
    from app.models import SysDict
    items = db.query(SysDict).filter(
        SysDict.dict_type == dict_type, SysDict.status == 1
    ).order_by(SysDict.sort_order.asc()).all()
    data = [{"code": i.dict_code, "label": i.dict_label, "value": i.dict_value} for i in items]
    try:
        redis_client.set_json(cache_key, data, CacheKeys.DICT_TTL)
    except Exception:
        pass
    return success(data=data)


@router_common.get("/colleges", response_model=ResponseModel, summary="查询学院列表(带缓存)")
def api_college_list_cache(db: Session = Depends(get_db)):
    try:
        cached = redis_client.get_json(CacheKeys.COLLEGE_LIST)
        if cached is not None:
            return success(data=cached)
    except Exception:
        pass
    from app.schemas.user import CollegeResponse
    cols = CollegeCRUD.list_all(db)
    data = [CollegeResponse.model_validate(c).model_dump(mode="json") for c in cols]
    try:
        redis_client.set_json(CacheKeys.COLLEGE_LIST, data, CacheKeys.COLLEGE_LIST_TTL)
    except Exception:
        pass
    return success(data=data)


# ====================================================================
# 附件上传/下载
# ====================================================================
def _secure_filename(filename: str) -> str:
    """安全化文件名：保留原扩展名，用UUID重命名避免覆盖/路径穿越"""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS_LIST:
        raise ParamValidateException(message=f"不允许的文件类型，仅支持 {settings.ALLOWED_EXTENSIONS}")
    return f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex}{ext}"


# 富文本内嵌图片允许的扩展名（仅图片，且不含 svg 以免脚本注入）
_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}


def _image_sig(att_id: int) -> str:
    """为内嵌图片生成长期有效的签名。

    富文本里的 <img> 无法携带 Authorization 头，因此图片直链改为签名访问：
    签名由密钥派生、不随登录令牌过期，内容页可长期正常显示。
    """
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(), f"files-img:{att_id}".encode(), hashlib.sha256
    ).hexdigest()[:32]


def _resolve_biz_project(db: Session, biz_type: str, biz_id: int):
    """把附件所属业务记录解析为对应的项目对象；无法解析时返回 None。

    注意：不同业务表的 biz_id 语义不同（project 用项目ID，achievement 用成果ID，
    expense 用报销ID，review 用审核记录ID），必须分别解析，不能统一当项目ID 处理。
    """
    if not biz_id or biz_id <= 0:
        return None
    if biz_type == "project":
        return ProjectCRUD.get_by_id(db, biz_id)
    if biz_type == "achievement":
        from app.models import ProjAchievement
        ach = db.query(ProjAchievement).filter(
            ProjAchievement.id == biz_id, ProjAchievement.is_deleted == 0
        ).first()
        return ProjectCRUD.get_by_id(db, ach.project_id) if ach else None
    if biz_type == "midterm":
        from app.models import ProjMidtermCheck
        mid = db.query(ProjMidtermCheck).filter(
            ProjMidtermCheck.id == biz_id, ProjMidtermCheck.is_deleted == 0
        ).first()
        return ProjectCRUD.get_by_id(db, mid.project_id) if mid else None
    if biz_type == "expense":
        from app.models import ProjExpense
        exp = db.query(ProjExpense).filter(
            ProjExpense.id == biz_id, ProjExpense.is_deleted == 0
        ).first()
        return ProjectCRUD.get_by_id(db, exp.project_id) if exp else None
    if biz_type == "review":
        from app.models import ProjReview
        rv = db.query(ProjReview).filter(
            ProjReview.id == biz_id, ProjReview.is_deleted == 0
        ).first()
        return ProjectCRUD.get_by_id(db, rv.project_id) if rv else None
    return None


def _ensure_biz_access(db: Session, biz_type: str, biz_id: int, user: SysUser,
                       allow_uploader_id: Optional[int] = None) -> None:
    """统一校验用户对某业务记录附件的访问/上传权限。

    放行条件：管理员；上传者本人(下载场景)；项目负责人/指导教师/团队成员；
    报销场景下额外的报销申请人或本院教师、学院管理员。其余一律拒绝。
    """
    if user.role == RoleEnum.ADMIN:
        # 真超级管理员（无学院归属）放行全部；学院管理员仅限本院项目附件
        if not user.college_id:
            return
        if allow_uploader_id is not None and allow_uploader_id == user.id:
            return
        project = _resolve_biz_project(db, biz_type, biz_id)
        if project is not None and project.college_id == user.college_id:
            return
        raise PermissionDeniedException(message="学院管理员仅可访问本院业务文件")
    if allow_uploader_id is not None and allow_uploader_id == user.id:
        return
    project = _resolve_biz_project(db, biz_type, biz_id)
    if project is None:
        raise PermissionDeniedException(message="无权访问该业务文件")
    if project.leader_id == user.id or project.teacher_id == user.id:
        return
    if biz_type == "expense":
        from app.models import ProjExpense
        exp = db.query(ProjExpense).filter(
            ProjExpense.id == biz_id, ProjExpense.is_deleted == 0
        ).first()
        if exp and exp.applicant_id == user.id:
            return
        # 本院教师/学院管理员可查看本院项目报销
        if (user.college_id and project.college_id == user.college_id
                and user.role in (RoleEnum.TEACHER, RoleEnum.ADMIN)):
            return
    from app.models import ProjTeamMember
    is_member = db.query(ProjTeamMember).filter(
        ProjTeamMember.project_id == project.id,
        ProjTeamMember.student_id == user.id,
    ).first() is not None
    if is_member:
        return
    raise PermissionDeniedException(message="无权访问该业务文件")


@router_upload.post("/upload", response_model=ResponseModel, summary="单文件上传")
async def api_upload(
    biz_type: str = Form(..., pattern=r"^[a-z_]{1,64}$", description="业务类型: project/expense/achievement/review"),
    biz_id: int = Form(default=0, ge=0, description="业务记录ID，0表示临时上传待关联"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 文件大小校验（前端提示，后端兜底）
    MAX = settings.MAX_UPLOAD_SIZE
    bytes_data = await file.read()
    if len(bytes_data) > MAX:
        raise ParamValidateException(message=f"文件大小超过上限 {MAX // 1024 // 1024}MB")

    # 2. 扩展名 + 重命名
    new_name = _secure_filename(file.filename or "unknown")

    # 3. 权限校验（先校验后写盘，避免越权请求在磁盘留下孤儿文件）
    if biz_id > 0:
        _ensure_biz_access(db, biz_type, biz_id, current_user)

    # 4. 落盘
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    save_path = os.path.join(settings.UPLOAD_DIR, new_name)
    with open(save_path, "wb") as f:
        f.write(bytes_data)

    # 5. 入库
    ext = os.path.splitext(file.filename or "")[1].lower()
    att = SysAttachment(
        biz_type=biz_type, biz_id=biz_id,
        file_name=file.filename, file_path=save_path,
        file_size=len(bytes_data),
        file_type=file.content_type,
        file_ext=ext.lstrip("."),
        uploader_id=current_user.id, uploader_name=current_user.real_name,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    with ctx:
        ctx.set_desc(f"上传附件[{file.filename}]到{biz_type}#{biz_id}")
    image_url = None
    if ext.lstrip(".").lower() in _IMAGE_EXTS:
        image_url = f"/api/files/img/{att.id}?sig={_image_sig(att.id)}"
    return success(data={
        "id": att.id, "file_name": att.file_name, "file_size": att.file_size,
        "file_url": f"/api/files/download/{att.id}",
        "image_url": image_url,
    })


@router_upload.get("/download/{att_id}", summary="下载附件（权限校验+计数）")
def api_download(
    att_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    att = db.query(SysAttachment).filter(SysAttachment.id == att_id, SysAttachment.is_deleted == 0).first()
    if not att:
        raise ResourceNotFoundException(message="文件不存在")
    # 下载权限：管理员/上传者/所属业务相关人（统一校验）
    _ensure_biz_access(db, att.biz_type, att.biz_id or 0, current_user,
                       allow_uploader_id=att.uploader_id)
    if not os.path.exists(att.file_path):
        raise ResourceNotFoundException(message="服务器上文件已丢失")

    # 下载计数+1
    att.download_count = (att.download_count or 0) + 1
    db.commit()

    # 解析MIME，PDF/图片等浏览器支持预览
    mime = att.file_type or mimetypes.guess_type(att.file_name)[0] or "application/octet-stream"
    # 中文文件名URL编码
    import urllib.parse
    fname_encode = urllib.parse.quote(att.file_name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{fname_encode}",
    }
    return FileResponse(path=att.file_path, media_type=mime, filename=att.file_name, headers=headers)


_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_to_html(path: str, filename: str) -> Optional[str]:
    """把 .docx 解析为可读 HTML（仅用标准库），供浏览器在线预览。

    浏览器无法内联渲染 docx，直接返回文件会触发下载；这里提取段落与表格，
    失败时返回 None，由调用方回退为原始文件响应。
    """
    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
        body = ET.fromstring(xml_bytes).find(f"{_DOCX_NS}body")
    except Exception:
        return None
    if body is None:
        return None

    blocks = []
    for node in body:
        if node.tag == f"{_DOCX_NS}p":
            text = "".join(t.text or "" for t in node.iter(f"{_DOCX_NS}t"))
            if not text.strip():
                continue
            style = ""
            ppr = node.find(f"{_DOCX_NS}pPr")
            if ppr is not None:
                st = ppr.find(f"{_DOCX_NS}pStyle")
                if st is not None:
                    style = (st.get(f"{_DOCX_NS}val") or "").lower()
            if style.startswith("heading") or style.startswith("标题"):
                try:
                    level = min(int(style.replace("heading", "")) + 1, 4)
                except ValueError:
                    level = 2
                blocks.append(f"<h{level}>{_html_escape(text)}</h{level}>")
            else:
                blocks.append(f"<p>{_html_escape(text)}</p>")
        elif node.tag == f"{_DOCX_NS}tbl":
            rows = []
            for tr in node.findall(f"{_DOCX_NS}tr"):
                cells = []
                for tc in tr.findall(f"{_DOCX_NS}tc"):
                    cell_text = "".join(t.text or "" for t in tc.iter(f"{_DOCX_NS}t"))
                    cells.append(f"<td>{_html_escape(cell_text)}</td>")
                rows.append("<tr>" + "".join(cells) + "</tr>")
            if rows:
                blocks.append("<table>" + "".join(rows) + "</table>")

    if not blocks:
        return None
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{_html_escape(filename)}</title>"
        "<style>"
        "body{margin:0;padding:24px;background:#f5f7fa;"
        "font-family:'Microsoft YaHei','PingFang SC',sans-serif;color:#303133;}"
        ".page{max-width:880px;margin:0 auto;background:#fff;padding:36px 44px;"
        "box-shadow:0 2px 12px rgba(0,0,0,.08);border-radius:6px;line-height:1.9;font-size:15px;}"
        "h1,h2,h3,h4{line-height:1.5;margin:18px 0 10px;}"
        "p{margin:6px 0;text-indent:2em;word-break:break-all;}"
        "table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;}"
        "td{border:1px solid #dcdfe6;padding:6px 10px;text-indent:0;}"
        ".notice{max-width:880px;margin:0 auto 12px;color:#909399;font-size:12px;}"
        "</style></head><body>"
        f"<div class=\"notice\">{_html_escape(filename)} · 在线预览</div>"
        f"<div class=\"page\">{''.join(blocks)}</div>"
        "</body></html>"
    )


@router_upload.get("/preview/{att_id}", summary="在线预览附件（inline）")
def api_preview(
    att_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    att = db.query(SysAttachment).filter(SysAttachment.id == att_id, SysAttachment.is_deleted == 0).first()
    if not att:
        raise ResourceNotFoundException(message="文件不存在")
    # 预览权限：与下载权限一致（统一校验）
    _ensure_biz_access(db, att.biz_type, att.biz_id or 0, current_user,
                       allow_uploader_id=att.uploader_id)
    if not os.path.exists(att.file_path):
        raise ResourceNotFoundException(message="服务器上文件已丢失")

    ext = (att.file_ext or os.path.splitext(att.file_name)[1].lstrip(".")).lower().lstrip(".")
    # Word 文档浏览器无法内联渲染，转 HTML 预览；解析失败则回退原始文件
    if ext == "docx":
        html = _docx_to_html(att.file_path, att.file_name)
        if html:
            return HTMLResponse(content=html, headers={"Content-Disposition": "inline"})

    mime = att.file_type or mimetypes.guess_type(att.file_name)[0] or "application/octet-stream"
    # inline 模式：浏览器直接展示而非下载
    return FileResponse(path=att.file_path, media_type=mime, headers={"Content-Disposition": "inline"})


@router_upload.get("/img/{att_id}", summary="富文本内嵌图片（签名直链，免登录）")
def api_embed_image(
    att_id: int,
    sig: str = Query(..., description="图片签名"),
    db: Session = Depends(get_db),
):
    """供富文本 <img src> 使用：<img> 无法携带令牌，改用长期有效的签名校验。

    仅允许图片扩展名，避免把该接口变成任意附件下载通道。
    """
    att = db.query(SysAttachment).filter(
        SysAttachment.id == att_id, SysAttachment.is_deleted == 0
    ).first()
    ext = (att.file_ext or "").lower().lstrip(".") if att else ""
    if not att or ext not in _IMAGE_EXTS:
        raise ResourceNotFoundException(message="图片不存在")
    if not hmac.compare_digest(sig, _image_sig(att_id)):
        raise PermissionDeniedException(message="图片链接无效")
    if not os.path.exists(att.file_path):
        raise ResourceNotFoundException(message="服务器上文件已丢失")

    mime = att.file_type if (att.file_type or "").startswith("image/") \
        else mimetypes.guess_type(att.file_name)[0] or "application/octet-stream"
    return FileResponse(
        path=att.file_path, media_type=mime,
        headers={"Content-Disposition": "inline", "Cache-Control": "public, max-age=86400"},
    )


@router_upload.get("/list/{biz_type}/{biz_id}", response_model=ResponseModel, summary="查询业务下附件列表")
def api_attachment_list(
    biz_type: str, biz_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 权限校验：已有业务记录按归属校验；临时附件(biz_id=0)仅本人可见
    q = db.query(SysAttachment).filter(
        SysAttachment.biz_type == biz_type,
        SysAttachment.biz_id == biz_id,
        SysAttachment.is_deleted == 0,
    )
    if biz_id > 0:
        _ensure_biz_access(db, biz_type, biz_id, current_user)
    elif current_user.role != RoleEnum.ADMIN:
        q = q.filter(SysAttachment.uploader_id == current_user.id)
    items = q.order_by(SysAttachment.created_at.desc()).all()
    data = [{
        "id": a.id, "file_name": a.file_name, "file_size": a.file_size,
        "file_type": a.file_type, "uploader_name": a.uploader_name,
        "download_count": a.download_count,
        "created_at": a.created_at,
        "download_url": f"/api/files/download/{a.id}",
    } for a in items]
    return success(data=data)


@router_upload.delete("/{att_id}", response_model=ResponseModel, summary="删除附件（软删除）")
def api_delete_attachment(
    att_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    att = db.query(SysAttachment).filter(
        SysAttachment.id == att_id, SysAttachment.is_deleted == 0
    ).first()
    if not att:
        raise ResourceNotFoundException(message="文件不存在")
    # 权限：仅上传者本人或系统管理员可删除
    if current_user.role != RoleEnum.ADMIN and att.uploader_id != current_user.id:
        raise PermissionDeniedException(message="无权删除该附件")
    # 已绑定项目的附件：仅当项目处于可编辑状态（草稿/已驳回）时允许删除，与编辑弹窗保持一致
    if att.biz_type == "project" and att.biz_id and att.biz_id > 0:
        project = _resolve_biz_project(db, att.biz_type, att.biz_id)
        if project is not None and project.status not in (0, 10):
            raise ParamValidateException(message="当前项目状态不可删除附件")
    att.is_deleted = 1
    db.commit()
    with ctx:
        ctx.set_desc(f"删除附件[{att.file_name}]")
    return success(data={"id": att_id})


# ====================================================================
# Excel 导入导出
# ====================================================================

@router_excel.get("/template/user", summary="下载-用户批量导入模板")
def api_user_template():
    xlsx = ExcelHelper.generate_template(USER_IMPORT_COLUMNS, sheet_name="用户导入")
    headers = _attachment_header("用户批量导入模板.xlsx")
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router_excel.get("/template/project", summary="下载-项目基础信息导入模板")
def api_project_template():
    xlsx = ExcelHelper.generate_template(PROJECT_IMPORT_COLUMNS, sheet_name="项目导入")
    headers = _attachment_header("项目基础信息导入模板.xlsx")
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router_excel.post("/import/user", response_model=ResponseModel[ImportResultResponse],
                   summary="上传-批量导入用户(Excel)")
async def api_import_users(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    raw = await file.read()
    rows, errors = ExcelHelper.parse_workbook(raw, USER_IMPORT_COLUMNS)
    if errors:
        return success(data=ImportResultResponse(
            total=len(rows) + len(errors), success=len(rows), failed=len(errors), errors=errors
        ))
    with ctx:
        ctx.set_desc(f"批量导入用户{len(rows)}人")
        result = UserService.batch_create(db, rows, current_user)
    # 清除学院/用户缓存
    redis_client.delete(CacheKeys.COLLEGE_LIST)
    return success(data=result, message="导入完成")


@router_excel.get("/export/projects", summary="导出-项目名单(Excel)")
def api_export_projects(
    params: ProjectQueryParams = Depends(),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    # [P1-7] 导出上限收紧：一次最多导出 2000 条（原 10000 过大，拉爆DB/内存）
    pager = PaginationParams(page=1, page_size=2000)
    items, _ = ProjectService.paginate(db, pager, params, data_scope)
    rows = [i.model_dump(mode="python") for i in items]
    xlsx = ExcelHelper.export_list(ExportTemplates.project_list_columns(), rows, sheet_name="项目名单")
    headers = _attachment_header(f'项目名单_{datetime.now().strftime("%Y%m%d")}.xlsx')
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router_excel.get("/export/logs", summary="导出-操作日志(Excel)")
def api_export_logs(
    keyword: Optional[str] = None, module_name: Optional[str] = None,
    operation_type: Optional[str] = None, user_id: Optional[int] = None,
    start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
    modules: Optional[str] = None, operation_types: Optional[str] = None,
    user_roles: Optional[str] = None, statuses: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
):
    # 数据范围与列表接口一致：真超级管理员导全部；学院管理员仅导本院用户日志
    college_id = None if is_super_admin(current_user) else current_user.college_id
    rows_orm = OperationLogCRUD.list_all_for_export(
        db, keyword=keyword, module_name=module_name,
        operation_type=operation_type, user_id=user_id,
        college_id=college_id,
        start_time=start_time, end_time=end_time,
        modules=modules, operation_types=operation_types,
        user_roles=user_roles, statuses=statuses,
    )
    from app.schemas.user import OperationLogItem
    rows = [OperationLogItem.model_validate(o).model_dump(mode="python") for o in rows_orm]
    xlsx = ExcelHelper.export_list(ExportTemplates.operation_log_columns(), rows, sheet_name="操作日志")
    headers = _attachment_header(f'操作日志_{datetime.now().strftime("%Y%m%d")}.xlsx')
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )
