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

/** 项目状态常量（与后端 project.py 严格一致：0~11） */
export const PROJECT_STATUS = {
  DRAFT: 0,               // 草稿
  PENDING_COLLEGE: 1,     // 待学院初审
  COLLEGE_PASSED: 2,      // 学院初审通过
  PENDING_UNIVERSITY: 3,  // 待校级复审
  UNIVERSITY_PASSED: 4,   // 校级复审通过
  PENDING_EXPERT: 5,      // 待专家评审
  APPROVED: 6,            // 已立项
  MIDTERM: 7,             // 中期检查阶段
  PENDING_FINAL: 8,       // 待结题
  FINISHED: 9,            // 已结题（归档）
  REJECTED: 10,           // 已驳回
  CANCELLED: 11,          // 已撤销
} as const

export const STATUS_LABELS: Record<number, string> = {
  0: '草稿',
  1: '待学院初审',
  2: '学院初审通过',
  3: '待校级复审',
  4: '校级复审通过',
  5: '待专家评审',
  6: '已立项',
  7: '中期检查中',
  8: '待结题',
  9: '已结题',
  10: '已驳回',
  11: '已撤销',
}

export const STATUS_TAG_TYPES: Record<number, string> = {
  0: 'info',
  1: 'warning',
  2: '',
  3: 'warning',
  4: '',
  5: 'warning',
  6: 'success',
  7: 'warning',
  8: 'warning',
  9: 'success',
  10: 'danger',
  11: 'info',
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
