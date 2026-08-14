/**
 * 审核管理接口
 */
import service, { get, post } from '@/utils/request'
import type { PageResult } from '@/utils/request'

export interface ReviewRecord {
  id: number
  project_id: number
  review_stage: number
  review_stage_name: string
  reviewer_id: number
  reviewer_name: string
  review_result: number
  review_result_name: string
  score: number | null
  review_comment: string | null
  review_time: string
  created_at: string
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

/** 提交审核(学院/校级) */
export function submitReview(data: {
  project_id: number
  review_stage: number
  review_result: number
  review_comment?: string
}) {
  return post('/api/reviews', data)
}

/** 专家评审 */
export function submitExpertReview(data: {
  project_id: number
  score: number
  review_result: number
  review_comment?: string
}) {
  return post('/api/reviews/expert', data)
}

/** 分配专家 */
export function assignExperts(data: {
  project_id: number
  expert_ids: number[]
  review_stage?: number
}) {
  return post('/api/reviews/assign-experts', data)
}

/** 专家待评审任务 */
export function getExpertTasks(params: {
  page: number
  page_size: number
  keyword?: string
}) {
  return get<PageResult<{
    project_id: number
    project_no: string | null
    project_name: string
    college_name: string
    leader_name: string
    project_type_name: string
    project_level_name: string
    submit_time: string | null
    status: number
    my_score: number | null
    my_review_result: number | null
  }>>('/api/reviews/expert-tasks', params)
}

/** 获取审核流程记录 */
export function getReviewHistory(projectId: number) {
  return get(`/api/reviews/flow/${projectId}`)
}

// ========== 中期检查接口 ==========
/** 查询项目中期检查结果 */
export function getMidtermCheck(projectId: number) {
  return get<{
    id: number
    project_id: number
    progress_desc?: string
    completed_tasks?: string
    remaining_tasks?: string
    problems?: string
    next_plan?: string
    budget_usage?: number
    status: number
    status_name: string
    reviewer_id?: number
    review_comment?: string
    review_time?: string
    submit_time?: string
  }>(`/api/midterm/by-project/${projectId}`)
}

/** 保存中期检查草稿 */
export function saveMidtermDraft(data: {
  project_id: number
  progress_desc?: string
  completed_tasks?: string
  remaining_tasks?: string
  problems?: string
  next_plan?: string
  budget_usage?: number
}) {
  return post('/api/midterm/draft', data)
}

/** 提交中期检查（进入审核） */
export function submitMidtermCheck(data: {
  project_id: number
  progress_desc?: string
  completed_tasks?: string
  remaining_tasks?: string
  problems?: string
  next_plan?: string
  budget_usage?: number
}) {
  return post('/api/midterm/submit', data)
}

/** 审核中期检查（教师/管理员/专家） */
export function reviewMidtermCheck(data: {
  check_id: number
  result: number
  review_comment: string
}) {
  return post('/api/midterm/review', data)
}

// ========== 变更/延期申请接口 ==========
/** 提交变更/延期申请 */
export function createChangeRequest(data: {
  project_id: number
  change_type: number
  change_reason: string
  original_content?: string
  new_content?: string
}) {
  return post('/api/changes', data)
}

/** 查询变更/延期申请列表 */
export function getChangeList(params: {
  page: number
  page_size: number
  project_id?: number
  change_type?: number
  status?: number
}) {
  return get<PageResult<{
    id: number
    project_id: number
    change_type: number
    change_type_name: string
    change_reason: string
    original_content?: string
    new_content?: string
    applicant_id: number
    status: number
    status_name: string
    reject_reason?: string
    submit_time?: string
    approval_time?: string
    created_at: string
  }>>('/api/changes', params)
}

/** 审批通过变更申请（后端 comment 通过 URL Query 传递） */
export function approveChangeRequest(changeId: number, comment?: string) {
  return service({
    method: 'post',
    url: `/api/changes/${changeId}/approve`,
    params: { comment: comment || '' },
  })
}

/** 审批驳回变更申请（后端 comment 通过 URL Query 传递） */
export function rejectChangeRequest(changeId: number, comment?: string) {
  return service({
    method: 'post',
    url: `/api/changes/${changeId}/reject`,
    params: { comment: comment || '' },
  })
}
