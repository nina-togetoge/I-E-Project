"""
通用接口路由：附件上传/下载、Excel导入导出模板、字典、健康检查
"""
# ====================================================================
# 通用工具路由（跨业务的公共能力）
# ----------------------------------------------------------------------------
# 对外接口分组：
#   /api/common   GET /dict/{dict_type} 按类型查系统字典（Redis 缓存）；
#                 GET /colleges 学院列表（带缓存）
#   /api/files    POST /upload 单文件上传、GET /download/{id} 下载（计数）、
#                 GET /preview/{id} 在线预览（docx 转 HTML）、
#                 GET /img/{id} 富文本内嵌图片（签名直链、免登录）、
#                 GET /list/{biz_type}/{biz_id} 业务附件列表、
#                 DELETE /{id} 软删附件
#   /api/excel    GET /template/user|project 下载导入模板、
#                 POST /import/user 批量导入用户、
#                 GET /export/projects 导出项目名单、GET /export/logs 导出操作日志
#   /health、/api/health 健康检查（探针用，不进 OpenAPI 文档）
# 前端对应：全局附件上传组件、富文本编辑器插图、管理端导入导出、登录页健康探针。
# 依赖：ExcelHelper（模板与解析）、UserService（批量建号）、ProjectService（导出复用列表权限）、
#       OperationLogCRUD（日志导出）、redis_client（字典/学院缓存）、ArchiveService 无直接依赖。
# 关键权限约束：
#   - 字典/学院/健康检查为登录后或公开只读，不含敏感信息；
#   - 附件访问统一走 _ensure_biz_access：管理员、上传者、项目负责人/指导教师/成员、
#     报销申请人与本院教师可读，其余拒绝；临时附件(biz_id=0)仅上传者可见；
#   - /api/files/img/{id} 是富文本直链，无法带 Token，改用 HMAC 签名且仅限图片扩展名；
#   - 用户导入与日志导出需管理员；学院管理员导出日志时强制只看本院。
# 特殊业务规则：
#   - 文件实体存 Docker 卷，DB 的 sys_attachment.file_path 仅记录路径；
#   - 上传先校验权限再落盘，避免越权请求产生孤儿文件；
#   - 下载计数使用原子自增；预览 docx 解析失败自动回退原文件；
#   - 项目导出上限 2000 条，避免一次性拉爆数据库与内存；
#   - 附件删除为软删；项目附件仅在草稿(0)/已驳回(10)可删，与编辑窗口一致。
# ====================================================================
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
from sqlalchemy import func
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
# --- 接口说明 ---
# URL: GET /health（以及别名 GET /api/health，别名不进 OpenAPI 文档）
# 调用方: 负载均衡/容器探针/前端启动检测，无需登录。
# 入参: 无。
# 返回: 应用名、版本、status="ok"、服务器当前时间。
# 异常: 无业务异常；仅进程不可用时探针失败。
# 副作用: 只读；不查数据库/Redis，避免依赖故障导致健康检查误判。
def api_health():
    # 1. 返回最小可用信息，供探针判断进程存活
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
# --- 接口说明 ---
# URL: GET /api/common/dict/{dict_type}
# 调用方: 已登录用户（前端下拉框/枚举翻译）。
# 入参: dict_type 字典类型编码（路径参数）。
# 返回: [{code 编码, label 展示名, value 实际值}]，按 sort_order 升序。
# 权限: 无额外行级限制，仅返回 status=1（启用）的字典项。
# 异常: Redis 不可用时静默降级为直接查库，不影响接口可用性。
# 副作用: 未命中缓存会回写 Redis（TTL 由 CacheKeys.DICT_TTL 控制）。
def api_get_dict(dict_type: str, db: Session = Depends(get_db)):
    """优先Redis缓存，未命中则查库并写入缓存"""
    # 1. 先读缓存；缓存异常（如 Redis 抖动）直接跳过，保证字典接口始终可用
    try:
        cache_key = CacheKeys.DICT_BY_TYPE.format(dict_type=dict_type)
        cached = redis_client.get_json(cache_key)
        if cached is not None:
            return success(data=cached)
    except Exception:
        pass
    # 2. 缓存未命中：只查启用的字典项，按展示顺序排序
    from app.models import SysDict
    items = db.query(SysDict).filter(
        SysDict.dict_type == dict_type, SysDict.status == 1
    ).order_by(SysDict.sort_order.asc()).all()
    # 3. 精简为前端直接消费的结构，避免暴露表内无关字段
    data = [{"code": i.dict_code, "label": i.dict_label, "value": i.dict_value} for i in items]
    # 4. 回写缓存；失败不影响本次响应
    try:
        redis_client.set_json(cache_key, data, CacheKeys.DICT_TTL)
    except Exception:
        pass
    return success(data=data)


