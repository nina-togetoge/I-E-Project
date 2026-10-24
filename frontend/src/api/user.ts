/**
 * 用户管理接口
 *
 * 覆盖用户列表、个人资料/密码、管理员的增删改与批量启停、Excel 导入模板。
 * 数据权限：后端按当前登录人注入范围（学院管理员仅本院、超管全校），
 * 前端下拉与列表筛选只是辅助，最终以接口返回为准。
 * 主要调用方：
 *   - views/admin/UserManage.vue：用户列表、新建/编辑/删除、批量启停；
 *   - views/profile/index.vue：个人资料与密码通过 store/user.ts 调用；
 *   - views/admin/AdminProjects.vue、ProjectCreate/MyProjects：按角色查教师/学生。
 */
import { get, post, put, patch, del } from '@/utils/request'
import type { PageResult } from '@/utils/request'
import type { UserInfo } from '@/store/user'

/**
 * 用户列表 GET /api/users
 * @param params 分页 + 关键字 + 角色/状态/学院筛选
 * @returns PageResult<UserInfo>，含角色、学院与登录信息
 * 调用方：UserManage 表格、AdminProjects（选专家）、项目申报（选教师/成员）。
 */
export function getUserList(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 用户名/真实姓名/学号模糊搜索 */
  keyword?: string
  /** 角色筛选：1学生 2教师 3专家 4管理员 */
  role?: number
  /** 状态筛选：1 启用 / 0 禁用 */
  status?: number
  /** 学院 ID，学院管理员默认锁定本院 */
  college_id?: number
}) {
  return get<PageResult<UserInfo>>('/api/users', params)
}

/**
 * 获取当前登录用户信息 GET /api/auth/me
 * 与 store/user.ts 的 fetchUserInfo 请求同一地址；页面通常应复用 store，
 * 避免多处维护 userInfo 副本。此处保留给需要独立刷新的场景。
 */
export function getUserInfo() {
  return get<UserInfo>('/api/auth/me')
}

/**
 * 修改当前用户资料 PATCH /api/users/me/profile
 * @param data 只允许改姓名、邮箱、手机号、头像，用户名/角色不可自改
 * 页面调用 store/user.ts 的 updateProfile（会同步 sessionStorage 缓存）。
 */
export function updateUserInfo(data: {
  /** 真实姓名 */
  real_name?: string
  /** 邮箱 */
  email?: string
  /** 手机号 */
  phone?: string
  /** 头像 URL/Base64 */
  avatar?: string
}) {
  return patch<UserInfo>('/api/users/me/profile', data)
}

/**
 * 修改密码 PATCH /api/users/me/profile
 * 与资料修改共用接口，仅传 old_password/new_password；
 * 调用方：store/user.ts 的 changePassword（个人中心，成功后清除强制改密标记）。
 */
export function changePassword(old_password: string, new_password: string) {
  return patch('/api/users/me/profile', { old_password, new_password })
}

/**
 * 创建用户 POST /api/users（管理员）
 * @param data 用户名、初始密码、姓名、角色与学院；学院管理员只能在本院创建
 * 调用方：UserManage 新建弹窗。
 */
export function createUser(data: {
  /** 登录用户名/学号/工号，唯一 */
  username: string
  /** 初始密码，建议用户首次登录后修改 */
  password: string
  /** 真实姓名 */
  real_name: string
  /** 邮箱 */
  email?: string
  /** 手机号 */
  phone?: string
  /** 角色：1学生 2教师 3专家 4管理员 */
  role: number
  /** 所属学院 ID，管理员可为空（超管） */
  college_id?: number
}) {
  return post<UserInfo>('/api/users', data)
}

/**
 * 修改用户 PUT /api/users/{id}（管理员）
 * 支持部分字段；行内启用/禁用也复用此接口，仅提交 status。
 * 调用方：UserManage 编辑弹窗与状态切换。
 */
export function updateUser(id: number, data: Partial<{
  /** 真实姓名 */
  real_name: string
  /** 邮箱 */
  email: string
  /** 手机号 */
  phone: string
  /** 角色：1-4 */
  role: number
  /** 所属学院 ID */
  college_id: number
  /** 状态：1 启用 / 0 禁用 */
  status: number
}>) {
  return put<UserInfo>(`/api/users/${id}`, data)
}

/**
 * 删除用户 DELETE /api/users/{id}（管理员）
 * 后端软删除并保留历史业务数据；调用方：UserManage 单条删除。
 */
export function deleteUser(id: number) {
  return del(`/api/users/${id}`)
}

/**
 * 批量导入用户 POST /api/excel/import/user
 * @param file Excel 文件（含用户名、姓名、角色等列，需与模板一致）
 * 预留接口：UserManage 目前使用独立的 Excel 上传组件，暂未直接调用此函数。
 */
export function importUsers(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return post('/api/excel/import/user', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/**
 * 下载用户导入模板 GET /api/excel/template/user
 * responseType=blob，返回的 res.data 即文件二进制；预留接口，页面暂未接入。
 */
export function downloadUserTemplate() {
  return get('/api/excel/template/user', {}, { responseType: 'blob' })
}

/**
 * 批量修改用户状态 PATCH /api/users/batch/status
 * @param userIds 选中的用户 ID 列表
 * @param status 1 启用 / 0 禁用
 * 调用方：UserManage 批量启用/禁用；空列表由页面按钮禁用兜底。
 */
export function batchUpdateUserStatus(userIds: number[], status: number) {
  return patch('/api/users/batch/status', { user_ids: userIds, status })
}
