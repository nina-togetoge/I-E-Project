/**
 * 创新创业大赛接口
 *
 * 覆盖比赛浏览（学生/教师/专家）、比赛管理（管理员）与获奖名单生成。
 * 主要调用方：
 *   - views/competition/CompetitionList.vue：比赛列表与详情弹窗；
 *   - views/competition/CompetitionManage.vue：管理员新建/编辑/上下线/生成获奖名单；
 *   - views/project/ProjectCreate.vue、MyProjects.vue：申报时选择可报名比赛；
 *   - views/announcement/ApprovalList.vue 等列表复用 competitionLabel 展示名称。
 * 统一约定：列表返回 PageResult，page 从 1 开始；比赛状态以 status 为准，
 * 学生端仅能看到「报名中/进行中」的比赛，申报提交时后端会再次校验状态。
 */
import { get, post, put, del, patch } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/**
 * 比赛列表项：列表卡片/表格使用，含报名与各阶段时间节点。
 * 比赛级别决定是否支持自动生成获奖名单（仅校级）。
 */
export interface CompetitionListItem {
  /** 比赛主键 */
  id: number
  /** 比赛名称，如「互联网+」 */
  title: string
  /** 届次，如「2026届」，可为空 */
  session: string | null
  /** 比赛类型：1 创新训练类 / 2 创业实践类 / 3 学科竞赛类 / 4 综合类 */
  competition_type: number
  /** 比赛类型文案 */
  competition_type_name: string
  /** 比赛级别：1 校级 / 2 省级 / 3 国家级 */
  level: number
  /** 比赛级别文案 */
  level_name: string
  /** 主办方 */
  organizer: string | null
  /** 报名开始时间 */
  registration_start: string | null
  /** 报名截止时间 */
  registration_end: string | null
  /** 比赛开始时间 */
  competition_start: string | null
  /** 比赛结束时间 */
  competition_end: string | null
  /** 学院初审时间节点 */
  college_review_date: string | null
  /** 校级复审时间节点 */
  university_review_date: string | null
  /** 专家评审时间节点 */
  expert_review_date: string | null
  /** 关联项目的中期检查截止时间 */
  midterm_deadline: string | null
  /** 关联项目的结题截止时间 */
  final_deadline: string | null
  /** 比赛地点 */
  location: string | null
  /** 封面图 URL */
  cover_image: string | null
  /** 比赛状态：0 草稿 / 1 报名中 / 2 进行中 / 3 已结束 / 4 已取消 */
  status: number
  /** 状态文案 */
  status_name: string
  /** 浏览次数，用于热度排序/展示 */
  view_count: number
  /** 创建时间 */
  created_at: string
}

/**
 * 比赛详情：在列表项基础上补充简介、参赛要求、奖励、联系方式与官方链接。
 * 调用方：CompetitionList 详情弹窗、CompetitionManage 编辑回填。
 */
export interface CompetitionDetail extends CompetitionListItem {
  /** 承办方 */
  co_organizer: string | null
  /** 比赛简介（富文本/长文本） */
  description: string | null
  /** 参赛要求 */
  requirements: string | null
  /** 奖励设置 */
  rewards: string | null
  /** 联系人/联系方式 */
  contact: string | null
  /** 官方报名或通知链接 */
  official_url: string | null
  /** 创建人用户 ID，系统预置数据可能为空 */
  created_by: number | null
  /** 创建人姓名 */
  creator_name: string | null
}

/**
 * 比赛创建/更新参数
 * 与后端 CompetitionCreate/Update Schema 对齐，除必填项外均可留空，
 * 日期字段为 ISO 字符串（YYYY-MM-DD 或带时间）。
 */
export interface CompetitionForm {
  /** 比赛名称（必填） */
  title: string
  /** 届次 */
  session?: string
  /** 比赛类型：1-4 */
  competition_type: number
  /** 比赛级别：1 校级 / 2 省级 / 3 国家级 */
  level: number
  /** 主办方 */
  organizer?: string
  /** 承办方 */
  co_organizer?: string
  /** 简介 */
  description?: string
  /** 参赛要求 */
  requirements?: string
  /** 奖励设置 */
  rewards?: string
  /** 报名开始时间 */
  registration_start?: string
  /** 报名截止时间 */
  registration_end?: string
  /** 比赛开始时间 */
  competition_start?: string
  /** 比赛结束时间 */
  competition_end?: string
  /** 学院初审时间节点 */
  college_review_date?: string
  /** 校级复审时间节点 */
  university_review_date?: string
  /** 专家评审时间节点 */
  expert_review_date?: string
  /** 中期检查截止时间 */
  midterm_deadline?: string
  /** 结题截止时间 */
  final_deadline?: string
  /** 地点 */
  location?: string
  /** 联系方式 */
  contact?: string
  /** 封面图 URL */
  cover_image?: string
  /** 官方链接 */
  official_url?: string
  /** 状态：0 草稿 / 1 报名中 / 2 进行中 / 3 已结束 / 4 已取消 */
  status: number
}