@router_common.get("/colleges", response_model=ResponseModel, summary="查询学院列表(带缓存)")
# --- 接口说明 ---
# URL: GET /api/common/colleges
# 调用方: 已登录用户（注册/申报/筛选等学院下拉框）。
# 入参: 无。
# 返回: CollegeResponse 列表（学院编码、名称、状态等）。
# 权限: 只读公共数据，无角色限制。
# 异常: Redis 异常静默降级查库；数据库异常由全局异常处理。
# 副作用: 未命中缓存时回写 Redis（COLLEGE_LIST_TTL）；用户导入成功后会主动清除该缓存。
def api_college_list_cache(db: Session = Depends(get_db)):
    # 1. 先读缓存，异常时降级为查库
    try:
        cached = redis_client.get_json(CacheKeys.COLLEGE_LIST)
        if cached is not None:
            return success(data=cached)
    except Exception:
        pass
    # 2. 查全部学院并序列化为 JSON 兼容结构（日期等字段统一转字符串）
    from app.schemas.user import CollegeResponse
    cols = CollegeCRUD.list_all(db)
    data = [CollegeResponse.model_validate(c).model_dump(mode="json") for c in cols]
    # 3. 回写缓存，供后续高频下拉请求复用
    try:
        redis_client.set_json(CacheKeys.COLLEGE_LIST, data, CacheKeys.COLLEGE_LIST_TTL)
    except Exception:
        pass
    return success(data=data)


# ====================================================================
# 附件上传/下载
# ====================================================================
def _secure_filename(filename: str) -> str:
    """安全化文件名：保留原扩展名，用UUID重命名避免覆盖/路径穿越

    参数:
        filename: 浏览器上传的原始文件名，可能含中文、路径片段或空值。
    返回:
        形如 ``20261024_<uuid>.<ext>`` 的落盘文件名；不保留用户可控的主干部分。
    异常:
        扩展名不在 settings.ALLOWED_EXTENSIONS_LIST 白名单 -> 参数校验异常。
    安全说明:
        - 只取扩展名，彻底丢弃原始路径与主干，避免 ``../`` 路径穿越与同名覆盖；
        - 日期前缀便于按天归档与人工排查，UUID 保证并发上传不冲突。
    """
    # 1. 取小写扩展名并按白名单校验（图片/文档/压缩包等由配置集中维护）
    ext = os.path.splitext(filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS_LIST:
        raise ParamValidateException(message=f"不允许的文件类型，仅支持 {settings.ALLOWED_EXTENSIONS}")
    # 2. 用“日期 + UUID”重新命名：不保留用户输入，规避路径穿越与覆盖
    return f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex}{ext}"


# 富文本内嵌图片允许的扩展名（仅图片，且不含 svg 以免脚本注入）
_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}


def _image_sig(att_id: int) -> str:
    """为内嵌图片生成长期有效的签名。

    富文本里的 <img> 无法携带 Authorization 头，因此图片直链改为签名访问：
    签名由密钥派生、不随登录令牌过期，内容页可长期正常显示。

    参数:
        att_id: 附件主键；签名只绑定附件 id，不绑定用户，因为浏览者可能未登录。
    返回:
        32 位十六进制签名（HMAC-SHA256 截断）。
    安全说明:
        - 使用服务端 JWT 密钥做 HMAC，攻击者无法在不知道密钥的情况下伪造；
        - 仅用于图片（调用方校验扩展名），避免签名接口被当成任意文件下载通道。
    """
    # 1. 用服务端密钥对固定前缀 + 附件 id 计算 HMAC，截断到 32 位便于放入 URL
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(), f"files-img:{att_id}".encode(), hashlib.sha256
    ).hexdigest()[:32]


