/**
 * 审核与过程管理接口
 *
 * 覆盖四类业务：
 *   1. 普通审核：指导教师确认、学院初审、校级复审、结题验收；
 *   2. 专家评审与专家分配；
 *   3. 中期检查的读写与审核；
 *   4. 项目变更/延期申请的提交与审批。
 * 主要调用方：
 *   - components/ReviewActionPanel.vue：各阶段审核提交与中期审核；
 *   - views/review/ReviewPending.vue、ReviewCenter.vue：待审核列表；
 *   - views/review/ChangeApproval.vue：变更申请审批；
 *   - views/expert/ExpertPending.vue：专家待评审任务；
 *   - views/project/MidtermCheck.vue：中期报告读写；
 *   - views/project/ProjectDetail.vue：审核流程与变更申请；
 *   - views/admin/AdminProjects.vue：分配评审专家。
 * 统一约定：
 *   - 列表接口返回 PageResult，page 从 1 开始；
 *   - 审核阶段 0指导教师/1学院/2校级/3专家/4结题；
 *   - 审核结果 1通过 2驳回 3修改后重提（3 已废弃）；驳回时评审意见必填，由后端校验；
 *   - 写操作成功后页面需重新拉取详情或列表，本层不负责刷新。
 */
import service, { get, post } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/**
 * 单条审核记录：用于项目详情的审批流时间线与审核工作台
 * review_result=99 是「专家已分配但未评审」的占位值，展示时需特殊处理。
 */
export interface ReviewRecord {
  /** 审核记录主键 */
  id: number
  /** 所属项目 ID */
  project_id: number
  /** 审核阶段：0指导教师确认 / 1学院初审 / 2校级复审 / 3专家评审 / 4结题验收 */
  review_stage: number
  /** 阶段中文文案，后端回填 */
  review_stage_name: string
  /** 审核人用户 ID */
  reviewer_id: number
  /** 审核人姓名快照，避免改名后历史记录失真 */
  reviewer_name: string
  /** 审核结果：1通过 / 2驳回 / 3修改后重提（已废弃） / 99已分配未评审 */
  review_result: number
  /** 结果中文文案 */
  review_result_name: string
  /** 专家评分，仅专家评审阶段有值 */
  score: number | null
  /** 评审意见，驳回时必填 */
  review_comment: string | null
  /** 审核完成时间 */
  review_time: string
  /** 记录创建时间（专家分配占位记录此时可能尚未审核） */
  created_at: string
}

/**
 * 待审核列表 GET /api/reviews
 * 后端按当前角色返回可处理的审核记录（学院管理员限本院、校级管理员全校）。
 * @param params 分页 + 项目名称/编号模糊搜索
 * 调用方：views/review/ReviewPending.vue。
 */
export function getReviewList(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 项目名称/编号关键字 */
  keyword?: string
}) {
  return get<PageResult<ReviewRecord>>('/api/reviews', params)
}

/**
 * 提交普通审核 POST /api/reviews
 * 用于指导教师确认、学院初审、校级复审、结题验收等非专家阶段。
 * @param data review_stage 见 0-4；review_result 1通过/2驳回/3修改后重提；驳回时意见必填
 * 调用方：components/ReviewActionPanel.vue、views/project/FinalCheck.vue。
 */
export function submitReview(data: {
  /** 被审核项目 ID */
  project_id: number
  /** 审核阶段：0指导教师确认 / 1学院初审 / 2校级复审 / 3专家评审 / 4结题验收 */
  review_stage: number
  /** 审核结果：1通过 / 2驳回 / 3修改后重提（已废弃） */
  review_result: number
  /** 评审意见，驳回时后端强制要求非空 */
  review_comment?: string
}) {
  return post('/api/reviews', data)
}

/**
 * 专家评审提交 POST /api/reviews/expert
 * @param data 加权总分 score、结论 review_result、意见与各维度分数
 * 通过时分数不得低于后端及格线且意见不少于 10 字；驳回必须填意见。
 * 调用方：components/ReviewActionPanel.vue。
 */
