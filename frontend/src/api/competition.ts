/**
 * 创新创业大赛接口
 */
import { get, post, put, del, patch } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 比赛列表项 */
export interface CompetitionListItem {
  id: number
  title: string
  session: string | null
  competition_type: number
  competition_type_name: string
  level: number
  level_name: string
  organizer: string | null
  registration_start: string | null
  registration_end: string | null
  competition_start: string | null
  competition_end: string | null
  college_review_date: string | null
  university_review_date: string | null
  expert_review_date: string | null
  midterm_deadline: string | null
  final_deadline: string | null
  location: string | null
  cover_image: string | null
  status: number
  status_name: string
  view_count: number
  created_at: string
}

/** 比赛详情 */
export interface CompetitionDetail extends CompetitionListItem {
  co_organizer: string | null
  description: string | null
  requirements: string | null
  rewards: string | null
  contact: string | null
  official_url: string | null
  created_by: number | null
  creator_name: string | null
}

/** 比赛创建/更新参数 */
export interface CompetitionForm {
  title: string
  session?: string
  competition_type: number
  level: number
  organizer?: string
  co_organizer?: string
  description?: string
  requirements?: string
  rewards?: string
  registration_start?: string
  registration_end?: string
  competition_start?: string
  competition_end?: string
  college_review_date?: string
  university_review_date?: string
  expert_review_date?: string
  midterm_deadline?: string
  final_deadline?: string
  location?: string
  contact?: string
  cover_image?: string
  official_url?: string
  status: number
}

/** 比赛列表 */
export function getCompetitionList(params: {
  page: number
  page_size: number
  keyword?: string
  competition_type?: number
  level?: number
  status?: number
}) {
  return get<PageResult<CompetitionListItem>>('/api/competitions', params)
}

/** 比赛详情 */
export function getCompetitionDetail(id: number) {
  return get<CompetitionDetail>(`/api/competitions/${id}`)
}

/** 创建比赛 */
export function createCompetition(data: CompetitionForm) {
  return post<CompetitionDetail>('/api/competitions', data)
}

/** 更新比赛 */
export function updateCompetition(id: number, data: CompetitionForm) {
  return put<CompetitionDetail>(`/api/competitions/${id}`, data)
}

/** 删除比赛 */
export function deleteCompetition(id: number) {
  return del(`/api/competitions/${id}`)
}

/** 修改比赛状态（后端为 Query 参数） */
export function updateCompetitionStatus(id: number, status: number) {
  return patch<CompetitionDetail>(`/api/competitions/${id}/status`, undefined, { params: { status } })
}

/** 比赛显示名称：名称+届次，如「互联网+（2026届）」 */
export function competitionLabel(c: { title: string; session?: string | null }): string {
  return c.session ? `${c.title}（${c.session}）` : c.title
}

/** 是否可申报选择：以比赛状态为准（报名中/进行中），与后端提交校验保持一致 */
export function isCompetitionSelectable(c: { status: number }): boolean {
  return [1, 2].includes(c.status)
}

/** 获奖名单项 */
export interface AwardItem {
  project_id: number
  project_name: string
  average_score: number
  rank: number
  award_level: string
}

/** 获奖名单分组（按负责人学院） */
export interface AwardGroup {
  college_id: number
  college_name: string | null
  items: AwardItem[]
}

/** 获奖名单生成结果 */
export interface AwardGenerateResult {
  competition_id: number
  competition_title: string
  session: string | null
  total_awarded: number
  groups: AwardGroup[]
}

/** 生成获奖名单（仅校级比赛，管理员手动触发） */
export function generateCompetitionAwards(id: number) {
  return post<AwardGenerateResult>(`/api/competitions/${id}/generate-awards`)
}
