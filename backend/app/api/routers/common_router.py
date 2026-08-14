"""
通用接口路由：附件上传/下载、Excel导入导出模板、全文检索、字典、健康检查
"""
import os
import uuid
import mimetypes
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import PaginationParams, OperationContext, DataScope
from app.core.security import (
    get_current_user, require_login, require_admin, RequireRole, RoleEnum, ROLE_NAME_MAP,
)
from app.core.response import ResponseModel, success, PageResult
from app.core.exceptions import ResourceNotFoundException, ParamValidateException, PermissionDeniedException
from app.database.session import get_db
from app.models import SysUser, SysAttachment, ProjProject

from app.utils.excel_helper import (
    ExcelHelper, ExportTemplates, USER_IMPORT_COLUMNS, PROJECT_IMPORT_COLUMNS,
)
from app.utils.search_engine import search_engine
from app.utils.redis_cache import redis_client, CacheKeys
from app.crud.user import CollegeCRUD, UserCRUD, OperationLogCRUD
from app.crud.project import ProjectCRUD
from app.services.project_service import ProjectService
from app.services.user_service import ImportResultResponse, UserService
from app.schemas.project import ProjectQueryParams

router_common = APIRouter(prefix="/common", tags=["通用工具"])
router_upload = APIRouter(prefix="/files", tags=["附件管理"])
router_search = APIRouter(prefix="/search", tags=["全文检索"])
router_excel = APIRouter(prefix="/excel", tags=["Excel导入导出"])
router_health = APIRouter(tags=["系统"])


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
    cache_key = CacheKeys.DICT_BY_TYPE.format(dict_type=dict_type)
    cached = redis_client.get_json(cache_key)
    if cached is not None:
        return success(data=cached)
    from app.models import SysDict
    items = db.query(SysDict).filter(
        SysDict.dict_type == dict_type, SysDict.status == 1
    ).order_by(SysDict.sort_order.asc()).all()
    data = [{"code": i.dict_code, "label": i.dict_label, "value": i.dict_value} for i in items]
    redis_client.set_json(cache_key, data, CacheKeys.DICT_TTL)
    return success(data=data)


@router_common.get("/colleges", response_model=ResponseModel, summary="查询学院列表(带缓存)")
def api_college_list_cache(db: Session = Depends(get_db)):
    cached = redis_client.get_json(CacheKeys.COLLEGE_LIST)
    if cached is not None:
        return success(data=cached)
    from app.schemas.user import CollegeResponse
    cols = CollegeCRUD.list_all(db)
    data = [CollegeResponse.model_validate(c).model_dump(mode="json") for c in cols]
    redis_client.set_json(CacheKeys.COLLEGE_LIST, data, CacheKeys.COLLEGE_LIST_TTL)
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