export function submitExpertReview(data: {
  /** 被评审项目 ID */
  project_id: number
  /** 加权总分（0-100），用于获奖名单排序 */
  score: number
  /** 评审结论：1通过 / 2驳回（不支持 3 修改后重提） */
  review_result: number
  /** 评审意见：通过时不少于 10 字，驳回时必填 */
  review_comment?: string
  /** 分项评分明细：创新性/可行性/团队/市场（与后端 ExpertReviewCreateRequest.dim_scores 对应） */
  dim_scores?: Record<string, number>
}) {
  return post('/api/reviews/expert', data)
}

/**
 * 分配评审专家 POST /api/reviews/assign-experts
 * 仅管理员可用，一般针对状态 13 的项目；分配后项目进入 5 待专家评审。
 * @param data expert_ids 专家用户 ID 数组（role=3）
 * 调用方：views/admin/AdminProjects.vue 分配专家弹窗。
 */
export function assignExperts(data: {
  /** 待分配专家的项目 ID */
  project_id: number
  /** 选中的专家用户 ID 列表 */
  expert_ids: number[]
}) {
  return post('/api/reviews/assign-experts', data)
}

/**
 * 专家待评审任务 GET /api/reviews/expert-tasks
 * @param params scope=pending 待评审 / reviewed 已评审；keyword 模糊搜索
 * @returns 项目摘要 + 本人评分与结论（未评审时 my_* 为 null）
 * 调用方：views/expert/ExpertPending.vue。
 */
export function getExpertTasks(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 项目名称/编号关键字 */
  keyword?: string
  /** 任务范围：pending 待评审 / reviewed 已评审 */
  scope?: 'pending' | 'reviewed'
}) {
  return get<PageResult<{
    /** 项目 ID */
    project_id: number
    /** 项目业务编号 */
    project_no: string | null
    /** 项目名称 */
    project_name: string
    /** 申报学院名称 */
    college_name: string
    /** 项目负责人姓名 */
    leader_name: string
    /** 项目类型文案 */
    project_type_name: string
    /** 项目级别文案 */
    project_level_name: string
    /** 提交时间 */
    submit_time: string | null
    /** 项目当前状态 */
    status: number
    /** 当前专家评分，未评审为 null */
    my_score: number | null
    /** 当前专家结论，未评审为 null */
    my_review_result: number | null
  }>>('/api/reviews/expert-tasks', params)
}

/**
 * 查询审核流程记录 GET /api/reviews/flow/{projectId}
 * 返回各阶段审核记录（含专家分配占位），用于详情页审批流/时间线。
 * 调用方：ProjectDetail、AdminProjects。
 */
export function getReviewHistory(projectId: number) {
  return get(`/api/reviews/flow/${projectId}`)
}

// ========== 中期检查接口 ==========
/**
 * 查询项目中期检查结果 GET /api/midterm/by-project/{projectId}
 * 一项目最多一条记录；未提交时后端可能返回空对象或 404，
 * 调用方（MidtermCheck、ReviewActionPanel）需 catch 并降级为空表单。
 * 返回结构化汇报项、报告正文、已用经费、审核状态与附件。
 */
