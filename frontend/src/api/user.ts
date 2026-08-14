/**
 * 用户管理接口
 */
import { get, post, put, del } from '@/utils/request'
import type { PageResult } from '@/utils/request'
import type { UserInfo } from '@/store/user'

/** 用户列表 */
export function getUserList(params: {
  page: number
  page_size: number
  keyword?: string
  role?: number
  status?: number
  college_id?: number
}) {
  return get<PageResult<UserInfo>>('/api/users', params)
}

/** 获取个人信息 */
export function getUserInfo() {
  return get<UserInfo>('/api/users/me')
}

/** 修改个人信息 */
export function updateUserInfo(data: {
  real_name?: string
  email?: string
  phone?: string
}) {
  return put<UserInfo>('/api/users/me', data)
}

/** 修改密码 */
export function changePassword(old_password: string, new_password: string) {
  return post('/api/users/me/password', { old_password, new_password })
}

/** 创建用户 */
export function createUser(data: {
  username: string
  password: string
  real_name: string
  email?: string
  phone?: string
  role: number
  college_id?: number
}) {
  return post<UserInfo>('/api/users', data)
}

/** 修改用户 */
export function updateUser(id: number, data: Partial<{
  real_name: string
  email: string
  phone: string
  role: number
  college_id: number
  status: number
}>) {
  return put<UserInfo>(`/api/users/${id}`, data)
}

/** 删除用户 */
export function deleteUser(id: number) {
  return del(`/api/users/${id}`)
}

/** 批量导入用户 */
export function importUsers(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return post('/api/users/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 下载导入模板 */
export function downloadUserTemplate() {
  return get('/api/users/import/template', {}, { responseType: 'blob' })
}