@router_upload.post("/upload", response_model=ResponseModel, summary="单文件上传")
async def api_upload(
    biz_type: str = Form(..., pattern=r"^[a-z_]{1,64}$", description="业务类型: project/expense/achievement/review"),
    biz_id: int = Form(..., ge=1, description="业务记录ID"),
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
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    save_path = os.path.join(settings.UPLOAD_DIR, new_name)
    with open(save_path, "wb") as f:
        f.write(bytes_data)

    # 3. 权限校验：用户是否有权上传到此业务
    # 简化：管理员可传任意；学生仅可传自己是负责人的项目
    if current_user.role != RoleEnum.ADMIN and biz_type in ("project", "achievement"):
        p = ProjectCRUD.get_by_id(db, biz_id)
        if not p:
            raise ResourceNotFoundException(message="业务记录不存在")
        if p.leader_id != current_user.id and p.teacher_id != current_user.id:
            if current_user.role == RoleEnum.STUDENT:
                raise PermissionDeniedException(message="仅项目负责人/指导教师可上传")

    # 4. 入库
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
    return success(data={
        "id": att.id, "file_name": att.file_name, "file_size": att.file_size,
        "file_url": f"/api/files/download/{att.id}",
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
    # 下载权限：管理员可下载；上传者；所属业务可读
    if current_user.role != RoleEnum.ADMIN and att.uploader_id != current_user.id:
        # 仅检查项目类：负责人/老师/成员可下载
        if att.biz_type in ("project", "achievement", "review"):
            p = ProjectCRUD.get_by_id(db, att.biz_id)
            if p:
                ok = (p.leader_id == current_user.id or
                      p.teacher_id == current_user.id)
                if not ok:
                    # 检查是否团队成员
                    from app.models import ProjTeamMember
                    ok = db.query(ProjTeamMember).filter(
                        ProjTeamMember.project_id == p.id,
                        ProjTeamMember.student_id == current_user.id,
                    ).first() is not None
                if not ok:
                    raise PermissionDeniedException(message="无权下载此文件")
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


@router_upload.get("/list/{biz_type}/{biz_id}", response_model=ResponseModel, summary="查询业务下附件列表")
def api_attachment_list(
    biz_type: str, biz_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    items = db.query(SysAttachment).filter(
        SysAttachment.biz_type == biz_type,
        SysAttachment.biz_id == biz_id,
        SysAttachment.is_deleted == 0,
    ).order_by(SysAttachment.created_at.desc()).all()
    data = [{
        "id": a.id, "file_name": a.file_name, "file_size": a.file_size,
        "file_type": a.file_type, "uploader_name": a.uploader_name,
        "download_count": a.download_count,
        "created_at": a.created_at,
        "download_url": f"/api/files/download/{a.id}",
    } for a in items]
    return success(data=data)


# ====================================================================
# Excel 导入导出
# ====================================================================

@router_excel.get("/template/user", summary="下载-用户批量导入模板")
def api_user_template():
    xlsx = ExcelHelper.generate_template(USER_IMPORT_COLUMNS, sheet_name="用户导入")
    headers = {"Content-Disposition": 'attachment; filename="用户批量导入模板.xlsx"'}
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router_excel.get("/template/project", summary="下载-项目基础信息导入模板")
def api_project_template():
    xlsx = ExcelHelper.generate_template(PROJECT_IMPORT_COLUMNS, sheet_name="项目导入")
    headers = {"Content-Disposition": 'attachment; filename="项目基础信息导入模板.xlsx"'}
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
    # 不分页拉取全部
    pager = PaginationParams(page=1, page_size=10000)
    items, _ = ProjectService.paginate(db, pager, params, data_scope)
    rows = [i.model_dump(mode="python") for i in items]
    xlsx = ExcelHelper.export_list(ExportTemplates.project_list_columns(), rows, sheet_name="项目名单")
    headers = {"Content-Disposition": f'attachment; filename="项目名单_{datetime.now().strftime("%Y%m%d")}.xlsx"'}
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router_excel.get("/export/logs", summary="导出-操作日志(Excel)")
def api_export_logs(
    keyword: Optional[str] = None, module_name: Optional[str] = None,
    operation_type: Optional[str] = None, user_id: Optional[int] = None,
    start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
):
    rows_orm = OperationLogCRUD.list_all_for_export(
        db, keyword=keyword, module_name=module_name,
        operation_type=operation_type, user_id=user_id,
        start_time=start_time, end_time=end_time,
    )
    from app.schemas.user import OperationLogItem
    rows = [OperationLogItem.model_validate(o).model_dump(mode="python") for o in rows_orm]
    xlsx = ExcelHelper.export_list(ExportTemplates.operation_log_columns(), rows, sheet_name="操作日志")
    headers = {"Content-Disposition": f'attachment; filename="操作日志_{datetime.now().strftime("%Y%m%d")}.xlsx"'}
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


# ====================================================================
# 全文检索接口
# ====================================================================
@router_search.get("/projects", response_model=ResponseModel, summary="全文检索-项目")
def api_search_projects(
    keyword: str = Query(..., min_length=1, max_length=128, description="关键词"),
    page: int = 1, page_size: int = 20,
    college_id: Optional[int] = None,
    status: Optional[int] = None,
):
    """Whoosh+Jieba 全文检索，返回含相关性得分与HTML高亮片段"""
    results, total = search_engine.search(
        keyword=keyword, page=page, page_size=page_size,
        filter_college_id=college_id, filter_status=status,
    )
    return success(data=PageResult.create(results, total, page, page_size))


@router_search.post("/rebuild-index", response_model=ResponseModel, summary="重建全文索引(管理员)")
def api_rebuild_index(current_user: SysUser = require_admin):
    total, ok = search_engine.rebuild_all()
    return success(data={"total_projects": total, "indexed": ok},
                   message=f"索引重建完成：共{total}条，成功{ok}条")
