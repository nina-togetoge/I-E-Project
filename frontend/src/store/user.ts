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
  avatar: string | null
  status: number
  last_login_at: string | null
  created_at: string
}

export const useUserStore = defineStore('user', () => {
  // ========== State ==========
  const accessToken = ref<string>(localStorage.getItem('access_token') || '')
  const refreshToken = ref<string>(localStorage.getItem('refresh_token') || '')
  const userInfo = ref<UserInfo | null>(null)

  // ========== Getters ==========
  const isLoggedIn = computed(() => !!accessToken.value)
  const role = computed(() => userInfo.value?.role || 0)
  const roleName = computed(() => userInfo.value?.role_name || '')
  const isAdmin = computed(() => role.value === 4)
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

    accessToken.value = res.data.access_token
    refreshToken.value = res.data.refresh_token
    userInfo.value = res.data.user_info

    localStorage.setItem('access_token', res.data.access_token)
    localStorage.setItem('refresh_token', res.data.refresh_token)
    localStorage.setItem('user_info', JSON.stringify(res.data.user_info))
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

    localStorage.setItem('access_token', res.data.access_token)
    localStorage.setItem('refresh_token', res.data.refresh_token)
  }

  /**
   * 获取当前用户信息
   */
  async function fetchUserInfo() {
    const cached = localStorage.getItem('user_info')
    if (cached) {
      userInfo.value = JSON.parse(cached)
    }
    try {
      const res = await get<UserInfo>('/api/auth/me')
      userInfo.value = res.data
      localStorage.setItem('user_info', JSON.stringify(res.data))
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
    localStorage.setItem('user_info', JSON.stringify(res.data))
    return res.data
  }

  async function changePassword(oldPassword: string, newPassword: string) {
    await patch('/api/users/me/profile', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  }

  /**
   * 退出登录
   */
  function logout() {
    clearAuth()
  }

  /**
   * 清除认证信息
   */
  function clearAuth() {
    accessToken.value = ''
    refreshToken.value = ''
    userInfo.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_info')
  }

  return {
    accessToken,
    refreshToken,
    userInfo,
    isLoggedIn,
    role,
    roleName,
    isAdmin,
    isStudent,
    isTeacher,
    isExpert,
    login,
    refreshToken: refreshTokenAction,
    fetchUserInfo,
    updateProfile,
    changePassword,
    logout,
    clearAuth,
  }
})
