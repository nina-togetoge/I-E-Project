/**
 * 项目管理接口
 */
import { get, post, put, del } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 项目列表项 */
export interface ProjectListItem {
  id: number
  project_code: string
  title: string
  category: number
  category_name: string
  status: number
  leader_name: string
  teacher_name: string
  college_name: string
  created_at: string
  submitted_at: string | null
  approved_at: string | null
  total_budget: number
}

/** 项目详情 */
export interface ProjectDetail {
  id: number
  project_code: string
  title: string
  category: number
  category_name: string
  status: number
  leader_id: number
  leader_name: string
  teacher_id: number | null
  teacher_name: string | null
  college_id: number
  college_name: string
  abstract: string
  keywords: string
  background: string
  objectives: string
  methodology: string
  expected_outcomes: string
  total_budget: number
  start_date: string | null
  end_date: string | null
  created_at: string
  submitted_at: string | null
  approved_at: string | null
  team_members: TeamMember[]
  budgets: BudgetItem[]
  achievements: Achievement[]
}

export interface TeamMember {
  id: number
  student_id: string
  student_name: string
  role: string
  contribution: string
}

export interface BudgetItem {
  id: number
  subject: string
  amount: number
  remark: string
}

export interface Achievement {
  id: number
  type: number
  title: string
  description: string
  authors: string
  publish_date: string | null
}

/** 项目统计 */
export interface StatisticsData {
  total_projects: number
  approved_projects: number
  archived_projects: number
  total_budget: number
  approval_rate: number
  by_category: { name: string; value: number }[]
  by_college: { name: string; value: number }[]
  by_status: { name: string; value: number }[]
  trend_by_month: { month: string; count: number }[]
}

/** 项目列表 */
export function getProjectList(params: {
  page: number
  page_size: number
  keyword?: string
  status?: number
  category?: number
  college_id?: number
}) {
  return get<PageResult<ProjectListItem>>('/api/projects', params)
}

/** 项目详情 */
export function getProjectDetail(id: number) {
  return get<ProjectDetail>(`/api/projects/${id}`)
}

/** 创建项目 */
export function createProject(data: any) {
  return post('/api/projects', data)
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
  start_date?: string
  end_date?: string
  college_id?: number
  category?: number
}) {
  return get<StatisticsData>('/api/statistics/overview', params)
}

/** 趋势统计 */
export function getTrend(params: {
  start_date?: string
  end_date?: string
  group_by?: string
}) {
  return get('/api/statistics/trend', params)
}

/** 导出项目列表 */
export function exportProjects(params: {
  keyword?: string
  status?: number
  category?: number
  college_id?: number
}) {
  return get('/api/projects/export', params, { responseType: 'blob' })
}