export function getMidtermCheck(projectId: number) {
  return get<{
    /** 中期检查主键，审核/撤回时作为 check_id 使用 */
    id: number
    /** 所属项目 ID */
    project_id: number
    /** 当前进展描述 */
    progress_desc?: string
    /** 已完成任务 */
    completed_tasks?: string
    /** 剩余任务计划 */
    remaining_tasks?: string
    /** 存在的问题 */
    problems?: string
    /** 下一步计划 */
    next_plan?: string
    /** 中期报告正文 */
    report?: string
    /** 报告时点已使用经费 */
    budget_usage?: number
    /** 状态：0草稿 1待审核 2通过 3需修改 4已驳回 5已作废 */
    status: number
    /** 状态中文文案 */
    status_name: string
    /** 审核人用户 ID */
    reviewer_id?: number
    /** 审核意见 */
    review_comment?: string
    /** 审核时间 */
    review_time?: string
    /** 提交时间 */
    submit_time?: string
    /** 中期报告附件 */
    attachments?: Array<{
      /** 附件主键 */
      id: number
      /** 文件名 */
      file_name: string
      /** 文件大小（字节） */
      file_size: number
      /** 上传者姓名 */
      uploader_name?: string
      /** 下载直链 */
      download_url?: string
      /** 预览直链 */
      preview_url?: string
    }>
  }>(`/api/midterm/by-project/${projectId}`)
}

/**
 * 保存中期检查草稿 POST /api/midterm/draft
 * 可重复保存，状态保持 0 草稿，不进入审核；附件为已上传的临时附件 ID。
 * 调用方：MidtermCheck 的「保存草稿」。
 */
export function saveMidtermDraft(data: {
  /** 项目 ID */
  project_id: number
  /** 当前进展描述 */
  progress_desc?: string
  /** 已完成任务 */
  completed_tasks?: string
  /** 剩余任务计划 */
  remaining_tasks?: string
  /** 存在的问题 */
  problems?: string
  /** 下一步计划 */
  next_plan?: string
  /** 中期报告正文，上限 10000 字 */
  report?: string
  /** 已使用经费，非负两位小数 */
  budget_usage?: number
  /** 中期报告附件 ID 列表 */
  attachment_ids?: number[]
}) {
  return post('/api/midterm/draft', data)
}

/**
 * 提交中期检查 POST /api/midterm/submit
 * 提交后状态变为 1 待审核；审核通过后项目进入 8 待结题。
 * 参数与草稿一致，调用方：MidtermCheck 的「提交」。
 */
export function submitMidtermCheck(data: {
  /** 项目 ID */
  project_id: number
  /** 当前进展描述 */
  progress_desc?: string
  /** 已完成任务 */
  completed_tasks?: string
  /** 剩余任务计划 */
  remaining_tasks?: string
  /** 存在的问题 */
  problems?: string
  /** 下一步计划 */
  next_plan?: string
  /** 中期报告正文 */
  report?: string
  /** 已使用经费 */
  budget_usage?: number
  /** 附件 ID 列表 */
  attachment_ids?: number[]
}) {
  return post('/api/midterm/submit', data)
}

/**
 * 审核中期检查 POST /api/midterm/review
 * @param data result 1通过 / 2驳回 / 3修改后重提；review_comment 必填
 * 调用方：MidtermCheck 审核区、ReviewActionPanel。
 */
export function reviewMidtermCheck(data: {
  /** 中期检查记录 ID（不是项目 ID） */
  check_id: number
  /** 审核结论：1通过 / 2驳回 / 3修改后重提 */
  result: number
  /** 审核意见，必填，上限 1000 字 */
  review_comment: string
}) {
  return post('/api/midterm/review', data)
}

/**
 * 撤回中期检查提交 POST /api/midterm/withdraw?check_id=...
 * 把待审核记录退回草稿，可修改后再次提交；仅本人且状态 1 可撤回。
 * 参数走 Query 而非 body；调用方：MidtermCheck 撤回按钮。
 */
export function withdrawMidtermCheck(checkId: number) {
  return post('/api/midterm/withdraw', undefined, { params: { check_id: checkId } })
}

// ========== 变更/延期申请接口 ==========
/**
 * 提交变更/延期申请 POST /api/changes
 * @param data change_type 1延期/2人员变更/3内容变更/4预算调整/5其他；change_reason 必填
 * 同一项目累计最多 2 次（不含已撤回/已作废），后端校验配额。
 * 调用方：ProjectDetail 变更申请弹窗。
 */
