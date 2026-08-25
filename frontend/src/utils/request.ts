/**
 * Axios 请求封装
 * 统一处理：Token 携带、401自动刷新、错误提示、响应格式化
 */
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import router from '@/router'

/** 后端统一响应格式 */
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
  timestamp: string
}

/** 分页结果 */
export interface PageResult<T = any> {
  total: number
  items: T[]
  page: number
  page_size: number
}

const baseURL = import.meta.env.VITE_API_BASE_URL || '/'

const service: AxiosInstance = axios.create({
  baseURL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 是否正在刷新 Token
let isRefreshing = false
let pendingRequests: Array<() => void> = []

// ==================== 请求拦截器 ====================
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const userStore = useUserStore()
    if (userStore.accessToken) {
      config.headers.Authorization = `Bearer ${userStore.accessToken}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ==================== 响应拦截器 ====================
service.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    const res = response.data

    // 二进制文件直接返回
    if (response.config.responseType === 'blob') {
      return response as any
    }

    if (res.code === 200) {
      return res
    }

    // 401: Token 过期
    if (res.code === 401) {
      return handleTokenExpired(response.config as any)
    }

    // 403: 权限不足
    if (res.code === 403) {
      ElMessage.error('权限不足，无法执行此操作')
      return Promise.reject(new Error(res.message))
    }

    // 其他业务错误
    ElMessage.error(res.message || '请求失败')
    return Promise.reject(new Error(res.message))
  },
  (error) => {
    if (error.response?.status === 401) {
      return handleTokenExpired(error.config)
    }
    const msg = error.response?.data?.message || error.message || '网络异常'
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

/**
 * Token 过期处理：尝试用 refreshToken 刷新
 */
async function handleTokenExpired(config: AxiosRequestConfig): Promise<any> {
  const userStore = useUserStore()

  if (!userStore.refreshToken) {
    userStore.clearAuth()
    router.push('/login')
    return Promise.reject(new Error('未登录'))
  }

  // 如果已经在刷新，排队等待
  if (isRefreshing) {
    return new Promise((resolve) => {
      pendingRequests.push(() => {
        if (config.headers) {
          config.headers.Authorization = `Bearer ${userStore.accessToken}`
        }
        resolve(service(config))
      })
    })
  }

  isRefreshing = true
  try {
    await userStore.doRefreshToken()
    // 重试原请求
    if (config.headers) {
      config.headers.Authorization = `Bearer ${userStore.accessToken}`
    }
    // 执行排队的请求
    pendingRequests.forEach((cb) => cb())
    pendingRequests = []
    return service(config)
  } catch (refreshError) {
    userStore.clearAuth()
    router.push('/login')
    ElMessage.error('登录已过期，请重新登录')
    return Promise.reject(refreshError)
  } finally {
    isRefreshing = false
  }
}

/** 清理 params 中的 undefined/null 值，避免序列化出 "undefined" 字符串 */
function cleanParams(params?: Record<string, any>): Record<string, any> | undefined {
  if (!params) return undefined
  const cleaned: Record<string, any> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      cleaned[key] = value
    }
  }
  return Object.keys(cleaned).length > 0 ? cleaned : undefined
}

/** GET 请求 */
export function get<T = any>(url: string, params?: Record<string, any>, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'get', url, params: cleanParams(params), ...config })
}

/** POST 请求 */
export function post<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'post', url, data, ...config })
}

/** PUT 请求 */
export function put<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'put', url, data, ...config })
}

/** PATCH 请求 */
export function patch<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'patch', url, data, ...config })
}

/** DELETE 请求 */
export function del<T = any>(url: string, params?: Record<string, any>, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'delete', url, params: cleanParams(params), ...config })
}

/** 文件上传 */
export function upload<T = any>(url: string, file: File | File[], config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  const formData = new FormData()
  if (Array.isArray(file)) {
    file.forEach((f) => formData.append('files', f))
  } else {
    formData.append('file', file)
  }
  return service({
    method: 'post',
    url,
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    ...config,
  })
}

/** 文件下载 */
export async function download(url: string, params?: Record<string, any>, filename?: string): Promise<void> {
  const res = await service({ method: 'get', url, params: cleanParams(params), responseType: 'blob' })
  const blob = new Blob([res.data])
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename || 'download'
  link.click()
  URL.revokeObjectURL(link.href)
}

export default service