def _resolve_biz_project(db: Session, biz_type: str, biz_id: int):
    """把附件所属业务记录解析为对应的项目对象；无法解析时返回 None。

    注意：不同业务表的 biz_id 语义不同（project 用项目ID，achievement 用成果ID，
    expense 用报销ID，review 用审核记录ID），必须分别解析，不能统一当项目ID 处理。

    参数:
        biz_type: 业务类型标识（project/achievement/midterm/expense/review）。
        biz_id: 业务记录主键；<=0 表示临时附件，直接视为无归属。
    返回:
        对应 ProjProject 或 None（记录不存在/已软删/未知 biz_type）。
    设计原因:
        附件权限最终都要落到“项目相关方”判断，因此统一解析出项目对象，
        而不是在每个接口里重复写各业务表查询。
    """
    # 1. 临时附件（biz_id=0）没有归属项目，交由调用方按上传者判断
    if not biz_id or biz_id <= 0:
        return None
    # 2. 项目附件：biz_id 就是项目主键
    if biz_type == "project":
        return ProjectCRUD.get_by_id(db, biz_id)
    # 3. 成果附件：先取成果再回溯项目，成果缺失或软删返回 None
    if biz_type == "achievement":
        from app.models import ProjAchievement
        ach = db.query(ProjAchievement).filter(
            ProjAchievement.id == biz_id, ProjAchievement.is_deleted == 0
        ).first()
        return ProjectCRUD.get_by_id(db, ach.project_id) if ach else None
    # 4. 中期检查附件：同样回溯到所属项目
    if biz_type == "midterm":
        from app.models import ProjMidtermCheck
        mid = db.query(ProjMidtermCheck).filter(
            ProjMidtermCheck.id == biz_id, ProjMidtermCheck.is_deleted == 0
        ).first()
        return ProjectCRUD.get_by_id(db, mid.project_id) if mid else None
    # 5. 报销附件：回溯项目，后续权限还会额外放行申请人与本院教师
    if biz_type == "expense":
        from app.models import ProjExpense
        exp = db.query(ProjExpense).filter(
            ProjExpense.id == biz_id, ProjExpense.is_deleted == 0
        ).first()
        return ProjectCRUD.get_by_id(db, exp.project_id) if exp else None
    # 6. 审核记录附件：回溯项目（审核人提交的佐证材料）
    if biz_type == "review":
        from app.models import ProjReview
        rv = db.query(ProjReview).filter(
            ProjReview.id == biz_id, ProjReview.is_deleted == 0
        ).first()
        return ProjectCRUD.get_by_id(db, rv.project_id) if rv else None
    # 7. 未知业务类型不授予任何项目归属，调用方会按无权处理
    return None


def _ensure_biz_access(db: Session, biz_type: str, biz_id: int, user: SysUser,
                       allow_uploader_id: Optional[int] = None) -> None:
    """统一校验用户对某业务记录附件的访问/上传权限。

    放行条件：管理员；上传者本人(下载场景)；项目负责人/指导教师/团队成员；
    报销场景下额外的报销申请人或本院教师、学院管理员。其余一律拒绝。

    参数:
        biz_type / biz_id: 附件所属业务与业务主键；biz_id=0 为临时附件。
        user: 当前登录用户。
        allow_uploader_id: 附件上传者 id；仅下载/预览/删除场景传入，用于放行本人。
    异常:
        无任何放行条件命中 -> PermissionDeniedException（403）。
    注意:
        - 学院管理员不是“全院任意文件”通行证：只放行本院项目附件；
        - 上传场景不传 allow_uploader_id，因此必须先有业务归属才能上传；
        - 权限判断顺序按“成本从低到高”排列，避免每个请求都查项目与成员表。
    """
    # 1. 管理员分支：真超管（college_id 为空）全放行；学院管理员限本院
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
    # 2. 非管理员：上传者本人可直接访问自己的文件（含临时附件）
    if allow_uploader_id is not None and allow_uploader_id == user.id:
        return
    # 3. 解析业务归属项目；无法解析说明临时附件或脏数据，直接拒绝
    project = _resolve_biz_project(db, biz_type, biz_id)
    if project is None:
        raise PermissionDeniedException(message="无权访问该业务文件")
    # 4. 项目负责人与指导教师天然可见
    if project.leader_id == user.id or project.teacher_id == user.id:
        return
    # 5. 报销附件额外放行申请人，以及本院教师/学院管理员（财务审核需要）
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
    # 6. 团队成员（学生成员）也可访问项目附件
    from app.models import ProjTeamMember
    is_member = db.query(ProjTeamMember).filter(
        ProjTeamMember.project_id == project.id,
        ProjTeamMember.student_id == user.id,
    ).first() is not None
    if is_member:
        return
    # 7. 以上均不满足则拒绝
    raise PermissionDeniedException(message="无权访问该业务文件")


