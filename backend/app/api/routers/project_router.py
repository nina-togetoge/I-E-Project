"""
项目申报模块 API 路由层
"""
# ====================================================================
# 项目申报 / 成果 / 统计路由
# ----------------------------------------------------------------------------
# 对外接口分组：
#   /api/projects     GET "" 项目列表、GET /announcement/list 立项公示、
#                      GET /{id} 详情、GET /{id}/archive 结项归档 ZIP、
#                      POST "" 存草稿、POST /submit-draft 创建即提交、
#                      PUT /{id} 修改、POST /{id}/submit 提交审核、
#                      POST /{id}/withdraw 撤回、POST /{id}/submit-final 提交结题报告、
#                      POST /{id}/withdraw-final 撤回结题报告、DELETE /{id} 软删
#   /api/achievements GET /by-project/{id} 成果列表、POST "" 登记、
#                      PUT /{pk} 编辑、POST /{pk}/review 认定、
#                      POST /{pk}/revoke 撤销认定、DELETE /{pk} 删除
#   /api/statistics   GET /overview 总览、GET /trend 月度趋势、
#                      GET /college-breakdown 学院维度统计
# 前端对应：学生「我的项目/项目详情/成果登记」、公示页、管理端「项目库/统计大屏」。
# 依赖 Service：ProjectService（申报状态机与数据权限）、AchievementService（成果认定）、
#               ArchiveService（结题归档打包）。
# 权限约束：
#   - 列表/统计由 DataScope 注入行级范围：超管全校、学院管理员本院、教师本院、
#     学生本人负责/参与、专家被分配项目；
#   - 创建/提交/撤回/结项报告仅学生与管理员（RequireRole），服务层再校验负责人归属；
#   - 详情复用 ProjectService.get_detail 的可见性规则；
#   - 归档仅已结题(9)项目可导出，并复用详情权限。
# 项目状态机：
#   0草稿 / 1待学院初审 / 3待校级复审 / 5待专家评审 / 6已立项 / 7中期检查中 /
#   8待结题 / 9已结题 / 10已驳回 / 11已撤销 / 12待指导教师确认 / 13待分配评审专家。
# 特殊业务规则：
#   - 提交审核会重置整条审核链（软删旧记录、重建教师确认占位、首次分配项目编号）；
#   - 仅「待指导教师确认(12)」可撤回，进入学院初审后不可撤回；
#   - 结题报告提交受截止日限制，但驳回后本轮重提不受截止日限制；
#   - 提交结题报告只登记报告，项目保持 8，必须由被分配专家验收后才变 9；
#   - 详情读取会惰性清扫超期变更/中期/结题，可能把项目自动置为已撤销(11)；
#   - 成果认定状态：0待认定 / 1已认定 / 2不通过；已认定成果对负责人锁定，
#     需先撤销认定才能修改/删除；成果级别 1校级/2省级/3国家级（与项目级别不同）；
#   - 公告公示仅状态 6/7/8/9 的项目，审核中项目绝不公开。
#   - 附件实体文件存在 Docker 卷，数据库只存 sys_attachment.file_path 相对路径。
# ====================================================================
import io
from typing import Optional, List
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import PaginationParams, DataScope, OperationContext
from app.core.security import (
    RequireRole, RoleEnum, require_login, require_admin,
)
from app.core.response import ResponseModel, success, PageResult
from app.database.session import get_db
from app.models import SysUser
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectQueryParams, ProjectListItem,
    ProjectDetailResponse, ProjectSubmitResponse,
    AchievementCreate, AchievementUpdate, AchievementReviewRequest, AchievementResponse, ProjectStatisticsResponse,
    StatisticsTrendItem, CollegeStatisticsItem, FinalSubmitRequest,
)
from app.services.project_service import ProjectService, AchievementService
from app.services.archive_service import ArchiveService

router_project = APIRouter(prefix="/projects", tags=["项目申报"])
router_achievement = APIRouter(prefix="/achievements", tags=["项目成果"])
router_stats = APIRouter(prefix="/statistics", tags=["统计分析"])


# ====================================================================
# 项目申报接口
# ====================================================================

