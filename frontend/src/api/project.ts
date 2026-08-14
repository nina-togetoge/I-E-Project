/**
 * 项目管理接口
 */
import { get, post, put, del } from '@/utils/request'
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
  start_date: string | null
  end_date: string | null
  budget_amount: number
  used_amount: number
  status: number
  status_name: string
  submit_time: string | null
  created_at: string
}

/** 项目详情 */
export interface ProjectDetail extends ProjectListItem {
  project_summary: string | null
  innovation_points: string | null
  expected_results: string | null
  reject_reason: string | null
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

/** 导出项目列表 */
export function exportProjects(params: {
  keyword?: string
  status?: number
  project_type?: number
  project_level?: number
  college_id?: number
}) {
  return get('/api/excel/export/projects', params, { responseType: 'blob' })
}

// ========== 项目成果 ==========
/** 查询项目下的成果列表 */
export function listAchievements(projectId: number) {
  return get<Array<{
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
  }>>(`/api/achievements/by-project/${projectId}`)
}

/** 登记项目成果 */
export function createAchievement(data: {
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
}) {
  return post('/api/achievements', data)
}

/** 删除项目成果 */
export function deleteAchievement(pk: number) {
  return del(`/api/achievements/${pk}`)
}
