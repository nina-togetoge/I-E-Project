/**
 * 认证相关接口
 */
import { get, post, put } from '@/utils/request'
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

export function getColleges(params?: { include_disabled?: boolean }) {
  return get('/api/colleges', params)
}

/** 新增学院（仅超级管理员） */
export function createCollege(data: {
  college_code: string
  college_name: string
  dean_id?: number
  sort_order?: number
  status?: number
}) {
  return post('/api/colleges', data)
}

/** 修改学院（仅超级管理员） */
export function updateCollege(id: number, data: {
  college_code?: string
  college_name?: string
  dean_id?: number
  sort_order?: number
  status?: number
}) {
  return put(`/api/colleges/${id}`, data)
}

export function getDictByType(dictType: string) {
  return get('/api/common/dict/' + dictType)
}
