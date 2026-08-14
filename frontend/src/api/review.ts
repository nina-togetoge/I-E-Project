/**
 * 审核管理接口
 */
import { get, post, put } from '@/utils/request'
import type { PageResult } from '@/utils/request'

export interface ReviewRecord {
  id: number
  project_id: number
  project_title: string
  project_code: string
  stage: number          // 1-学院初审 2-校级复审 3-专家评审
  stage_name: string
  reviewer_id: number | null
  reviewer_name: string | null
  review_type: string    // pass / reject
  score: number | null
  opinion: string | null
  status: number        // 0-待审核 1-通过 2-驳回
  created_at: string
  reviewed_at: string | null
}

/** 待审核列表 */
export function getReviewList(params: {
  page: number
  page_size: number
  stage?: number
  status?: number
  keyword?: string
}) {
  return get<PageResult<ReviewRecord>>('/api/reviews', params)
}

/** 提交审核 */
export function submitReview(data: {
  project_id: number
  review_type: 'pass' | 'reject'
  opinion: string
}) {
  return post('/api/reviews', data)
}

/** 专家评审 */
export function submitExpertReview(data: {
  project_id: number
  score: number
  innovation_score: number
  feasibility_score: number
  practical_score: number
  opinion: string
}) {
  return post('/api/reviews/expert', data)
}

/** 分配专家 */
export function assignExperts(data: {
  project_id: number
  expert_ids: number[]
}) {
  return post('/api/reviews/assign-experts', data)
}

/** 获取审核记录 */
export function getReviewHistory(projectId: number) {
  return get<ReviewRecord[]>(`/api/reviews/project/${projectId}`)
}
