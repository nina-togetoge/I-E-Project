/**
 * 创新创业大赛接口
 */
import { get, post, put, del, patch } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 比赛列表项 */
export interface CompetitionListItem {
  id: number
  title: string
  competition_type: number
  competition_type_name: string
  level: number
  level_name: string
  organizer: string | null
  registration_start: string | null
  registration_end: string | null
  competition_start: string | null
  competition_end: string | null
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

/** 修改比赛状态 */
export function updateCompetitionStatus(id: number, status: number) {
  return patch<CompetitionDetail>(`/api/competitions/${id}/status`, { status })
}
