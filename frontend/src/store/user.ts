/**
 * 用户状态管理（Pinia）
 *
 * 全局唯一的登录态来源：Token、当前用户信息、角色及其派生权限。
 * 生命周期：应用启动时从 sessionStorage 恢复 Token；路由守卫在 userInfo 为空时
 * 调用 fetchUserInfo 拉取 /api/auth/me；退出登录或刷新失败时 clearAuth 清空全部状态。
 *
 * Token 持久化：
 *   - access_token / refresh_token / user_info 均写入 sessionStorage；
 *   - 选择 sessionStorage 而非 localStorage，关闭标签页即失效，降低共用电脑风险；
 *   - 401 时由 utils/request 调用 doRefreshToken 续期并重放排队请求。
 *
 * 登录/登出流程：
 *   - login：POST /api/auth/login → 同时写入内存与 sessionStorage；
 *   - logout：先调用 /api/auth/logout 吊销 Token（失败也忽略），finally 清理本地；
 *   - clearAuth：只清本地，不请求后端，供 401/刷新失败时使用。
 *
 * 角色与权限：
 *   - 学生 1 / 教师 2 / 专家 3 / 管理员 4；
 *   - isAdmin 仅判断 role=4；超管与学院管理员再用 college_id 细分；
 *   - 路由 meta.roles 由 router 守卫直接比对 role，本 store 的 computed 供页面按钮级控制。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { get, post, put, patch } from '@/utils/request'

/**
 * 用户信息：登录接口与 /api/auth/me 返回的统一结构。
 * college_id 是管理员细分与数据权限的关键字段。
 */
export interface UserInfo {
  /** 用户主键 */
  id: number
  /** 登录用户名/学号/工号 */
  username: string
  /** 真实姓名，列表与审批记录展示用 */
  real_name: string
  /** 邮箱，可为空 */
  email: string | null
  /** 手机号，可为空 */
  phone: string | null
  /** 角色：1-学生 2-教师 3-专家 4-管理员 */
  role: number          // 1-学生 2-教师 3-专家 4-管理员
  /** 角色文案，后端回填 */
  role_name: string
  /** 所属学院 ID；管理员为空表示超级管理员，决定数据范围 */
  college_id: number | null
  /** 学院名称 */
  college_name: string | null
  /** 年级（仅学生有值，如 2023） */
  grade: string | null   // 年级（仅学生有值，如 2023）
  /** 学校名称，用于顶栏/个人中心展示 */
  school_name: string
  /** 头像 URL，可为空 */
  avatar: string | null
  /** 账号状态：1 启用 / 0 禁用 */
  status: number
  /** 首次登录强制改密: 0-否 1-是；为 1 时路由守卫只放行改密页 */
  force_change_pwd: number  // 首次登录强制改密: 0-否 1-是
  /** 最近登录时间 */
  last_login_at: string | null
  /** 账号创建时间 */
  created_at: string
}