@router_project.get("", response_model=ResponseModel[PageResult[ProjectListItem]], summary="项目列表(分页)")
# --- 接口说明 ---
# URL: GET /api/projects
# 调用方: 已登录用户（学生/教师/专家/管理员）；实际可见范围由 DataScope 决定。
# 入参:
#   params(ProjectQueryParams): 关键词、比赛、学院、状态、年份等筛选条件；
#   pager(PaginationParams): page 页码、page_size 每页条数、排序字段。
# 返回: PageResult[ProjectListItem]（items + total + 页码 + 每页条数）。
# 权限: 超管全校；学院管理员本院；教师本院（含本人指导）；学生本人负责/参与；
#       专家仅被分配的项目。过滤在 Service 层按角色拼接，避免越权读取。
# 异常: 参数非法由 FastAPI/Pydantic 返回 422；无权限时 Service 抛 PermissionDeniedException。
# 副作用: 只读，不写库（分页查询不做惰性清扫，避免列表接口产生写事务）。
def api_project_list(
    params: ProjectQueryParams = Depends(),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    # 1. 按查询条件 + 角色数据范围查项目分页（软删数据自动排除）
    items, total = ProjectService.paginate(db, pager, params, data_scope)
    # 2. 统一包装成分页响应，前端表格/卡片直接消费
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


@router_project.get("/announcement/list", response_model=ResponseModel[PageResult[ProjectListItem]],
                    summary="立项结果公示列表(公开)")
# --- 接口说明 ---
# URL: GET /api/projects/announcement/list
# 调用方: 已登录用户（公示页对全校开放）。
# 入参: keyword 项目名/负责人关键词；college_id 学院过滤；start_year/end_year 立项年份区间；
#       pager 分页参数。均为可选，最大关键词长度 128。
# 返回: PageResult[ProjectListItem]。
# 权限: 不做行级数据权限过滤，全校可见；但仅返回公示态项目（6已立项/7中期/8待结题/9已结题），
#       审核中（1/3/5/12/13）与草稿/驳回/撤销的项目绝不公开。
# 异常: 年份等参数非法由框架返回 422。
# 副作用: 只读。
def api_announcement_list(
    keyword: Optional[str] = Query(default=None, max_length=128),
    college_id: Optional[int] = Query(default=None),
    start_year: Optional[int] = Query(default=None),
    end_year: Optional[int] = Query(default=None),
    pager: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    """立项结果公示：展示所有已立项及之后阶段的项目（不做数据权限过滤，全校可见）"""
    # 1. 把散装 Query 参数收敛为统一的 ProjectQueryParams，复用列表查询逻辑
    params = ProjectQueryParams(
        keyword=keyword,
        college_id=college_id,
        start_year=start_year,
        end_year=end_year,
    )
    # 2. 走公示专用查询：内部强制限定公示状态，避免复用普通列表而泄漏审核中项目
    items, total = ProjectService.paginate_announcement(db, pager, params)
    return success(data=PageResult.create(items, total, pager.page, pager.page_size))


@router_project.get("/{project_id}", response_model=ResponseModel[ProjectDetailResponse], summary="项目详情")
# --- 接口说明 ---
# URL: GET /api/projects/{project_id}
# 调用方: 已登录用户。
# 入参: project_id 项目主键（路径参数）。
# 返回: ProjectDetailResponse（项目信息、成员、预算、审核流、附件、变更等聚合）。
# 权限: 由 ProjectService.get_detail 校验：负责人/成员、指导教师、本院管理员、超管、
#       被分配专家可读，其余一律拒绝。
# 异常: 不存在或已软删 -> 404 ResourceNotFoundException；无权 -> 403 PermissionDeniedException。
# 副作用: 详情读取触发行级「惰性清扫」——顺带作废超期变更/中期/结题数据，
#         可能把项目自动置为已撤销(11)或释放卡住的状态，因此是“读接口但有写库可能”。
def api_project_detail(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 聚合并校验可见性；内部已包含超期数据清扫与状态修正
    return success(data=ProjectService.get_detail(db, project_id, current_user))


@router_project.get("/{project_id}/archive", summary="导出结项归档(ZIP)")
# --- 接口说明 ---
# URL: GET /api/projects/{project_id}/archive
# 调用方: 已登录用户（实际仅项目相关方与管理员可导出）。
# 入参: project_id 项目主键。
# 返回: ZIP 文件流（项目归档信息.xlsx + 附件目录），非 JSON 包装。
# 权限: 复用 ProjectService.get_detail 的可见性校验；且项目必须为已结题(9)，
#       未结题项目导出会被拒绝（归档材料需验收定稿）。
# 异常: 未结题/无权 -> 业务异常；文件不存在时打包阶段跳过或报错。
# 副作用: 只读；从 Docker 卷读取附件实体，数据库仅提供 file_path 相对路径。
def api_project_archive(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    """仅已结题项目可导出：项目归档信息.xlsx + 附件目录"""
    # 1. 服务层校验状态与权限，并在内存中组装 ZIP（返回文件名 + 字节内容）
    filename, data = ArchiveService.export_zip(db, project_id, current_user)
    # 2. 以流式响应下发；filename* 使用 UTF-8 编码，避免中文文件名乱码
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            # 浏览器跨域下载时需要暴露该响应头，前端才能读到真实文件名
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router_project.post("", response_model=ResponseModel[ProjectDetailResponse], summary="创建项目(草稿)")
# --- 接口说明 ---
# URL: POST /api/projects
# 调用方: 学生或管理员（RequireRole(STUDENT, ADMIN)）；教师/专家直接 403。
# 入参: req(ProjectCreate) 项目名称、比赛、类别、成员、指导教师、预算、附件等；as_draft=True。
# 返回: ProjectDetailResponse（新建草稿的完整详情）。
# 权限: 服务层再校验负责人必须为当前学生本人；管理员代建时按管理员权限处理。
# 异常: 名额已满/重复报名/比赛未开放/参数非法 -> 参数或冲突异常（4xx）。
# 副作用: 新增 proj_project（状态 0 草稿）与成员/预算等子表；记录操作日志。
def api_project_create(
    req: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文：统一记录模块、操作人、耗时与描述，异常也会被捕获记录
    with ctx:
        ctx.set_desc(f"创建项目草稿[{req.project_name}]")
        # 2. as_draft=True 表示只存草稿，不触发审核链；编号在首次提交时才分配
        data = ProjectService.create(db, req, current_user, as_draft=True)
    return success(data=data, message="草稿保存成功")


@router_project.post("/submit-draft", response_model=ResponseModel[ProjectDetailResponse],
                     summary="创建并直接提交审核")
# --- 接口说明 ---
# URL: POST /api/projects/submit-draft
# 调用方: 学生或管理员。
# 入参: req(ProjectCreate) 同创建接口；接口内部以 as_draft=False 直接提交。
# 返回: ProjectDetailResponse（已进入审核流程的项目详情）。
# 权限: 同创建；服务层校验负责人、比赛名额与报名窗口。
# 异常: 名额/时间窗口/必填材料缺失等 -> 4xx；数据库冲突 -> 409。
# 副作用: 一次性创建项目并提交——项目状态置 12(待指导教师确认)、重置审核链、
#         首次分配项目编号、生成教师确认占位记录、给指导教师发通知。
def api_project_create_and_submit(
    req: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文：记录“创建并提交”这一原子动作的描述
    with ctx:
        ctx.set_desc(f"创建并提交项目[{req.project_name}]")
        # 2. as_draft=False：保存后立即走提交流程，避免前端再调一次提交接口
        data = ProjectService.create(db, req, current_user, as_draft=False)
    return success(data=data, message="创建并提交成功")


@router_project.put("/{project_id}", response_model=ResponseModel[ProjectDetailResponse], summary="修改项目")
# --- 接口说明 ---
# URL: PUT /api/projects/{project_id}
# 调用方: 已登录用户；实际仅负责人（学生）或具备管理权限者可改。
# 入参: project_id 项目主键；req(ProjectUpdate) 需修改的字段（成员、预算、附件等）。
# 返回: ProjectDetailResponse（更新后的详情）。
# 权限: 服务层校验负责人归属与项目状态可编辑性（已进入审核后通常只允许草稿态修改）。
# 异常: 不存在 -> 404；无权 -> 403；状态不允许修改 -> 400/409。
# 副作用: 更新项目及成员/预算子表、重建附件绑定；记录操作日志。
def api_project_update(
    project_id: int,
    req: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录被修改的项目编号
    with ctx:
        ctx.set_desc(f"修改项目#{project_id}")
        # 2. 服务层负责权限/状态校验与子表全量覆盖，路由层不重复判断
        data = ProjectService.update(db, project_id, req, current_user)
    return success(data=data, message="更新成功")


@router_project.post("/{project_id}/submit", response_model=ResponseModel[ProjectSubmitResponse],
                     summary="提交审核(草稿->待初审)")
# --- 接口说明 ---
# URL: POST /api/projects/{project_id}/submit
# 调用方: 学生或管理员。
# 入参: project_id 项目主键（无请求体）。
# 返回: ProjectSubmitResponse（提交结果、当前状态等）。
# 权限: 服务层校验项目负责人必须为当前学生；管理员可代提交。
# 异常: 非草稿/材料不全/名额或窗口不满足 -> 4xx。
# 副作用: 状态 0 -> 12(待指导教师确认)；重置整条审核链（软删历史审核记录）、
#         重建教师确认占位记录、首次分配项目编号、通知指导教师。
def api_project_submit(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录提交动作
    with ctx:
        ctx.set_desc(f"提交项目#{project_id}进入审核流程")
        # 2. 服务层完成状态机校验与审核链重建，返回新的流程信息
        data = ProjectService.submit(db, project_id, current_user)
    return success(data=data, message="提交成功")


@router_project.post("/{project_id}/withdraw", response_model=ResponseModel, summary="撤回项目")
# --- 接口说明 ---
# URL: POST /api/projects/{project_id}/withdraw
# 调用方: 学生或管理员。
# 入参: project_id 项目主键。
# 返回: 通用成功包装（无业务数据）。
# 权限: 仅项目负责人本人；状态必须为 12(待指导教师确认)。
# 异常: 已进入学院初审及之后 -> 400（不可撤回）；无权 -> 403。
# 副作用: 状态 12 -> 0(草稿)；软删本轮审核记录，清理占位与待办；
#         已分配的项目编号保留，下次提交沿用。
# 注意: 学院初审之后不允许撤回，防止已审项目回滚造成审核记录与结论不一致。
def api_project_withdraw(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录撤回动作
    with ctx:
        ctx.set_desc(f"撤回项目#{project_id}")
        # 2. 服务层校验“仅状态12可撤回”，并软删审核记录、退回草稿
        ProjectService.withdraw(db, project_id, current_user)
    return success(message="撤回成功，项目已退回草稿状态")


@router_project.post("/{project_id}/submit-final", response_model=ResponseModel[ProjectSubmitResponse],
                     summary="提交结项验收报告")
# --- 接口说明 ---
# URL: POST /api/projects/{project_id}/submit-final
# 调用方: 学生或管理员。
# 入参: project_id 项目主键；data(FinalSubmitRequest) 含 final_report 结题报告正文、
#       attachment_ids 证明材料附件 id 列表（临时附件以 biz_id=0 绑定到项目）。
# 返回: ProjectSubmitResponse。
# 权限: 仅项目负责人；项目状态必须为 8(待结题)。
# 异常: 非负责人 -> 403；状态不符 -> 400；超过结题截止日 -> 400。
# 副作用: 生成/复用结题验收占位审核记录（review_result=99，供专家验收）；
#         绑定附件；通知相关审核人。项目状态保持 8，不会自动变 9。
# 特殊规则:
#   - 截止日按比赛 final_deadline 判定；但本轮曾被驳回（final_rejected_current_round）
#     的重提不受截止日限制，避免驳回后无法补救；
#   - 提交前校验三项结项条件（成果、经费、中期等），不满足直接拒绝。
def api_project_submit_final(
    project_id: int,
    data: FinalSubmitRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录结题报告提交
    with ctx:
        ctx.set_desc(f"提交项目#{project_id}结项验收报告")
        # 2. 服务层做截止日/驳回豁免判断、三条件校验、占位记录维护与附件绑定
        result = ProjectService.submit_final(db, project_id, data.final_report, data.attachment_ids, current_user)
    return success(data=result, message="结项验收报告已提交")


@router_project.post("/{project_id}/withdraw-final", response_model=ResponseModel[ProjectSubmitResponse],
                     summary="撤回结项验收报告提交")
# --- 接口说明 ---
# URL: POST /api/projects/{project_id}/withdraw-final
# 调用方: 学生或管理员。
# 入参: project_id 项目主键。
# 返回: ProjectSubmitResponse（当前状态与提示）。
# 权限: 仅项目负责人；项目需处于待结题(8)且报告已提交但尚未验收完成。
# 异常: 已过结题截止日 -> 400（提交锁定后不可撤回）；状态不符 -> 400；无权 -> 403。
# 副作用: 物理删除结题验收的占位审核记录，清空本轮报告提交标记，项目仍为 8，
#         负责人可修改报告后重新提交。
def api_project_withdraw_final(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = Depends(RequireRole(RoleEnum.STUDENT, RoleEnum.ADMIN)),
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录撤回结题报告
    with ctx:
        ctx.set_desc(f"撤回项目#{project_id}结项验收报告")
        # 2. 服务层校验截止日（过期即锁）并清理验收占位记录
        result = ProjectService.withdraw_final(db, project_id, current_user)
    return success(data=result, message="结项验收报告已撤回")


@router_project.delete("/{project_id}", response_model=ResponseModel, summary="删除项目(软删)")
# --- 接口说明 ---
# URL: DELETE /api/projects/{project_id}
# 调用方: 已登录用户；实际按分级权限判断（负责人本人 / 本院管理员 / 超管）。
# 入参: project_id 项目主键。
# 返回: 通用成功包装。
# 权限: 学生仅能删本人草稿类项目；学院管理员限本院；超管全校；教师/专家不可删。
# 异常: 不存在 -> 404；越权 -> 403；状态不允许删除 -> 400。
# 副作用: 软删项目（is_deleted=1）并级联软删成员、预算、审核、成果等子表，
#         数据保留在库中以便审计与统计口径一致。
def api_project_delete(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录删除动作
    with ctx:
        ctx.set_desc(f"删除项目#{project_id}")
        # 2. 服务层执行分级权限校验与级联软删
        ProjectService.delete(db, project_id, current_user)
    return success(message="删除成功")


# ====================================================================
# 项目成果接口
# ====================================================================

@router_achievement.get("/by-project/{project_id}", response_model=ResponseModel[list[AchievementResponse]],
                        summary="查询项目下成果列表")
# --- 接口说明 ---
# URL: GET /api/achievements/by-project/{project_id}
# 调用方: 已登录用户（项目相关方）。
# 入参: project_id 项目主键。
# 返回: list[AchievementResponse]，不分页（单项目成果数量有限）。
# 权限: 复用项目详情可见性（负责人/成员/指导教师/本院管理员/超管/被分配专家）。
# 异常: 项目不存在 -> 404；无权 -> 403。
# 副作用: 只读；仅返回未软删成果及其认定状态。
def api_achievement_list(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
):
    # 1. 服务层校验项目可见性后返回该项目下全部成果
    return success(data=AchievementService.list_by_project(db, project_id, current_user))


@router_achievement.post("", response_model=ResponseModel[AchievementResponse], summary="登记项目成果")
# --- 接口说明 ---
# URL: POST /api/achievements
# 调用方: 已登录用户；实际仅项目负责人/成员可登记。
# 入参: req(AchievementCreate) 含 project_id、标题、类型、级别（1校级/2省级/3国家级）、
#       获奖/发表信息、证明材料附件 id。
# 返回: AchievementResponse（新成果，初始认定状态 0待认定）。
# 权限: 服务层校验项目归属与项目阶段（通常需已立项后的项目可登记成果）。
# 异常: 项目不存在/无权 -> 4xx；重复成果/参数非法 -> 4xx。
# 副作用: 新增 proj_achievement、绑定附件（biz_type=achievement），记录操作日志；
#         不直接产生证书，证书由后续认定/比赛颁奖流程生成。
def api_achievement_create(
    req: AchievementCreate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录成果标题与所属项目
    with ctx:
        ctx.set_desc(f"登记项目#{req.project_id}成果[{req.title}]")
        # 2. 服务层校验项目权限/阶段并落库，初始为待认定
        data = AchievementService.create(db, req, current_user)
    return success(data=data, message="成果登记成功")


@router_achievement.put("/{pk}", response_model=ResponseModel[AchievementResponse], summary="编辑成果")
# --- 接口说明 ---
# URL: PUT /api/achievements/{pk}
# 调用方: 已登录用户；实际仅成果所属项目负责人/成员（管理员按权限放行）。
# 入参: pk 成果主键；req(AchievementUpdate) 可修改的字段。
# 返回: AchievementResponse。
# 权限: 服务层校验归属与认定状态。
# 异常: 成果不存在 -> 404；无权 -> 403；已认定(1)成果被锁定禁止修改 -> 400。
# 副作用: 更新成果字段并重建附件绑定，记录操作日志。
# 注意: 已认定成果必须先「撤销认定」才能编辑，保证认定结论与材料一致。
def api_achievement_update(
    pk: int,
    req: AchievementUpdate,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录成果主键
    with ctx:
        ctx.set_desc(f"编辑成果#{pk}")
        # 2. 服务层校验认定锁定与归属后更新
        data = AchievementService.update(db, pk, req, current_user)
    return success(data=data, message="成果修改成功")


@router_achievement.post("/{pk}/review", response_model=ResponseModel[AchievementResponse], summary="成果认定")
# --- 接口说明 ---
# URL: POST /api/achievements/{pk}/review
# 调用方: 已登录用户；实际仅管理员（超管/对应学院管理员）有认定权。
# 入参: pk 成果主键；req(AchievementReviewRequest) 含 review_status（1认定通过/2不通过）、
#       认定意见等。
# 返回: AchievementResponse（含最新认定状态）。
# 权限: 服务层校验管理员身份与学院范围；学生/教师不能自审。
# 异常: 成果不存在 -> 404；无权 -> 403；重复认定 -> 409。
# 副作用: 写 proj_achievement_review 认定记录并回写成果状态；通知项目负责人与指导教师。
def api_achievement_review(
    pk: int,
    req: AchievementReviewRequest,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录认定动作
    with ctx:
        ctx.set_desc(f"认定成果#{pk}")
        # 2. 服务层写认定记录并推送通知
        data = AchievementService.review(db, pk, req, current_user)
    return success(data=data, message="成果认定完成")


@router_achievement.post("/{pk}/revoke", response_model=ResponseModel[AchievementResponse], summary="撤销成果认定")
# --- 接口说明 ---
# URL: POST /api/achievements/{pk}/revoke
# 调用方: 已登录用户；实际仅管理员（与认定权限一致）。
# 入参: pk 成果主键。
# 返回: AchievementResponse（认定状态回退为 0待认定）。
# 权限: 管理员且在有权限的学院范围内。
# 异常: 成果不存在 -> 404；无权 -> 403；当前未认定 -> 400。
# 副作用: 撤销认定结论（保留历史记录，不物理删除），通知负责人；
#         撤销后成果恢复可编辑/可删除状态。
def api_achievement_revoke(
    pk: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录撤销动作
    with ctx:
        ctx.set_desc(f"撤销成果#{pk}认定")
        # 2. 服务层更新认定状态并通知相关人
        data = AchievementService.revoke_review(db, pk, current_user)
    return success(data=data, message="已撤销认定")


@router_achievement.delete("/{pk}", response_model=ResponseModel, summary="删除成果")
# --- 接口说明 ---
# URL: DELETE /api/achievements/{pk}
# 调用方: 已登录用户；实际仅成果所属项目负责人/成员或管理员。
# 入参: pk 成果主键。
# 返回: 通用成功包装。
# 权限: 服务层校验归属；管理员按学院范围放行。
# 异常: 成果不存在 -> 404；无权 -> 403；已认定(1)成果禁止删除 -> 400。
# 副作用: 软删成果（is_deleted=1）并解除附件绑定；认定记录保留用于审计。
def api_achievement_delete(
    pk: int,
    db: Session = Depends(get_db),
    current_user: SysUser = require_login,
    ctx: OperationContext = Depends(),
):
    # 1. 审计上下文记录删除动作
    with ctx:
        ctx.set_desc(f"删除成果#{pk}")
        # 2. 服务层校验认定锁定后软删
        AchievementService.delete(db, pk, current_user)
    return success(message="删除成功")


# ====================================================================
# 统计分析接口
# ====================================================================

@router_stats.get("/overview", response_model=ResponseModel[ProjectStatisticsResponse],
                  summary="项目总览统计(ECharts适配)")
# --- 接口说明 ---
# URL: GET /api/statistics/overview
# 调用方: 已登录用户；统计口径按 DataScope 收缩。
# 入参:
#   college_id: 学院过滤（学院管理员只能看本院，传其他学院由 Service 按范围收敛）；
#   project_type: 项目类别 1创新训练 / 2创业训练 / 3创业实践；
#   start_year/end_year: 立项年份区间。
# 返回: ProjectStatisticsResponse（总量、各状态数、类别分布、金额等，适配 ECharts）。
# 权限: 超管全校；学院管理员本院；教师本院；学生本人相关；专家被分配项目。
# 异常: 参数越界由 Query 校验返回 422。
# 副作用: 只读，不写库。
def api_stats_overview(
    college_id: Optional[int] = Query(default=None, description="学院过滤"),
    project_type: Optional[int] = Query(default=None, ge=1, le=3, description="项目类别过滤"),
    start_year: Optional[int] = Query(default=None, description="立项年份起过滤"),
    end_year: Optional[int] = Query(default=None, description="立项年份止过滤"),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    # 1. 把筛选条件交给服务层，与行级数据范围合并后做聚合统计
    return success(data=ProjectService.statistics_overview(
        db, data_scope,
        college_id=college_id, project_type=project_type,
        start_year=start_year, end_year=end_year,
    ))


@router_stats.get("/trend", response_model=ResponseModel[list[StatisticsTrendItem]],
                  summary="按月申报趋势统计")
# --- 接口说明 ---
# URL: GET /api/statistics/trend
# 调用方: 已登录用户；同样受 DataScope 限制。
# 入参: start_year 起始年份（默认 2020）、end_year 结束年份（默认 2030），均为查询参数。
# 返回: list[StatisticsTrendItem]，按月份给出申报/立项数量，供折线图使用。
# 权限: 学生/教师/专家只统计其可见项目，避免通过趋势反推全校数据。
# 异常: 年份非整数由框架返回 422。
# 副作用: 只读。
def api_stats_trend(
    start_year: int = 2020,
    end_year: int = 2030,
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    # 1. 按月聚合（内部用 extract(year/month) 分组），并叠加权限范围
    return success(data=ProjectService.trend_by_month(db, start_year, end_year, data_scope))


@router_stats.get("/college-breakdown", response_model=ResponseModel[list[CollegeStatisticsItem]],
                  summary="各学院统计数据（雷达图/热力图/学院立项率）")
# --- 接口说明 ---
# URL: GET /api/statistics/college-breakdown
# 调用方: 已登录用户；用于统计大屏的雷达图/热力图与学院立项率。
# 入参:
#   college_id: 学院过滤；project_type: 1创新训练/2创业训练/3创业实践；
#   start_year/end_year: 立项年份区间。
# 返回: list[CollegeStatisticsItem]，每学院申报数、立项数、立项率等。
# 权限: DataScope 收敛——学院管理员只看到本院一行，学生/教师仅本人相关。
# 异常: 参数越界 -> 422。
# 副作用: 只读。
def api_stats_college_breakdown(
    college_id: Optional[int] = Query(default=None, description="学院过滤"),
    project_type: Optional[int] = Query(default=None, ge=1, le=3, description="项目类别过滤"),
    start_year: Optional[int] = Query(default=None, description="立项年份起过滤"),
    end_year: Optional[int] = Query(default=None, description="立项年份止过滤"),
    db: Session = Depends(get_db),
    data_scope: DataScope = Depends(),
    current_user: SysUser = require_login,
):
    # 1. 按学院分组聚合，并合并筛选条件与数据权限
    return success(data=ProjectService.college_breakdown(
        db, data_scope,
        college_id=college_id, project_type=project_type,
        start_year=start_year, end_year=end_year,
    ))
