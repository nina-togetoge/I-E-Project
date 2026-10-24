/**
 * 认证与学院基础数据接口
 *
 * 包含登录、刷新 Token、学院列表/维护、数据字典查询。
 * 注意：登录与刷新 Token 的封装主要供 store/user.ts 内部调用，
 * 页面直接使用 userStore.login/doRefreshToken，不要重复实现登录态保存逻辑。
 * 学院下拉被项目申报、用户管理、统计筛选、立项公示等多个页面复用。
 */
import { get, post, put } from '@/utils/request'
import type { UserInfo } from '@/store/user'

/**
 * 账号密码登录 POST /api/auth/login
 * @param username 用户名/学号/工号
 * @param password 明文密码（HTTPS 传输，后端 bcrypt 校验）
 * @returns access_token/refresh_token/过期秒数与 user_info
 * 调用方：store/user.ts 的 login；成功后由 store 写入 sessionStorage。
 */
export function login(username: string, password: string) {
  return post<{
    access_token: string
    refresh_token: string
    token_type: string
    expires_in: number
    user_info: UserInfo
  }>('/api/auth/login', { username, password })
}

/**
 * 刷新访问令牌 POST /api/auth/refresh
 * @param refresh_token 登录时下发的刷新令牌
 * @returns 新的 access_token 与 refresh_token（后端轮换）
 * 调用方：utils/request 的 401 处理与 store/user.ts 的 doRefreshToken；
 * 刷新失败会清空登录态并跳转登录页，不要在页面里直接调用。
 */
export function refreshToken(refresh_token: string) {
  return post<{
    access_token: string
    refresh_token: string
  }>('/api/auth/refresh', { refresh_token })
}

/**
 * 学院列表 GET /api/colleges
 * @param params include_disabled=true 时包含已停用学院（学院管理页使用）
 * @returns 学院数组（id/college_code/college_name/dean_id/status/sort_order）
 * 调用方：CollegeManage、UserManage、ProjectCreate、MyProjects、ApprovalList、
 *         admin/Statistics。
 */
export function getColleges(params?: { include_disabled?: boolean }) {
  return get('/api/colleges', params)
}

/**
 * 新增学院 POST /api/colleges（仅超级管理员）
 * @param data college_code 唯一编码、college_name 名称、dean_id 院长、sort_order 排序、status 状态
 * 调用方：views/admin/CollegeManage.vue 新建弹窗；成功后刷新学院列表。
 */
export function createCollege(data: {
  college_code: string
  college_name: string
  dean_id?: number
  sort_order?: number
  status?: number
}) {
  return post('/api/colleges', data)
}

/**
 * 修改学院 PUT /api/colleges/{id}（仅超级管理员）
 * 支持部分字段更新，学院管理页也用它切换启用/停用状态（仅传 status）。
 * 调用方：views/admin/CollegeManage.vue 编辑与停用开关。
 */
export function updateCollege(id: number, data: {
  /** 学院编码，保持唯一 */
  college_code?: string
  /** 学院名称 */
  college_name?: string
  /** 院长用户 ID */
  dean_id?: number
  /** 排序号，越小越靠前 */
  sort_order?: number
  /** 状态：1 启用 / 0 停用 */
  status?: number
}) {
  return put(`/api/colleges/${id}`, data)
}

/**
 * 按类型查询数据字典 GET /api/common/dict/{dictType}
 * @param dictType 字典类型编码（如成果类型、项目类型）
 * @returns 字典项数组，用于动态下拉/标签文案
 * 预留接口：当前页面下拉多为本地常量，暂未直接调用。
 */
export function getDictByType(dictType: string) {
  return get('/api/common/dict/' + dictType)
}