export const useUserStore = defineStore('user', () => {
  // ========== State ==========
  /** 访问令牌：请求拦截器读取它写入 Authorization 头；从 sessionStorage 恢复 */
  const accessToken = ref<string>(sessionStorage.getItem('access_token') || '')
  /** 刷新令牌：access_token 过期时用于换取新令牌；同样存 sessionStorage */
  const refreshToken = ref<string>(sessionStorage.getItem('refresh_token') || '')
  /** 当前用户信息：初始为空，由路由守卫或登录流程填充 */
  const userInfo = ref<UserInfo | null>(null)

  // ========== Getters ==========
  /** 是否已登录：仅看 accessToken，userInfo 可能尚未拉取 */
  const isLoggedIn = computed(() => !!accessToken.value)
  /** 当前角色数值：未登录/未拉取用户信息时为 0，页面权限判断以此为准 */
  const role = computed(() => userInfo.value?.role || 0)
  /** 后端返回的角色文案（如「系统管理员」） */
  const roleName = computed(() => userInfo.value?.role_name || '')
  /** 所属学院 ID：超管为 null/0，学院管理员为具体值 */
  const collegeId = computed(() => userInfo.value?.college_id ?? null)
  /** 学校名称，个人中心与顶栏兜底展示 */
  const schoolName = computed(() => userInfo.value?.school_name || '')
  /** 学院/学校显示名：有学院显示学院名，否则显示学校名 */
  const displayCollegeName = computed(() => userInfo.value?.college_name || schoolName.value)
  const isAdmin = computed(() => role.value === 4)

  /** 真·超级管理员（对应后端 is_super_admin）：role=4 且 未绑定学院（college_id=null/0） */
  const isSuperAdmin = computed(() => (
    role.value === 4 && (collegeId.value === null || collegeId.value === 0 || collegeId.value === undefined)
  ))

  /** 学院管理员（对应后端 is_college_admin）：role=4 且 已绑定具体 college_id */
  const isCollegeAdmin = computed(() => (
    role.value === 4 && collegeId.value !== null && collegeId.value !== 0 && collegeId.value !== undefined
  ))

  /** 角色展示名：学院管理员单独显示「学院管理员」，避免和 super_admin 混淆 */
  const roleNameDisplay = computed(() => {
    if (isCollegeAdmin.value) return '学院管理员'
    if (isSuperAdmin.value) return '系统管理员'
    return roleName.value
  })

  /** 是否学生（role=1）：决定「项目申报」「我的证书」等入口 */
  const isStudent = computed(() => role.value === 1)
  /** 是否指导教师（role=2）：可见「审核工作台」「我的项目」等 */
  const isTeacher = computed(() => role.value === 2)
  /** 是否评审专家（role=3）：可见「待评审项目」入口 */
  const isExpert = computed(() => role.value === 3)

  // ========== Actions ==========
  /**
   * 登录 POST /api/auth/login
   * 成功后同时更新内存状态与 sessionStorage，供刷新页面后恢复；
   * 失败由请求拦截器提示，本函数不捕获，调用方需 try/catch 处理跳转。
   * @param username 用户名/学号/工号
   * @param password 明文密码
   */
  async function login(username: string, password: string) {
    const res = await post<{
      access_token: string
      refresh_token: string
      token_type: string
      expires_in: number
      user_info: UserInfo
    }>('/api/auth/login', { username, password })
    // 后端统一响应格式：{ code, message, data: LoginResponse }
    // 注意：LoginResponse.user_info 才是用户对象，不要和外层 data 混淆
    const payload = res.data
    accessToken.value = payload.access_token
    refreshToken.value = payload.refresh_token
    const info: UserInfo = payload.user_info
    userInfo.value = info
    sessionStorage.setItem('access_token', payload.access_token)
    sessionStorage.setItem('refresh_token', payload.refresh_token)
    sessionStorage.setItem('user_info', JSON.stringify(info))
  }

  /**
   * 刷新 Token POST /api/auth/refresh
   * 由 utils/request 在收到 401 时调用（别名 doRefreshToken），
   * 刷新成功后轮换两个 Token 并覆盖 sessionStorage；失败直接抛错，
   * 由拦截器统一 clearAuth 并跳登录页，页面不应直接调用。
   */
  async function refreshTokenAction() {
    const res = await post<{
      access_token: string
      refresh_token: string
    }>('/api/auth/refresh', { refresh_token: refreshToken.value })
    accessToken.value = res.data.access_token
    refreshToken.value = res.data.refresh_token
    sessionStorage.setItem('access_token', res.data.access_token)
    sessionStorage.setItem('refresh_token', res.data.refresh_token)
  }

  /**
   * 拉取当前用户信息 GET /api/auth/me
   * 先用 sessionStorage 缓存的 user_info 立即回填，避免刷新时页面空白，
   * 再请求后端覆盖最新数据（角色/学院可能被管理员调整）。
   * 请求失败时静默保留缓存；若 Token 已失效，拦截器会清空登录态，
   * 路由守卫随后跳转登录页。调用方：router.beforeEach。
   */
  async function fetchUserInfo() {
    const cached = sessionStorage.getItem('user_info')
    if (cached) {
      userInfo.value = JSON.parse(cached)
    }
    try {
      const res = await get<UserInfo>('/api/auth/me')
      userInfo.value = res.data
      sessionStorage.setItem('user_info', JSON.stringify(res.data))
    } catch {
      // 如果获取失败且有缓存，继续使用缓存
    }
  }

  /**
   * 更新个人资料 PATCH /api/users/me/profile
   * 成功后同步内存 userInfo 与 sessionStorage 缓存，顶栏头像/姓名即时生效。
   * @param data 可只传需要修改的字段；调用方：views/profile/index.vue。
   */
  async function updateProfile(data: { real_name?: string; email?: string; phone?: string; avatar?: string }) {
    const res = await patch<UserInfo>('/api/users/me/profile', data)
    userInfo.value = res.data
    sessionStorage.setItem('user_info', JSON.stringify(res.data))
    return res.data
  }

  /**
   * 修改密码 PATCH /api/users/me/profile
   * 成功后把 force_change_pwd 置 0 并更新缓存，解除路由守卫的强制改密拦截。
   * 旧密码错误/新密码不合规由后端返回，拦截器统一提示。
   * @param oldPassword 当前密码
   * @param newPassword 新密码
   * 调用方：views/profile/index.vue 的密码 Tab。
   */
  async function changePassword(oldPassword: string, newPassword: string) {
    await patch('/api/users/me/profile', {
      old_password: oldPassword,
      new_password: newPassword,
    })
    // 改密成功后，清零强制改密标志
    if (userInfo.value) {
      userInfo.value.force_change_pwd = 0
      sessionStorage.setItem('user_info', JSON.stringify(userInfo.value))
    }
  }

  /**
   * 退出登录 POST /api/auth/logout
   * 后端把 access_token 与 refresh_token 加入黑名单；无论请求成功与否，
   * finally 都会 clearAuth，保证本地一定能退出。调用方：顶栏用户菜单。
   */
  async function logout() {
    try {
      // 后端会同时从 Authorization 头提取 access_token，并把 refresh_token 一并加入 Redis 黑名单
      await post('/api/auth/logout', { refresh_token: refreshToken.value })
    } catch {
      // 忽略后端错误，确保本地登出始终执行
    } finally {
      clearAuth()
    }
  }

  /**
   * 清除本地认证信息（不发请求）
   * 同时清空内存 Token/userInfo 与 sessionStorage 三个缓存键；
   * 调用场景：主动登出的 finally、refresh token 失效、请求 401 无法续期。
   */
  function clearAuth() {
    accessToken.value = ''
    refreshToken.value = ''
    userInfo.value = null
    sessionStorage.removeItem('access_token')
    sessionStorage.removeItem('refresh_token')
    sessionStorage.removeItem('user_info')
  }

  return {
    accessToken,
    refreshToken,
    userInfo,
    isLoggedIn,
    role,
    roleName,
    roleNameDisplay,
    collegeId,
    schoolName,
    displayCollegeName,
    isAdmin,
    isSuperAdmin,
    isCollegeAdmin,
    isStudent,
    isTeacher,
    isExpert,
    login,
    doRefreshToken: refreshTokenAction,
    fetchUserInfo,
    updateProfile,
    changePassword,
    logout,
    clearAuth,
  }
})