export function createChangeRequest(data: {
  /** 项目 ID */
  project_id: number
  /** 变更类型：1延期 2人员变更 3内容变更 4预算调整 5其他 */
  change_type: number
  /** 变更原因，上限 1000 字 */
  change_reason: string
  /** 变更前内容，用于对照留痕 */
  original_content?: string
  /** 变更后内容 */
  new_content?: string
}) {
  return post('/api/changes', data)
}

/**
 * 查询变更/延期申请列表 GET /api/changes
 * @param params 分页 + 项目/类型/状态筛选；详情页固定传 project_id 拉全量
 * @returns 申请人、审批状态、驳回原因与时间线字段
 * 调用方：ProjectDetail、views/review/ChangeApproval.vue。
 */
export function getChangeList(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 限定某个项目的申请 */
  project_id?: number
  /** 变更类型筛选：1-5 */
  change_type?: number
  /** 审批状态：0待审核 3已通过 4已驳回 5已撤回 6已作废 */
  status?: number
}) {
  return get<PageResult<{
    /** 申请主键 */
    id: number
    /** 所属项目 ID */
    project_id: number
    /** 项目名称（列表回填） */
    project_name?: string | null
    /** 变更类型：1延期 2人员变更 3内容变更 4预算调整 5其他 */
    change_type: number
    /** 类型文案 */
    change_type_name: string
    /** 变更原因 */
    change_reason: string
    /** 变更前内容 */
    original_content?: string
    /** 变更后内容 */
    new_content?: string
    /** 申请人用户 ID */
    applicant_id: number
    /** 状态：0待审核 3通过 4驳回 5撤回 6作废 */
    status: number
    /** 状态文案 */
    status_name: string
    /** 驳回原因，仅状态 4 有值 */
    reject_reason?: string
    /** 提交时间 */
    submit_time?: string
    /** 审批完成时间 */
    approval_time?: string
    /** 创建时间 */
    created_at: string
  }>>('/api/changes', params)
}

/**
 * 审批通过变更申请 POST /api/changes/{changeId}/approve
 * 后端从 URL Query 读取 comment，不接收 JSON body。
 * @param comment 审批意见，可为空字符串
 * 调用方：ChangeApproval 通过操作；成功后申请状态变为 3。
 */
export function approveChangeRequest(changeId: number, comment?: string) {
  return service({
    method: 'post',
    url: `/api/changes/${changeId}/approve`,
    params: { comment: comment || '' },
  })
}

/**
 * 审批驳回变更申请 POST /api/changes/{changeId}/reject
 * comment 同样走 URL Query；驳回后申请人可修改重提。
 * 调用方：ChangeApproval 驳回操作（页面会要求填写理由）。
 */
export function rejectChangeRequest(changeId: number, comment?: string) {
  return service({
    method: 'post',
    url: `/api/changes/${changeId}/reject`,
    params: { comment: comment || '' },
  })
}

/**
 * 撤回变更申请 POST /api/changes/{changeId}/withdraw
 * 仅申请人本人且状态为 0 待审核时允许，撤回后状态 5，不占用提交配额。
 * 调用方：ProjectDetail 撤回操作。
 */
export function withdrawChangeRequest(changeId: number) {
  return post(`/api/changes/${changeId}/withdraw`)
}

/**
 * 重新提交被驳回的变更申请 POST /api/changes/{changeId}/resubmit
 * 复用同一条记录（不新增），状态从 4 回到 0 待审核。
 * 调用方：ProjectDetail 编辑已驳回申请后重新提交。
 */
export function resubmitChangeRequest(changeId: number, data: {
  /** 项目 ID */
  project_id: number
  /** 变更类型：1延期 2人员变更 3内容变更 4预算调整 5其他 */
  change_type: number
  /** 变更原因 */
  change_reason: string
  /** 变更前内容 */
  original_content?: string
  /** 变更后内容 */
  new_content?: string
}) {
  return post(`/api/changes/${changeId}/resubmit`, data)
}
