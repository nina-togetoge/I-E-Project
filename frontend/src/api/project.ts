/**
 * 项目管理接口
 *
 * 覆盖项目申报、审核流转、立项公示、中期/结项、项目成果与归档导出。
 * 主要调用方：
 *   - views/project/MyProjects.vue：我的项目列表、提交/撤回/删除；
 *   - views/project/ProjectCreate.vue：新建、保存草稿、编辑后提交；
 *   - views/project/ProjectDetail.vue：详情、审核流程、变更申请；
 *   - views/project/MidtermCheck.vue、FinalCheck.vue：中期与结题阶段；
 *   - views/project/ProjectAchievements.vue、components/AchievementPanel.vue：成果登记与认定；
 *   - views/admin/AdminProjects.vue、admin/Statistics.vue、dashboard/index.vue：管理与统计；
 *   - views/announcement/ApprovalList.vue：立项结果公示。
 * 统一约定：
 *   - 列表接口返回 PageResult<T>（items/total/page/page_size），page 从 1 开始；
 *   - 响应由 utils/request 拦截器解包为 { code, message, data }，业务错误已统一提示；
 *   - Token 由请求拦截器自动携带，本层不处理鉴权与 loading。
 */
import { get, post, put, del, download } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/**
 * 项目列表项：列表/归档/公示页共用的精简视图
 * 由后端 ProjectListItem Schema 返回，已冗余学院、负责人、教师与比赛名称，
 * 前端无需再逐条查询关联表。
 */
export interface ProjectListItem {
  /** 项目主键 */
  id: number
  /** 业务编号（如 S2026-001），草稿阶段可能为空 */
  project_no: string | null
  /** 项目名称 */
  project_name: string
  /** 项目类型：1 创新训练 / 2 创业训练 / 3 创业实践（注意与比赛类型取值不同） */
  project_type: number
  /** 项目类型文案，后端回填 */
  project_type_name: string
  /** 项目级别：1 院级 / 2 校级 / 3 省级 / 4 国家级（与成果 level 含义不同） */
  project_level: number
  /** 项目级别文案 */
  project_level_name: string
  /** 申报学院 ID，学院管理员的数据范围依据 */
  college_id: number
  /** 申报学院名称 */
  college_name: string
  /** 负责人（学生）用户 ID */
  leader_id: number
  /** 负责人姓名 */
  leader_name: string
  /** 指导教师用户 ID，未选导师时为空 */
  teacher_id: number | null
  /** 指导教师姓名 */
  teacher_name: string | null
  /** 关联比赛 ID，非比赛类项目为空 */
  competition_id: number | null
  /** 关联比赛名称 */
  competition_name: string | null
  /** 比赛届次，用于「名称（届次）」展示 */
  competition_session: string | null
  /** 立项开始日期 */
  start_date: string | null
  /** 计划结束日期，延期申请通过后由后端调整 */
  end_date: string | null
  /** 预算总额（预算明细汇总） */
  budget_amount: number
  /** 已使用金额，按报销流水累计 */
  used_amount: number
  /** 流程状态：0草稿/1待学院/3待校级/5待专家/6已立项/7中期/8待结题/9已结题/10驳回/11撤销/12待教师/13待分配专家 */
  status: number
  /** 状态中文文案，后端回填，前端展示优先使用 */
  status_name: string
  /** 竞赛获奖成果数量 */
  award_count?: number
  /** 是否可修改后重新提交（仅「指导教师驳回」为 true；学院/校级/专家驳回即落选） */
  resubmittable?: boolean
  submit_time: string | null
  created_at: string
}

/**
 * 项目详情：在列表项基础上补充正文、驳回原因、结题验收状态与关联明细。
 * 详情页、中期/结题页均复用此结构。
 */
export interface ProjectDetail extends ProjectListItem {
  /** 项目简介 */
  project_summary: string | null
  /** 创新点说明 */
  innovation_points: string | null
  /** 预期成果 */
  expected_results: string | null
  /** 最近一次驳回原因，仅在状态 10 时有值 */
  reject_reason: string | null
  /** 是否已提交结项报告（true 时前端隐藏提交入口，改为展示验收进度） */
  final_report_submitted?: boolean
  /** 结项验收报告正文 */
  final_report?: string | null
  /** 结项报告状态：0未提交 1待验收 2已通过 3已驳回 */
  final_report_status?: number
  /** 最近一次结题验收驳回意见 */
  final_reject_reason?: string | null
  /** 参与结题验收的专家数 */
  final_review_total?: number
  /** 本轮已提交结题验收意见的专家数 */
  final_review_done?: number
  /** 当前用户是否可进行结题验收 */
  final_can_accept?: boolean
  /** 当前用户本轮是否已提交结题验收意见 */
  final_reviewed_by_me?: boolean
  /** 结项条件检查清单 */
  final_checklist?: { key: string; label: string; passed: boolean; detail: string }[]
  /** 变更申请截止时间，过期后后端拒绝新申请 */
  change_deadline?: string | null
  /** 是否锁定变更申请（如已有待审批申请或次数用尽） */
  change_locked?: boolean
  /** 中期检查截止时间 */
  midterm_deadline?: string | null
  /** 结题验收截止时间 */
  final_deadline?: string | null
  /** 团队成员列表（姓名、学号、角色等由后端回填） */
  team_members?: any[]
  /** 预算科目明细，用于经费页与结题检查 */
  budgets?: any[]
  /** 项目附件列表，含证明材料与结项报告附件 */
  attachments?: any[]
}