@router_upload.post("/upload", response_model=ResponseModel, summary="单文件上传")
# --- 接口说明 ---
# URL: POST /api/files/upload（multipart/form-data）
# 调用方: 已登录用户。
# 入参:
#   biz_type: 业务类型 project/expense/achievement/review（正则限制小写与下划线）；
#   biz_id: 业务记录 id，0 表示临时上传，待后续业务保存时再绑定；
#   file: 上传文件。
# 返回: {id, file_name, file_size, file_url 下载地址, image_url 图片签名直链（非图片为 null）}。
# 权限: biz_id>0 时走 _ensure_biz_access；biz_id=0 仅要求登录，文件归属上传者。
# 异常: 超过 MAX_UPLOAD_SIZE -> 400；扩展名不在白名单 -> 400；越权 -> 403。
# 副作用: 先写磁盘（UPLOAD_DIR/Docker 卷）再写 sys_attachment；记录操作日志。
# 注意: 先校验权限再落盘，避免越权请求留下无人认领的孤儿文件。
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
    # 目录可能因新部署尚不存在，先确保存在；文件名已由 UUID 重命名，无路径穿越风险
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    save_path = os.path.join(settings.UPLOAD_DIR, new_name)
    with open(save_path, "wb") as f:
        f.write(bytes_data)

    # 5. 入库
    # 数据库只保存相对/容器内路径，实体文件在 Docker 卷；同时记录原始文件名供展示
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
    # 6. 审计日志：记录文件名与归属业务，便于追溯上传行为
    with ctx:
        ctx.set_desc(f"上传附件[{file.filename}]到{biz_type}#{biz_id}")
    # 7. 图片额外返回签名直链，供富文本编辑器立即插入预览；非图片为 None
    image_url = None
    if ext.lstrip(".").lower() in _IMAGE_EXTS:
        image_url = f"/api/files/img/{att.id}?sig={_image_sig(att.id)}"
    return success(data={
        "id": att.id, "file_name": att.file_name, "file_size": att.file_size,
        "file_url": f"/api/files/download/{att.id}",
        "image_url": image_url,
    })


