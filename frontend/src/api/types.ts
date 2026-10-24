/**
 * 全局类型定义与业务枚举常量
 *
 * 本模块不发起网络请求，只维护各页面共用的分页参数、项目状态、角色常量
 * 及其展示映射，供项目列表、状态标签、菜单权限等逻辑引用。
 * 状态数值必须与后端 app/models/project.py、app/schemas 中的常量保持一致，
 * 否则会出现「状态文案与实际可操作按钮不匹配」的问题。
 */

/**
 * 通用分页参数：所有列表接口均以 Query 形式携带，页码从 1 开始。
 */
export interface PaginationParams {
  /** 页码，从 1 开始；超过总页数时后端返回空 items，不报错 */
  page: number
  /** 每页条数，常见取值 10/20/50/100，由各页面表格自行决定 */
  page_size: number
}

/**
 * 通用列表查询参数：在分页基础上扩展关键字与状态筛选。
 * 索引签名用于兼容各业务模块自有筛选项（如 project_type、college_id）。
 */
export interface QueryParams extends PaginationParams {
  /** 模糊搜索关键字：项目名/编号/负责人等，具体匹配字段由后端模块决定 */
  keyword?: string
  /** 状态筛选，取值含义随模块不同（项目/报销/申请状态），不传表示全部 */
  status?: number
  /** 其它业务筛选条件，原样透传为 Query 参数 */
  [key: string]: any
}

/**
 * 项目状态常量（与后端 project.py 严格一致）
 *
 * 主流程：0 草稿 → 12 待指导教师确认 → 1 学院初审 → 3 校级复审 →
 *         13 待分配评审专家 → 5 专家评审 → 6 已立项 → 7 中期检查 →
 *         8 待结题 → 9 已结题。
 * 2/4 是「学院/校级通过」的瞬时状态，仅用于流程记录展示，前端不单独停留。
 * 10 已驳回：指导教师驳回时 resubmittable=true，可修改重提；学院及之后驳回即落选。
 * 11 已撤销：申请人主动撤回，可重新编辑提交。
 */
export const PROJECT_STATUS = {
  DRAFT: 0,               // 草稿
  PENDING_TEACHER: 12,    // 待指导教师确认
  PENDING_COLLEGE: 1,     // 待学院初审
  COLLEGE_PASSED: 2,      // 学院初审通过
  PENDING_UNIVERSITY: 3,  // 待校级复审
  UNIVERSITY_PASSED: 4,   // 校级复审通过
  PENDING_EXPERT: 5,      // 待专家评审
  PENDING_EXPERT_ASSIGN: 13, // 待分配评审专家
  APPROVED: 6,            // 已立项
  MIDTERM: 7,             // 中期检查阶段
  PENDING_FINAL: 8,       // 待结题
  FINISHED: 9,            // 已结题（归档）
  REJECTED: 10,           // 已驳回
  CANCELLED: 11,          // 已撤销
} as const

/**
 * 项目状态 → 中文文案映射
 * 被 MyProjects、AdminProjects、归档列表等表格与标签直接引用；
 * 新增状态时需同步 PROJECT_STATUS 与 STATUS_TAG_TYPES，避免页面显示「未知状态」。
 */
export const STATUS_LABELS: Record<number, string> = {
  0: '草稿',
  12: '待指导教师确认',
  1: '待学院初审',
  2: '学院初审通过',
  3: '待校级复审',
  4: '校级复审通过',
  5: '待专家评审',
  13: '待分配评审专家',
  6: '已立项',
  7: '中期检查中',
  8: '待结题',
  9: '已结题',
  10: '已驳回',
  11: '已撤销',
}

/**
 * 项目状态 → Element Plus el-tag 的 type
 * '' 表示默认主题色（蓝），用于学院/校级通过等中间态；
 * 该映射只影响标签观感，不参与任何权限或流程判断。
 */
export const STATUS_TAG_TYPES: Record<number, string> = {
  0: 'info',
  12: 'warning',
  1: 'warning',
  2: '',
  3: 'warning',
  4: '',
  5: 'warning',
  13: 'warning',
  6: 'success',
  7: 'warning',
  8: 'warning',
  9: 'success',
  10: 'danger',
  11: 'info',
}

/**
 * 角色常量：与后端 User.role 取值一致
 * 路由守卫按此值校验 meta.roles；管理员内部还需结合 college_id 细分：
 * 超管 = role 4 且无学院，学院管理员 = role 4 且绑定学院（见 store/user.ts）。
 */
export const ROLES = {
  STUDENT: 1,
  TEACHER: 2,
  EXPERT: 3,
  ADMIN: 4,
} as const

/**
 * 角色 → 展示文案
 * 用于用户管理表格、个人中心等只读展示；
 * 学院管理员在 user store 的 roleNameDisplay 中会单独改写为「学院管理员」。
 */
export const ROLE_LABELS: Record<number, string> = {
  1: '学生',
  2: '指导教师',
  3: '评审专家',
  4: '系统管理员',
}