/**
 * 统计概览：首页数据卡片与数据看板共用
 * 后端按当前登录人的数据范围聚合（学院管理员仅本院）。
 */
export interface StatisticsData {
  /** 项目总数（含各状态） */
  total_projects: number
  /** 待审核项目数 */
  pending_review: number
  /** 已立项项目数 */
  approved_projects: number
  /** 已结题项目数 */
  finished_projects: number
  /** 预算总额 */
  total_budget: number
  /** 已使用金额 */
  total_used: number
  /** 立项率（百分比数值，前端直接展示） */
  approval_rate: number
  /** 项目类型分布，用于饼图 */
  category_dist?: { name: string; value: number }[]
  /** 状态分布，status 字段便于前端按状态着色 */
  status_dist?: { name: string; value: number; status: number }[]
  /** 各类型预算金额，用于柱状图 */
  budget_by_category?: { name: string; amount: number }[]
}

/**
 * 分页查询项目列表 GET /api/projects
 * 后端按当前登录人角色注入数据范围：学生仅本人、教师看指导项目、
 * 学院管理员限本院、超管全校，因此前端无需额外传 leader_id 做隔离。
 * @param params 分页 + 关键字 + 状态/类型/级别/学院/负责人/教师筛选
 * @returns PageResult<ProjectListItem>，含状态文案与获奖数量
 * 调用方：MyProjects、AdminProjects、ArchiveList、MyExpenses（项目下拉）。
 */
export function getProjectList(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 项目名称/编号模糊搜索 */
  keyword?: string
  /** 项目状态筛选，取值见 PROJECT_STATUS */
  status?: number
  /** 项目类型：1 创新训练 / 2 创业训练 / 3 创业实践 */
  project_type?: number
  /** 项目级别：1 院级 / 2 校级 / 3 省级 / 4 国家级 */
  project_level?: number
  /** 申报学院 ID，仅管理员侧使用 */
  college_id?: number
  /** 负责人用户 ID，用于筛选某学生的项目 */
  leader_id?: number
  /** 指导教师用户 ID，用于教师端只看自己指导的项目 */
  teacher_id?: number
}) {
  return get<PageResult<ProjectListItem>>('/api/projects', params)
}

/**
 * 立项结果公示列表（公开只读）GET /api/projects/announcement/list
 * 返回已立项/已结题项目，供全校师生按学院与年份浏览。
 * 调用方：views/announcement/ApprovalList.vue，无写操作。
 */
export function getAnnouncementList(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 项目名称/编号/负责人模糊搜索 */
  keyword?: string
  /** 按申报学院筛选 */
  college_id?: number
  /** 起始立项年份（含） */
  start_year?: number
  /** 结束立项年份（含） */
  end_year?: number
}) {
  return get<PageResult<ProjectListItem>>('/api/projects/announcement/list', params)
}

/**
 * 查询项目详情 GET /api/projects/{id}
 * 返回立项信息、结题验收进度、变更/中期截止时间及团队成员、预算、附件。
 * 调用方：ProjectDetail、ProjectCreate（编辑回填）、MidtermCheck、FinalCheck、
 *         ProjectAchievements；权限由后端校验。
 */
export function getProjectDetail(id: number) {
  return get<ProjectDetail>(`/api/projects/${id}`)
}

/**
 * 新建项目并保存为草稿 POST /api/projects
 * @param data 申报表单主体：基本信息、团队、预算、附件 ID 等
 * 调用方：ProjectCreate 的「保存草稿」；状态为 0，不进入审核流程。
 */
export function createProject(data: any) {
  return post('/api/projects', data)
}

/**
 * 新建并直接提交审核 POST /api/projects/submit-draft
 * 一步完成创建与提交，成功后状态进入 12 待指导教师确认。
 * 调用方：ProjectCreate 的「提交申报」；编辑后再提交走 updateProject + submitProject。
 */
export function createAndSubmitProject(data: any) {
  return post('/api/projects/submit-draft', data)
}

/**
 * 修改项目 PUT /api/projects/{id}
 * 仅草稿、指导教师驳回（resubmittable=true）等允许编辑的状态可调用，
 * 其他状态由后端返回业务错误并统一提示。
 * 调用方：ProjectCreate 编辑模式、MyProjects 快速编辑。
 */
export function updateProject(id: number, data: any) {
  return put(`/api/projects/${id}`, data)
}

/**
 * 提交项目进入审核 POST /api/projects/{id}/submit
 * 状态由 0/12 推进到 1 待学院初审；成功后调用方需刷新列表或详情。
 * 调用方：MyProjects 提交按钮、ProjectCreate 编辑后提交。
 */
export function submitProject(id: number) {
  return post(`/api/projects/${id}/submit`)
}

/**
 * 撤回已提交项目 POST /api/projects/{id}/withdraw
 * 状态变为 11 已撤销；仅尚未被审核处理时允许，后端校验。
 * 调用方：MyProjects 撤回操作。
 */
export function withdrawProject(id: number) {
  return post(`/api/projects/${id}/withdraw`)
}

/**
 * 提交结项验收报告 POST /api/projects/{id}/submit-final
 * @param data final_report 报告正文；attachment_ids 已上传附件的主键列表
 * 提交后项目停留在 8 待结题，等待专家/管理员验收。
 * 调用方：FinalCheck 提交按钮。
 */
export function submitFinal(id: number, data: { final_report: string; attachment_ids: number[] }) {
  return post(`/api/projects/${id}/submit-final`, data)
}

/**
 * 撤回结项验收报告 POST /api/projects/{id}/withdraw-final
 * 专家尚未验收时，可撤回修改后重新提交；项目仍停留在待结题。
 * 调用方：FinalCheck、ProjectDetail。
 */
export function withdrawFinal(id: number) {
  return post(`/api/projects/${id}/withdraw-final`)
}

/**
 * 删除项目 DELETE /api/projects/{id}
 * 后端软删除，仅草稿/已撤销等允许删除的状态可调用。
 * 调用方：MyProjects；页面负责二次确认，本层不再弹窗。
 */
export function deleteProject(id: number) {
  return del(`/api/projects/${id}`)
}

/**
 * 统计概览 GET /api/statistics/overview
 * @param params 年份区间、学院、项目类型筛选；不传表示全校全量
 * @returns 项目总量、待审数、立项/结题数、预算与使用额、立项率及分布
 * 调用方：dashboard/index.vue、admin/Statistics.vue。
 */
export function getStatistics(params?: {
  /** 起始年份（含） */
  start_year?: number
  /** 结束年份（含） */
  end_year?: number
  /** 学院 ID，学院管理员默认只看本院 */
  college_id?: number
  /** 项目类型筛选 */
  project_type?: number
}) {
  return get<StatisticsData>('/api/statistics/overview', params)
}

/**
 * 申报趋势统计 GET /api/statistics/trend
 * 参数为年份整数（start_year/end_year），返回按月/按年的申报量序列。
 * 调用方：dashboard 折线图、admin/Statistics.vue 趋势图。
 */
export function getTrend(params: {
  /** 起始年份（含），不传由后端取默认区间 */
  start_year?: number
  /** 结束年份（含） */
  end_year?: number
} = {}) {
  return get('/api/statistics/trend', params)
}

/**
 * 各学院维度统计 GET /api/statistics/college-breakdown
 * 用于雷达图、热力图与学院立项率对比；学院管理员只会拿到本院数据。
 * 调用方：admin/Statistics.vue。
 */
export function getCollegeBreakdown(params?: {
  /** 起始年份（含） */
  start_year?: number
  /** 结束年份（含） */
  end_year?: number
  /** 指定学院 ID，不传则返回权限范围内的全部学院 */
  college_id?: number
  /** 项目类型筛选 */
  project_type?: number
}) {
  return get('/api/statistics/college-breakdown', params)
}

// ========== 项目成果 ==========
/**
 * 成果证明材料附件：由公共附件表返回，展示在成果卡片的附件区。
 */
export interface AchievementAttachment {
  /** 附件主键，下载/预览/删除均使用它 */
  id: number
  /** 原始文件名 */
  file_name: string
  /** 文件大小（字节），前端格式化后展示 */
  file_size: number
  /** MIME 类型，用于判断是否可直接预览 */
  file_type?: string
  /** 上传者姓名 */
  uploader_name?: string
  /** 后端直链，若为空则用公共下载接口拼接 */
  download_url?: string
  /** 在线预览地址，图片/PDF 可用 */
  preview_url?: string
}

/**
 * 项目成果：论文、专利、软著、竞赛获奖等
 * 认定状态决定是否可编辑/删除，竞赛获奖还用于生成证书与获奖名单。
 */
export interface Achievement {
  /** 成果主键 */
  id: number
  /** 所属项目 ID */
  project_id: number
  /** 成果类型：由后端字典定义（论文/专利/竞赛获奖等） */
  achievement_type: number
  /** 成果标题 */
  title: string
  /** 作者/完成人 */
  author?: string
  /** 发表日期或获奖日期 */
  publish_date?: string
  /** 发表期刊、授权机构或颁奖单位 */
  publisher?: string
  /** 成果编号（论文 DOI、专利号、证书编号等） */
  achievement_no?: string
  /** 成果级别：1 校级 / 2 省级 / 3 国家级 */
  level?: number
  /** 获奖等级文案（一等奖/二等奖等），仅竞赛类有值 */
  award_level?: string
  /** 成果摘要 */
  summary?: string
  /** 登记时间 */
  created_at: string
  /** 证明材料附件列表 */
  attachments?: AchievementAttachment[]
  /** 认定状态：0待认定 1已认定 2不通过 */
  review_status?: number
  /** 认定状态文案，后端回填 */
  review_status_name?: string
  /** 认定意见，不通过时说明原因 */
  review_comment?: string | null
  /** 认定人姓名 */
  reviewer_name?: string | null
  /** 认定时间 */
  review_time?: string | null
}

/**
 * 成果登记/编辑提交数据
 * 附件先通过 api/common.uploadFiles 上传拿到 ID，再随表单提交 attachment_ids。
 */
export interface AchievementPayload {
  /** 成果类型 */
  achievement_type: number
  /** 成果标题（必填） */
  title: string
  /** 作者/完成人 */
  author?: string
  /** 发表日期或获奖日期，格式 YYYY-MM-DD */
  publish_date?: string
  /** 发表/颁奖单位 */
  publisher?: string
  /** 成果编号 */
  achievement_no?: string
  /** 成果级别：1校级 2省级 3国家级 */
  level?: number
  /** 获奖等级文案 */
  award_level?: string
  /** 成果摘要 */
  summary?: string
  /** 已上传证明材料的附件 ID 列表 */
  attachment_ids?: number[]
}

/**
 * 查询项目下的成果列表 GET /api/achievements/by-project/{projectId}
 * 返回成果及认定状态、证明材料附件。
 * 调用方：AchievementPanel、ProjectDetail（与详情并行加载，失败时降级为空数组）。
 */
export function listAchievements(projectId: number) {
  return get<Achievement[]>(`/api/achievements/by-project/${projectId}`)
}

/**
 * 登记项目成果 POST /api/achievements
 * @param data 成果字段 + project_id + attachment_ids
 * 新成果默认 review_status=0 待认定；调用方：AchievementPanel 登记弹窗。
 */
export function createAchievement(data: AchievementPayload & { project_id: number }) {
  return post('/api/achievements', data)
}

/**
 * 编辑项目成果 PUT /api/achievements/{id}
 * 仅成果负责人可改，已认定成果可能被后端拒绝（需先撤销认定）。
 * 调用方：AchievementPanel 编辑弹窗。
 */
export function updateAchievement(id: number, data: AchievementPayload) {
  return put(`/api/achievements/${id}`, data)
}

/**
 * 删除项目成果 DELETE /api/achievements/{pk}
 * @param pk 成果主键（与其他函数命名不同，注意别传成项目 ID）
 * 后端软删除；调用方：AchievementPanel 删除操作。
 */
export function deleteAchievement(pk: number) {
  return del(`/api/achievements/${pk}`)
}

/**
 * 成果认定 POST /api/achievements/{pk}/review
 * @param data result 1 通过 / 2 不通过；comment 不通过时需说明理由
 * 仅教师/管理员可用；调用方：AchievementPanel 认定面板。
 */
export function reviewAchievement(pk: number, data: { result: number; comment?: string }) {
  return post<Achievement>(`/api/achievements/${pk}/review`, data)
}

/**
 * 撤销成果认定 POST /api/achievements/{pk}/revoke
 * 回到 0 待认定，允许负责人修改后重新提交认定。
 * 调用方：AchievementPanel 撤销按钮。
 */
export function revokeAchievement(pk: number) {
  return post<Achievement>(`/api/achievements/${pk}/revoke`)
}

/**
 * 导出结项归档 ZIP GET /api/projects/{projectId}/archive
 * 直接触发浏览器下载（responseType=blob），不经过统一 JSON 解包。
 * @param filename 缺省为「项目归档_{id}.zip」
 * 调用方：FinalCheck 导出按钮。
 */
export function downloadProjectArchive(projectId: number, filename?: string) {
  return download(
    `/api/projects/${projectId}/archive`,
    undefined,
    filename || `项目归档_${projectId}.zip`,
  )
}