/**
 * 比赛列表 GET /api/competitions
 * 学生端后端只返回状态 1/2 的比赛；管理端可通过 status 查看全部。
 * @param params 分页 + 关键字 + 类型/级别/状态筛选
 * @returns PageResult<CompetitionListItem>
 * 调用方：CompetitionList、CompetitionManage、ProjectCreate（比赛下拉）。
 */
export function getCompetitionList(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 比赛名称/届次/主办方模糊搜索 */
  keyword?: string
  /** 比赛类型：1-4 */
  competition_type?: number
  /** 比赛级别：1校级 2省级 3国家级 */
  level?: number
  /** 比赛状态：0草稿 1报名中 2进行中 3已结束 4已取消 */
  status?: number
}) {
  return get<PageResult<CompetitionListItem>>('/api/competitions', params)
}

/**
 * 比赛详情 GET /api/competitions/{id}
 * 返回简介、要求、奖励与各阶段时间节点；学生端通常只读。
 * 调用方：CompetitionList 详情弹窗、CompetitionManage 编辑回填/查看。
 */
export function getCompetitionDetail(id: number) {
  return get<CompetitionDetail>(`/api/competitions/${id}`)
}

/**
 * 创建比赛 POST /api/competitions
 * 仅管理员可调用；成功后返回完整详情，调用方用它刷新列表。
 * 调用方：CompetitionManage 新建弹窗。
 */
export function createCompetition(data: CompetitionForm) {
  return post<CompetitionDetail>('/api/competitions', data)
}

/**
 * 更新比赛 PUT /api/competitions/{id}
 * 全量提交表单字段，仅管理员可调用；调用方：CompetitionManage 编辑弹窗。
 */
export function updateCompetition(id: number, data: CompetitionForm) {
  return put<CompetitionDetail>(`/api/competitions/${id}`, data)
}

/**
 * 删除比赛 DELETE /api/competitions/{id}
 * 后端为软删除，已有关联项目时可能被拒绝；调用方：CompetitionManage。
 */
export function deleteCompetition(id: number) {
  return del(`/api/competitions/${id}`)
}

/**
 * 修改比赛状态 PATCH /api/competitions/{id}/status
 * status 通过 URL Query 传递（不是 body），用于草稿发布、结束或取消比赛。
 * 调用方：CompetitionManage 状态切换；成功后刷新行数据。
 */
export function updateCompetitionStatus(id: number, status: number) {
  return patch<CompetitionDetail>(`/api/competitions/${id}/status`, undefined, { params: { status } })
}

/**
 * 生成比赛显示名称：名称 + 届次，如「互联网+（2026届）」
 * 纯前端格式化函数，无网络请求；MyProjects、ProjectCreate 的下拉选项使用。
 * @param c 至少包含 title，session 可空
 */
export function competitionLabel(c: { title: string; session?: string | null }): string {
  return c.session ? `${c.title}（${c.session}）` : c.title
}

/**
 * 判断比赛当前是否可被申报选择：仅状态 1 报名中 / 2 进行中
 * 与后端提交时的状态校验保持一致，避免前端展示不可申报的比赛。
 * 纯函数，无副作用；调用方：MyProjects、ProjectCreate 过滤比赛下拉。
 */
export function isCompetitionSelectable(c: { status: number }): boolean {
  return [1, 2].includes(c.status)
}

/**
 * 获奖名单中的单个项目：按专家平均分排名后确定获奖等级。
 */
export interface AwardItem {
  /** 获奖项目 ID */
  project_id: number
  /** 项目名称 */
  project_name: string
  /** 专家平均分，用于排名与公示 */
  average_score: number
  /** 名次（从 1 开始） */
  rank: number
  /** 获奖等级文案（一等奖/二等奖/三等奖） */
  award_level: string
}

/**
 * 获奖名单分组：按项目负责人所属学院聚合，便于分学院公示。
 */
export interface AwardGroup {
  /** 学院 ID */
  college_id: number
  /** 学院名称，未知时为空 */
  college_name: string | null
  /** 该学院的获奖项目 */
  items: AwardItem[]
}

/**
 * 获奖名单生成结果：一次生成返回比赛信息与全部分组。
 */
export interface AwardGenerateResult {
  /** 比赛 ID */
  competition_id: number
  /** 比赛名称 */
  competition_title: string
  /** 届次 */
  session: string | null
  /** 获奖项目总数 */
  total_awarded: number
  /** 按学院分组的获奖名单 */
  groups: AwardGroup[]
}

/**
 * 生成获奖名单 POST /api/competitions/{id}/generate-awards
 * 仅校级比赛且由管理员手动触发；后端按专家平均分排名并划分等级、生成证书。
 * 调用方：CompetitionManage「生成获奖名单」；返回结果用于弹窗预览/公示。
 */
export function generateCompetitionAwards(id: number) {
  return post<AwardGenerateResult>(`/api/competitions/${id}/generate-awards`)
}
