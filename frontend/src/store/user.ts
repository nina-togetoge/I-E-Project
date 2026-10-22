/**
 * 用户状态管理（Pinia）
 * 管理用户登录状态、Token、角色权限
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { get, post, put, patch } from '@/utils/request'

/** 用户信息接口 */
export interface UserInfo {
  id: number
  username: string
  real_name: string
  email: string | null
  phone: string | null
  role: number          // 1-学生 2-教师 3-专家 4-管理员
  role_name: string
  college_id: number | null
  college_name: string | null
  grade: string | null   // 年级（仅学生有值，如 2023）
  school_name: string
  avatar: string | null
  status: number
  force_change_pwd: number  // 首次登录强制改密: 0-否 1-是
  last_login_at: string | null
  created_at: string
}

export const useUserStore = defineStore('user', () => {
  // ========== State ==========
  const accessToken = ref<string>(sessionStorage.getItem('access_token') || '')
  const refreshToken = ref<string>(sessionStorage.getItem('refresh_token') || '')
  const userInfo = ref<UserInfo | null>(null)

  // ========== Getters ==========
  const isLoggedIn = computed(() => !!accessToken.value)
  const role = computed(() => userInfo.value?.role || 0)
  const roleName = computed(() => userInfo.value?.role_name || '')
  const collegeId = computed(() => userInfo.value?.college_id ?? null)
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

  const isStudent = computed(() => role.value === 1)
  const isTeacher = computed(() => role.value === 2)
  const isExpert = computed(() => role.value === 3)

  // ========== Actions ==========
  /**
   * 登录
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
   * 刷新 Token
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
   * 获取当前用户信息
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
   * 更新个人信息
   */
  async function updateProfile(data: { real_name?: string; email?: string; phone?: string; avatar?: string }) {
    const res = await patch<UserInfo>('/api/users/me/profile', data)
    userInfo.value = res.data
    sessionStorage.setItem('user_info', JSON.stringify(res.data))
    return res.data
  }

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
   * 退出登录（调用后端接口吊销 Token，失败也强制本地清理）
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
   * 清除认证信息
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