@router_upload.get("/download/{att_id}", summary="下载附件（权限校验+计数）")
# --- 接口说明 ---
# URL: GET /api/files/download/{att_id}
# 调用方: 已登录用户（附件所属业务相关人）。
# 入参: att_id 附件主键。
# 返回: 文件二进制流（FileResponse），Content-Disposition 带 UTF-8 中文文件名。
# 权限: _ensure_biz_access，并额外放行上传者本人。
# 异常: 附件不存在/已软删 -> 404；物理文件丢失 -> 404；无权 -> 403。
# 副作用: 下载计数 +1（SQL 原子自增，synchronize_session=False 避免 ORM 全表同步）。
# 注意: media_type 优先取上传时记录的 MIME，其次按文件名推断，最后回退二进制流。
def api_download(
    att_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 查询未软删附件记录
    att = db.query(SysAttachment).filter(SysAttachment.id == att_id, SysAttachment.is_deleted == 0).first()
    if not att:
        raise ResourceNotFoundException(message="文件不存在")
    # 下载权限：管理员/上传者/所属业务相关人（统一校验）
    # 2. 统一权限校验：下载场景传入 uploader_id，允许本人访问自己的临时附件
    _ensure_biz_access(db, att.biz_type, att.biz_id or 0, current_user,
                       allow_uploader_id=att.uploader_id)
    # 3. 数据库有记录但磁盘文件被清理时，明确提示而不是返回空文件
    if not os.path.exists(att.file_path):
        raise ResourceNotFoundException(message="服务器上文件已丢失")

    # 下载计数+1（原子自增，避免并发下载相互覆盖计数）
    # 4. 在数据库侧完成 +1，避免“读-改-写”竞态导致计数丢失
    db.query(SysAttachment).filter(SysAttachment.id == att.id).update(
        {SysAttachment.download_count: func.coalesce(SysAttachment.download_count, 0) + 1},
        synchronize_session=False,
    )
    db.commit()

    # 解析MIME，PDF/图片等浏览器支持预览
    # 5. 确定响应类型：优先 upload 时记录的 content_type，避免误判
    mime = att.file_type or mimetypes.guess_type(att.file_name)[0] or "application/octet-stream"
    # 中文文件名URL编码
    # 6. RFC 6266：filename* 使用 UTF-8 编码，保证中文文件名在各浏览器正常
    import urllib.parse
    fname_encode = urllib.parse.quote(att.file_name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{fname_encode}",
    }
    # 7. attachment 模式强制下载（预览走 /preview 接口）
    return FileResponse(path=att.file_path, media_type=mime, filename=att.file_name, headers=headers)


_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_to_html(path: str, filename: str) -> Optional[str]:
    """把 .docx 解析为可读 HTML（仅用标准库），供浏览器在线预览。

    浏览器无法内联渲染 docx，直接返回文件会触发下载；这里提取段落与表格，
    失败时返回 None，由调用方回退为原始文件响应。
    """
    try:
        # 1. docx 本质是 zip，正文位于 word/document.xml；读取失败说明文件损坏或非 docx
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
        body = ET.fromstring(xml_bytes).find(f"{_DOCX_NS}body")
    except Exception:
        return None
    if body is None:
        return None

    # 2. 逐块转换：段落转 <p>/<h*>，表格转 <table>，其余节点（分节符等）忽略
    blocks = []
    for node in body:
        if node.tag == f"{_DOCX_NS}p":
            # 2.1 提取段落内所有文本片段（含 run），空段落直接跳过
            text = "".join(t.text or "" for t in node.iter(f"{_DOCX_NS}t"))
            if not text.strip():
                continue
            style = ""
            ppr = node.find(f"{_DOCX_NS}pPr")
            if ppr is not None:
                st = ppr.find(f"{_DOCX_NS}pStyle")
                if st is not None:
                    style = (st.get(f"{_DOCX_NS}val") or "").lower()
            # 2.2 标题样式映射为 h1~h4（受 HTML 语义层数限制，最多 4 级）
            if style.startswith("heading") or style.startswith("标题"):
                try:
                    level = min(int(style.replace("heading", "")) + 1, 4)
                except ValueError:
                    level = 2
                blocks.append(f"<h{level}>{_html_escape(text)}</h{level}>")
            else:
                # 2.3 普通段落；文本统一转义，防止文档内容注入 HTML/脚本
                blocks.append(f"<p>{_html_escape(text)}</p>")
        elif node.tag == f"{_DOCX_NS}tbl":
            # 2.4 表格：逐行逐单元格拼接，单元格文本同样转义
            rows = []
            for tr in node.findall(f"{_DOCX_NS}tr"):
                cells = []
                for tc in tr.findall(f"{_DOCX_NS}tc"):
                    cell_text = "".join(t.text or "" for t in tc.iter(f"{_DOCX_NS}t"))
                    cells.append(f"<td>{_html_escape(cell_text)}</td>")
                rows.append("<tr>" + "".join(cells) + "</tr>")
            if rows:
                blocks.append("<table>" + "".join(rows) + "</table>")

    # 3. 完全无内容时返回 None，交由调用方回退为原始文件下载
    if not blocks:
        return None
    # 4. 组装自包含的 HTML 页面（内联样式），前端 iframe/新窗口直接可读
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
# --- 接口说明 ---
# URL: GET /api/files/preview/{att_id}
# 调用方: 已登录用户（附件所属业务相关人）。
# 入参: att_id 附件主键。
# 返回: 浏览器可直接渲染的内容（HTMLResponse 或 inline FileResponse）。
# 权限: 与下载一致（_ensure_biz_access + 上传者本人）。
# 异常: 附件不存在 -> 404；物理文件丢失 -> 404；无权 -> 403。
# 副作用: 只读，不增加下载计数（预览与下载分开统计）。
# 特殊处理: docx 由标准库解析成 HTML；解析失败或非 docx 回退为 inline 原始文件，
#           由浏览器决定是否内置预览（PDF/图片通常可预览，Office 文件可能触发下载）。
def api_preview(
    att_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 查询附件并做存在性校验
    att = db.query(SysAttachment).filter(SysAttachment.id == att_id, SysAttachment.is_deleted == 0).first()
    if not att:
        raise ResourceNotFoundException(message="文件不存在")
    # 预览权限：与下载权限一致（统一校验）
    # 2. 权限校验
    _ensure_biz_access(db, att.biz_type, att.biz_id or 0, current_user,
                       allow_uploader_id=att.uploader_id)
    # 3. 物理文件丢失时明确报错
    if not os.path.exists(att.file_path):
        raise ResourceNotFoundException(message="服务器上文件已丢失")

    # 4. 取扩展名：优先数据库记录，兼容早期未写 file_ext 的数据
    ext = (att.file_ext or os.path.splitext(att.file_name)[1].lstrip(".")).lower().lstrip(".")
    # Word 文档浏览器无法内联渲染，转 HTML 预览；解析失败则回退原始文件
    if ext == "docx":
        html = _docx_to_html(att.file_path, att.file_name)
        if html:
            return HTMLResponse(content=html, headers={"Content-Disposition": "inline"})

    # 5. 其余类型按 MIME 内联返回，不做强制下载
    mime = att.file_type or mimetypes.guess_type(att.file_name)[0] or "application/octet-stream"
    # inline 模式：浏览器直接展示而非下载
    return FileResponse(path=att.file_path, media_type=mime, headers={"Content-Disposition": "inline"})


@router_upload.get("/img/{att_id}", summary="富文本内嵌图片（签名直链，免登录）")
# --- 接口说明 ---
# URL: GET /api/files/img/{att_id}?sig={signature}
# 调用方: 浏览器 <img> 标签直接访问，故意免登录（无法携带 Authorization 头）。
# 入参: att_id 附件主键；sig 由上传/查询接口下发的 HMAC 签名。
# 返回: 图片二进制流，inline 展示，Cache-Control 缓存 1 天。
# 权限: 不校验登录态，改用签名校验；且仅允许 _IMAGE_EXTS 中的图片扩展名。
# 异常: 附件不存在/非图片 -> 404（不暴露“存在但类型不符”）；签名错误 -> 403。
# 副作用: 只读。
# 安全说明: 与 svg 一并禁用、签名常量时间比较，避免该接口退化为任意文件直链。
def api_embed_image(
    att_id: int,
    sig: str = Query(..., description="图片签名"),
    db: Session = Depends(get_db),
):
    """供富文本 <img src> 使用：<img> 无法携带令牌，改用长期有效的签名校验。

    仅允许图片扩展名，避免把该接口变成任意附件下载通道。
    """
    # 1. 查询未软删附件
    att = db.query(SysAttachment).filter(
        SysAttachment.id == att_id, SysAttachment.is_deleted == 0
    ).first()
    # 2. 仅图片可走直链；非图片与不存在同样返回 404，避免探测附件是否存在
    ext = (att.file_ext or "").lower().lstrip(".") if att else ""
    if not att or ext not in _IMAGE_EXTS:
        raise ResourceNotFoundException(message="图片不存在")
    # 3. 常量时间比较签名，避免时序侧信道；签名不匹配直接 403
    if not hmac.compare_digest(sig, _image_sig(att_id)):
        raise PermissionDeniedException(message="图片链接无效")
    # 4. 物理文件需存在，否则明确 404
    if not os.path.exists(att.file_path):
        raise ResourceNotFoundException(message="服务器上文件已丢失")

    # 5. MIME 优先使用记录的 image/*，否则按文件名推断；inline + 长缓存适合富文本重复展示
    mime = att.file_type if (att.file_type or "").startswith("image/") \
        else mimetypes.guess_type(att.file_name)[0] or "application/octet-stream"
    return FileResponse(
        path=att.file_path, media_type=mime,
        headers={"Content-Disposition": "inline", "Cache-Control": "public, max-age=86400"},
    )


@router_upload.get("/list/{biz_type}/{biz_id}", response_model=ResponseModel, summary="查询业务下附件列表")
# --- 接口说明 ---
# URL: GET /api/files/list/{biz_type}/{biz_id}
# 调用方: 已登录用户。
# 入参: biz_type 业务类型；biz_id 业务记录 id；biz_id=0 查临时附件。
# 返回: 附件数组（id、文件名、大小、类型、上传人、下载次数、创建时间、下载地址）。
# 权限:
#   - biz_id>0：_ensure_biz_access 校验业务归属；
#   - biz_id=0：非管理员只能看到自己上传的临时附件，管理员可见全部。
# 异常: 无权 -> 403；业务类型非法不报错，只是查不到数据。
# 副作用: 只读；按创建时间倒序，最新上传排前面。
def api_attachment_list(
    biz_type: str, biz_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 权限校验：已有业务记录按归属校验；临时附件(biz_id=0)仅本人可见
    # 1. 基础查询：限定业务类型 + 业务 id + 未软删
    q = db.query(SysAttachment).filter(
        SysAttachment.biz_type == biz_type,
        SysAttachment.biz_id == biz_id,
        SysAttachment.is_deleted == 0,
    )
    # 2. 正式业务附件走统一权限；临时附件对非管理员追加上传者过滤
    if biz_id > 0:
        _ensure_biz_access(db, biz_type, biz_id, current_user)
    elif current_user.role != RoleEnum.ADMIN:
        q = q.filter(SysAttachment.uploader_id == current_user.id)
    # 3. 最新上传优先，前端附件列表直接按此顺序展示
    items = q.order_by(SysAttachment.created_at.desc()).all()
    # 4. 只暴露前端需要的字段，下载地址统一指向受权限保护的下载接口
    data = [{
        "id": a.id, "file_name": a.file_name, "file_size": a.file_size,
        "file_type": a.file_type, "uploader_name": a.uploader_name,
        "download_count": a.download_count,
        "created_at": a.created_at,
        "download_url": f"/api/files/download/{a.id}",
    } for a in items]
    return success(data=data)


@router_upload.delete("/{att_id}", response_model=ResponseModel, summary="删除附件（软删除）")
# --- 接口说明 ---
# URL: DELETE /api/files/{att_id}
# 调用方: 已登录用户；实际仅上传者本人或系统管理员。
# 入参: att_id 附件主键。
# 返回: {"id": att_id}。
# 权限: 上传者本人或 ADMIN；其余一律 403。
# 异常: 附件不存在 -> 404；无权 -> 403；项目附件所在项目状态不允许 -> 400。
# 副作用: 软删附件（is_deleted=1），磁盘文件保留（便于审计/误删恢复）；
#         记录操作日志。
# 特殊规则: 已绑定项目的附件仅在项目状态 0草稿 / 10已驳回 时允许删除，
#           与前端“编辑项目”窗口的可操作范围保持一致；其他状态需走变更流程。
def api_delete_attachment(
    att_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 查询未软删附件
    att = db.query(SysAttachment).filter(
        SysAttachment.id == att_id, SysAttachment.is_deleted == 0
    ).first()
    if not att:
        raise ResourceNotFoundException(message="文件不存在")
    # 权限：仅上传者本人或系统管理员可删除
    # 2. 删除权比查看权更窄：业务相关人也不能删别人的材料，只认上传者或管理员
    if current_user.role != RoleEnum.ADMIN and att.uploader_id != current_user.id:
        raise PermissionDeniedException(message="无权删除该附件")
    # 已绑定项目的附件：仅当项目处于可编辑状态（草稿/已驳回）时允许删除，与编辑弹窗保持一致
    # 3. 项目进入审核后材料已冻结，删除会破坏审核依据，因此按状态拦截
    if att.biz_type == "project" and att.biz_id and att.biz_id > 0:
        project = _resolve_biz_project(db, att.biz_type, att.biz_id)
        if project is not None and project.status not in (0, 10):
            raise ParamValidateException(message="当前项目状态不可删除附件")
    # 4. 软删并落库；物理文件保留，以便审计追踪或误删恢复
    att.is_deleted = 1
    db.commit()
    # 5. 审计日志记录被删文件名
    with ctx:
        ctx.set_desc(f"删除附件[{att.file_name}]")
    return success(data={"id": att_id})


# ====================================================================
# Excel 导入导出
# ====================================================================

@router_excel.get("/template/user", summary="下载-用户批量导入模板")
# --- 接口说明 ---
# URL: GET /api/excel/template/user
# 调用方: 未登录也可下载（模板不含敏感数据，便于提前准备）。
# 入参: 无。
# 返回: 用户批量导入模板 xlsx 流。
# 异常: Excel 生成失败由全局异常处理。
# 副作用: 只读；列定义来自 USER_IMPORT_COLUMNS，与导入解析保持同一份配置。
def api_user_template():
    # 1. 按统一的列定义生成空模板，保证模板与后端解析字段完全一致
    xlsx = ExcelHelper.generate_template(USER_IMPORT_COLUMNS, sheet_name="用户导入")
    # 2. 中文文件名做 RFC 6266 编码，避免下载时乱码
    headers = _attachment_header("用户批量导入模板.xlsx")
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


# --- 接口说明 ---
# URL: GET /api/excel/template/project
# 调用方: 未登录也可下载。
# 入参: 无。
# 返回: 项目基础信息导入模板 xlsx 流。
# 异常: 生成失败由全局异常处理。
# 副作用: 只读；列定义来自 PROJECT_IMPORT_COLUMNS。
@router_excel.get("/template/project", summary="下载-项目基础信息导入模板")
def api_project_template():
    # 1. 生成项目导入空模板，列顺序与解析逻辑共享配置
    xlsx = ExcelHelper.generate_template(PROJECT_IMPORT_COLUMNS, sheet_name="项目导入")
    headers = _attachment_header("项目基础信息导入模板.xlsx")
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


@router_excel.post("/import/user", response_model=ResponseModel[ImportResultResponse],
                   summary="上传-批量导入用户(Excel)")
# --- 接口说明 ---
# URL: POST /api/excel/import/user（multipart/form-data）
# 调用方: 管理员（require_admin）；学生/教师/专家 403。
# 入参: file 按用户导入模板填写的 xlsx。
# 返回: ImportResultResponse（total 总行数、success 成功数、failed 失败数、errors 明细）。
# 权限: 管理员；服务层再按超管/学院管理员限制可创建的角色与学院范围。
# 异常: 文件无法解析/列缺失 -> 返回解析错误明细（HTTP 仍成功）；数据库冲突按行汇总。
# 副作用: 批量创建用户（密码哈希落库）、写操作日志；成功后清除学院列表缓存，
#         保证后续下拉立即看到最新学院数据。
# 注意: 解析出错误时不落库，直接返回成功/失败统计，避免“部分导入”难以回滚。
async def api_import_users(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: SysUser = require_admin,
    ctx: OperationContext = Depends(),
):
    # 1. 读取整个 Excel 并在内存中解析为模板列对应的行数据
    raw = await file.read()
    rows, errors = ExcelHelper.parse_workbook(raw, USER_IMPORT_COLUMNS)
    # 2. 全文件校验失败（缺列/格式错）时不进入写库，直接反馈错误明细
    if errors:
        return success(data=ImportResultResponse(
            total=len(rows) + len(errors), success=len(rows), failed=len(errors), errors=errors
        ))
    # 3. 逐行创建用户；服务层负责角色/学院权限与重复账号校验
    with ctx:
        ctx.set_desc(f"批量导入用户{len(rows)}人")
        result = UserService.batch_create(db, rows, current_user)
    # 4. 学院/用户缓存可能因导入而变化，主动失效避免前端读到旧数据
    redis_client.delete(CacheKeys.COLLEGE_LIST)
    return success(data=result, message="导入完成")


@router_excel.get("/export/projects", summary="导出-项目名单(Excel)")
# --- 接口说明 ---
# URL: GET /api/excel/export/projects
# 调用方: 已登录用户（管理端导出为主）。
# 入参: params(ProjectQueryParams) 与项目列表完全相同的筛选条件；分页参数被忽略。
# 返回: 项目名单 xlsx 文件流。
# 权限: 复用 ProjectService.paginate + DataScope，导出的数据范围与列表一致，
#       防止通过导出绕过行级权限拿到全校数据。
# 异常: 参数非法 -> 422；Excel 生成失败由全局异常处理。
# 副作用: 只读。
# 特殊规则: 单次最多导出 2000 条（page_size 固定），避免大结果集拉爆数据库与内存。
def api_export_projects(
    params: ProjectQueryParams = Depends(),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    # [P1-7] 导出上限收紧：一次最多导出 2000 条（原 10000 过大，拉爆DB/内存）
    # 1. 固定第一页 2000 条，作为导出上限；超出部分需缩小筛选条件
    pager = PaginationParams(page=1, page_size=2000)
    # 2. 与列表接口共用查询与权限逻辑，保证“看到的”和“导出的”一致
    items, _ = ProjectService.paginate(db, pager, params, data_scope)
    # 3. 转为普通 dict 供 Excel 模板按列取值
    rows = [i.model_dump(mode="python") for i in items]
    xlsx = ExcelHelper.export_list(ExportTemplates.project_list_columns(), rows, sheet_name="项目名单")
    # 4. 文件名带导出日期，便于区分多次导出
    headers = _attachment_header(f'项目名单_{datetime.now().strftime("%Y%m%d")}.xlsx')
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )


# --- 接口说明 ---
# URL: GET /api/excel/export/logs
# 调用方: 管理员（require_admin）；学院管理员仅能导出本院日志。
# 入参: keyword 关键词、module_name/operation_type 单值、modules/operation_types/user_roles/statuses
#       多值（逗号分隔）、user_id、start_time/end_time 时间区间。
# 返回: 操作日志 xlsx 文件流。
# 权限: 真超管（role=4 且无 college_id）导出全部；学院管理员强制附加本院 college_id，
#       防止其通过不传学院参数越权导出全校日志。
# 异常: 时间格式非法 -> 422；Excel 生成失败由全局异常处理。
# 副作用: 只读；导出行为本身由 OperationLogCRUD 读取，不会再次写日志（避免递归）。
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
    # 1. 计算学院过滤条件：非真超管强制限定到本人学院
    college_id = None if is_super_admin(current_user) else current_user.college_id
    # 2. 按筛选条件一次性取日志（导出场景不分页，由 CRUD 控制上限）
    rows_orm = OperationLogCRUD.list_all_for_export(
        db, keyword=keyword, module_name=module_name,
        operation_type=operation_type, user_id=user_id,
        college_id=college_id,
        start_time=start_time, end_time=end_time,
        modules=modules, operation_types=operation_types,
        user_roles=user_roles, statuses=statuses,
    )
    # 3. 统一走 OperationLogItem 序列化，保证导出列与接口字段一致
    from app.schemas.user import OperationLogItem
    rows = [OperationLogItem.model_validate(o).model_dump(mode="python") for o in rows_orm]
    # 4. 生成带日期的 xlsx 并流式下载
    xlsx = ExcelHelper.export_list(ExportTemplates.operation_log_columns(), rows, sheet_name="操作日志")
    headers = _attachment_header(f'操作日志_{datetime.now().strftime("%Y%m%d")}.xlsx')
    return StreamingResponse(
        iter([xlsx]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )
