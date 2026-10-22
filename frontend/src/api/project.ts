/**
 * 项目管理接口
 */
import { get, post, put, del, download } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 项目列表项 */
export interface ProjectListItem {
  id: number
  project_no: string | null
  project_name: string
  project_type: number
  project_type_name: string
  project_level: number
  project_level_name: string
  college_id: number
  college_name: string
  leader_id: number
  leader_name: string
  teacher_id: number | null
  teacher_name: string | null
  competition_id: number | null
  competition_name: string | null
  competition_session: string | null
  start_date: string | null
  end_date: string | null
  budget_amount: number
  used_amount: number
  status: number
  status_name: string
  /** 竞赛获奖成果数量 */
  award_count?: number
  /** 是否可修改后重新提交（仅「指导教师驳回」为 true；学院/校级/专家驳回即落选） */
  resubmittable?: boolean
  submit_time: string | null
  created_at: string
}

/** 项目详情 */
export interface ProjectDetail extends ProjectListItem {
  project_summary: string | null
  innovation_points: string | null
  expected_results: string | null
  reject_reason: string | null
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
  change_deadline?: string | null
  change_locked?: boolean
  midterm_deadline?: string | null
  final_deadline?: string | null
  team_members?: any[]
  budgets?: any[]
  attachments?: any[]
}

/** 项目统计 */
export interface StatisticsData {
  total_projects: number
  pending_review: number
  approved_projects: number
  finished_projects: number
  total_budget: number
  total_used: number
  approval_rate: number
  category_dist?: { name: string; value: number }[]
  status_dist?: { name: string; value: number; status: number }[]
  budget_by_category?: { name: string; amount: number }[]
}

/** 项目列表 */
export function getProjectList(params: {
  page: number
  page_size: number
  keyword?: string
  status?: number
  project_type?: number
  project_level?: number
  college_id?: number
  leader_id?: number
  teacher_id?: number
}) {
  return get<PageResult<ProjectListItem>>('/api/projects', params)
}

/** 立项结果公示列表（公开，全校可见） */
export function getAnnouncementList(params: {
  page: number
  page_size: number
  keyword?: string
  college_id?: number
  start_year?: number
  end_year?: number
}) {
  return get<PageResult<ProjectListItem>>('/api/projects/announcement/list', params)
}

/** 项目详情 */
export function getProjectDetail(id: number) {
  return get<ProjectDetail>(`/api/projects/${id}`)
}

/** 创建项目（保存草稿） */
export function createProject(data: any) {
  return post('/api/projects', data)
}

/** 创建并直接提交审核（非草稿） */
export function createAndSubmitProject(data: any) {
  return post('/api/projects/submit-draft', data)
}

/** 修改项目 */
export function updateProject(id: number, data: any) {
  return put(`/api/projects/${id}`, data)
}

/** 提交项目 */
export function submitProject(id: number) {
  return post(`/api/projects/${id}/submit`)
}

/** 撤回项目 */
export function withdrawProject(id: number) {
  return post(`/api/projects/${id}/withdraw`)
}

/** 提交结项验收报告 */
export function submitFinal(id: number, data: { final_report: string; attachment_ids: number[] }) {
  return post(`/api/projects/${id}/submit-final`, data)
}

/** 撤回结项验收报告提交（项目仍停留待结题，可修改后重新提交） */
export function withdrawFinal(id: number) {
  return post(`/api/projects/${id}/withdraw-final`)
}

/** 删除项目 */
export function deleteProject(id: number) {
  return del(`/api/projects/${id}`)
}

/** 项目统计 */
export function getStatistics(params?: {
  start_year?: number
  end_year?: number
  college_id?: number
  project_type?: number
}) {
  return get<StatisticsData>('/api/statistics/overview', params)
}

/** 趋势统计（与后端对齐：start_year/end_year 为年份整数） */
export function getTrend(params: {
  start_year?: number
  end_year?: number
} = {}) {
  return get('/api/statistics/trend', params)
}

/** 各学院统计数据（雷达图/热力图/学院立项率） */
export function getCollegeBreakdown() {
  return get('/api/statistics/college-breakdown')
}

// ========== 项目成果 ==========
/** 成果附件（证明材料） */
export interface AchievementAttachment {
  id: number
  file_name: string
  file_size: number
  file_type?: string
  uploader_name?: string
  download_url?: string
  preview_url?: string
}

/** 项目成果 */
export interface Achievement {
  id: number
  project_id: number
  achievement_type: number
  title: string
  author?: string
  publish_date?: string
  publisher?: string
  achievement_no?: string
  level?: number
  award_level?: string
  summary?: string
  created_at: string
  attachments?: AchievementAttachment[]
  /** 认定状态：0待认定 1已认定 2不通过 */
  review_status?: number
  review_status_name?: string
  review_comment?: string | null
  reviewer_name?: string | null
  review_time?: string | null
}

/** 成果登记/编辑提交数据 */
export interface AchievementPayload {
  achievement_type: number
  title: string
  author?: string
  publish_date?: string
  publisher?: string
  achievement_no?: string
  level?: number
  award_level?: string
  summary?: string
  attachment_ids?: number[]
}

/** 查询项目下的成果列表 */
export function listAchievements(projectId: number) {
  return get<Achievement[]>(`/api/achievements/by-project/${projectId}`)
}

/** 登记项目成果 */
export function createAchievement(data: AchievementPayload & { project_id: number }) {
  return post('/api/achievements', data)
}

/** 编辑项目成果 */
export function updateAchievement(id: number, data: AchievementPayload) {
  return put(`/api/achievements/${id}`, data)
}

/** 删除项目成果 */
export function deleteAchievement(pk: number) {
  return del(`/api/achievements/${pk}`)
}

/** 成果认定（1通过 / 2不通过） */
export function reviewAchievement(pk: number, data: { result: number; comment?: string }) {
  return post<Achievement>(`/api/achievements/${pk}/review`, data)
}

/** 导出结项归档（ZIP） */
export function downloadProjectArchive(projectId: number, filename?: string) {
  return download(
    `/api/projects/${projectId}/archive`,
    undefined,
    filename || `项目归档_${projectId}.zip`,
  )
}
