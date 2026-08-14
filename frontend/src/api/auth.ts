/**
 * 认证相关接口
 */
import { get, post } from '@/utils/request'
import type { UserInfo } from '@/store/user'

export function login(username: string, password: string) {
  return post<{
    access_token: string
    refresh_token: string
    token_type: string
    expires_in: number
    user_info: UserInfo
  }>('/api/auth/login', { username, password })
}

export function refreshToken(refresh_token: string) {
  return post<{
    access_token: string
    refresh_token: string
  }>('/api/auth/refresh', { refresh_token })
}

export function register(data: {
  username: string
  password: string
  real_name: string
  email: string
  college_id?: number
}) {
  return post<UserInfo>('/api/auth/register', data)
}

export function getColleges() {
  return get('/api/colleges')
}

export function getDictByType(dictType: string) {
  return get('/api/dict/list', { dict_type: dictType })
}
