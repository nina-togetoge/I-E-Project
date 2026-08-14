/**
 * 全局类型定义
 */
export interface PaginationParams {
  page: number
  page_size: number
}

export interface QueryParams extends PaginationParams {
  keyword?: string
  status?: number
  [key: string]: any
}

/** 项目状态常量 */
export const PROJECT_STATUS = {
  DRAFT: 0,
  PENDING_REVIEW: 10,
  COLLEGE_REVIEW: 20,
  SCHOOL_REVIEW: 30,
  EXPERT_REVIEW: 40,
  APPROVED: 50,
  REJECTED: 60,
  IN_PROGRESS: 70,
  MIDTERM_CHECK: 80,
  ARCHIVED: 90,
} as const

export const STATUS_LABELS: Record<number, string> = {
  0: '草稿',
  10: '待审核',
  20: '学院初审中',
  30: '校级复审中',
  40: '专家评审中',
  50: '已立项',
  60: '已驳回',
  70: '进行中',
  80: '中期检查',
  90: '已归档',
}

export const STATUS_TAG_TYPES: Record<number, string> = {
  0: 'info',
  10: 'warning',
  20: 'warning',
  30: 'warning',
  40: 'warning',
  50: 'success',
  60: 'danger',
  70: '',
  80: 'warning',
  90: 'success',
}

/** 角色常量 */
export const ROLES = {
  STUDENT: 1,
  TEACHER: 2,
  EXPERT: 3,
  ADMIN: 4,
} as const

export const ROLE_LABELS: Record<number, string> = {
  1: '学生',
  2: '指导教师',
  3: '评审专家',
  4: '系统管理员',
}
