/**
 * Axios 请求封装
 * 统一处理：Token 携带、401自动刷新、错误提示、响应格式化
 * 增强功能：防重复提交、本地缓存、自动重试（指数退避）
 */
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import router from '@/router'
import { requestCache, CACHE_WHITELIST_REGEX, CACHE_BLACKLIST_REGEX } from '@/utils/cache'

export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
  timestamp: string
}

export interface PageResult<T = any> {
  total: number
  items: T[]
  page: number
  page_size: number
}

interface RetryConfig {
  _retryCount?: number
  maxRetries?: number
  _startTime?: number
}

const baseURL = import.meta.env.VITE_API_BASE_URL || '/'

const service: AxiosInstance = axios.create({
  baseURL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

let isRefreshing = false
let pendingRequests: Array<() => void> = []

const pendingMap = new Map<string, number>()
const PENDING_WINDOW_MS = 500 // 仅拦截极短时间内的用户双击提交

function getRequestKey(config: AxiosRequestConfig): string {
  const method = (config.method || 'GET').toUpperCase()
  const url = config.url || ''
  const dataObj = config.data
    ? (() => {
        try {
          if (typeof config.data === 'string') {
            const parsed = JSON.parse(config.data)
            return Object.fromEntries(Object.entries(parsed).slice(0, 5))
          }
          if (typeof config.data === 'object' && config.data !== null) {
            return Object.fromEntries(Object.entries(config.data as Record<string, any>).slice(0, 5))
          }
          return {}
        } catch {
          return {}
        }
      })()
    : {}
  const paramsObj = config.params
    ? Object.fromEntries(Object.entries(config.params as Record<string, any>).slice(0, 5))
    : {}
  return `${method}:${url}:${JSON.stringify(paramsObj)}:${JSON.stringify(dataObj)}`
}

function addPendingRequest(config: AxiosRequestConfig): string | null {
  // 仅对非幂等的写操作（POST/PUT/DELETE/PATCH）启用防重复提交
  // GET/HEAD/OPTIONS 是幂等查询，允许并发，mounted 阶段的重复加载不应被阻断
  if (isIdempotentMethod(config.method)) return null
  const key = getRequestKey(config)
  const now = Date.now()
  if (pendingMap.has(key)) {
    const lastTime = pendingMap.get(key)!
    if (now - lastTime < PENDING_WINDOW_MS) {
      return key
    }
  }
  pendingMap.set(key, now)
  return null
}

function removePendingRequest(config: AxiosRequestConfig): void {
  if (isIdempotentMethod(config.method)) return
  const key = getRequestKey(config)
  pendingMap.delete(key)
}

function isIdempotentMethod(method?: string): boolean {
  const m = (method || 'GET').toUpperCase()
  return m === 'GET' || m === 'HEAD'
}

function isRetriableError(error: any): boolean {
  if (error.response) {
    const status = error.response.status
    return status >= 500 && status <= 599
  }
  const code = error.code || ''
  return code === 'ERR_NETWORK' || code === 'ETIMEDOUT' || code === 'ECONNABORTED'
}

function calcRetryDelay(retryCount: number): number {
  return 1000 * Math.pow(2, retryCount) + Math.floor(Math.random() * 500)
}

service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const userStore = useUserStore()
    if (userStore.accessToken) {
      config.headers.Authorization = `Bearer ${userStore.accessToken}`
    }

    const duplicateKey = addPendingRequest(config)
    if (duplicateKey) {
      removePendingRequest(config)
      return Promise.reject(new Error('重复请求被拦截'))
    }

    const method = (config.method || 'GET').toUpperCase()
    // 先剥离 query string，只用 path 部分匹配黑白名单，避免 ?page=... 影响正则判定
    const rawUrl = config.url || ''
    const url = rawUrl.split('?')[0]

    if (method === 'GET' && !CACHE_BLACKLIST_REGEX.test(url) && CACHE_WHITELIST_REGEX.test(url)) {
      const cacheKey = requestCache.genKey(rawUrl.split('?')[0], config.params, method)
      const cached = requestCache.get<ApiResponse>(cacheKey)
      if (cached) {
        removePendingRequest(config)
        return Promise.resolve({
          ...config,
          data: {
            code: 200,
            message: 'from cache',
            data: cached.data,
            timestamp: new Date().toISOString(),
          },
          status: 200,
          statusText: 'OK',
          headers: {},
          config: config as any,
        } as AxiosResponse<ApiResponse>) as any
      }
    }

    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
      requestCache.clear()
    }

    const retryCfg = config as RetryConfig
    if (retryCfg._retryCount === undefined) {
      retryCfg._retryCount = 0
      retryCfg.maxRetries = isIdempotentMethod(config.method) ? 2 : 0
      retryCfg._startTime = Date.now()
    }

    return config
  },
  (error) => {
    if (error.config) removePendingRequest(error.config)
    return Promise.reject(error)
  }
)

service.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    removePendingRequest(response.config)

    if (response.config.responseType === 'blob') {
      return response as any
    }

    const res = response.data
    const config = response.config as AxiosRequestConfig
    const method = (config.method || 'GET').toUpperCase()
    // 同 request 拦截器：剥离 query 再匹配
    const rawUrl = config.url || ''
    const url = rawUrl.split('?')[0]

    if (res.code === 200) {
      if (method === 'GET' && !CACHE_BLACKLIST_REGEX.test(url) && CACHE_WHITELIST_REGEX.test(url)) {
        const cacheKey = requestCache.genKey(rawUrl.split('?')[0], config.params, method)
        requestCache.set(cacheKey, { data: res.data })
      }
      return res
    }

    if (res.code === 401) {
      // refresh token 接口本身返回 401，说明 refresh token 也已过期
      // 不能再递归调用 handleTokenExpired，否则会进入死锁（isRefreshing=true 导致 pendingRequests 永不 resolve）
      if (url.includes('/auth/refresh')) {
        const userStore = useUserStore()
        userStore.clearAuth()
        ElMessage.error('登录已过期，请重新登录')
        // 延迟跳转，避免在导航守卫中调用 router.push 导致路由状态混乱
        setTimeout(() => router.push('/login'), 0)
        return Promise.reject(new Error('登录已过期'))
      }
      return handleTokenExpired(response.config as any)
    }

    if (res.code === 403) {
      ElMessage.error('权限不足，无法执行此操作')
      return Promise.reject(new Error(res.message))
    }

    ElMessage.error(res.message || '请求失败')
    return Promise.reject(new Error(res.message))
  },
  async (error) => {
    if (error.config) removePendingRequest(error.config)

    // ======== 静默：用户主动取消（切页面/标签）的 abort 类错误 ========
    // 这类错误是浏览器正常行为（组件卸载时XHR被取消），不需要弹提示，也不应被ErrorBoundary当成异常
    const msg = (error.message || '').toLowerCase()
    const errCode = (error.code || '').toUpperCase()
    const isUserCancel =
      msg.includes('abort') ||
      msg.includes('canceled') ||
      msg.includes('cancelled') ||
      errCode === 'ERR_ABORTED' ||
      errCode === 'ECONNABORTED' ||
      errCode === 'ERR_CANCELED' ||
      error.name === 'CanceledError' ||
      (error as any).__CANCELLED__ === true
    if (isUserCancel) {
      console.warn('[request] 请求被取消/abort（组件卸载或用户切换），已忽略:', error.config?.url)
      return Promise.reject(error) // 保持reject，让调用方await进入catch，但不传ElMessage
    }

    if (error.message === '重复请求被拦截') {
      // 重复提交拦截（仅POST等写操作会命中），同样静默不弹 toast，避免干扰
      console.warn('[request] 重复请求已忽略:', error.config?.url)
      return Promise.reject(error)
    }

    if (error.response?.status === 401) {
      // refresh token 接口返回 HTTP 401，同样说明 refresh token 已过期
      const errUrl = (error.config?.url || '').split('?')[0]
      if (errUrl.includes('/auth/refresh')) {
        const userStore = useUserStore()
        userStore.clearAuth()
        ElMessage.error('登录已过期，请重新登录')
        setTimeout(() => router.push('/login'), 0)
        return Promise.reject(error)
      }
      return handleTokenExpired(error.config)
    }

    const config = error.config as (AxiosRequestConfig & RetryConfig) | undefined
    if (
      config &&
      isIdempotentMethod(config.method) &&
      isRetriableError(error) &&
      (config._retryCount || 0) < (config.maxRetries || 0)
    ) {
      config._retryCount = (config._retryCount || 0) + 1
      const delay = calcRetryDelay(config._retryCount)
      await new Promise((resolve) => setTimeout(resolve, delay))
      return service(config)
    }

    const msgFinal = error.response?.data?.message || error.message || '网络异常'
    ElMessage.error(msgFinal)
    return Promise.reject(error)
  }
)

async function handleTokenExpired(config: AxiosRequestConfig): Promise<any> {
  const userStore = useUserStore()

  if (!userStore.refreshToken) {
    userStore.clearAuth()
    // 延迟跳转，避免在导航守卫中调用 router.push 导致路由状态混乱
    setTimeout(() => router.push('/login'), 0)
    return Promise.reject(new Error('未登录'))
  }

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
    if (config.headers) {
      config.headers.Authorization = `Bearer ${userStore.accessToken}`
    }
    pendingRequests.forEach((cb) => cb())
    pendingRequests = []
    return service(config)
  } catch (refreshError) {
    userStore.clearAuth()
    // 延迟跳转，避免在导航守卫中调用 router.push 导致路由状态混乱
    setTimeout(() => router.push('/login'), 0)
    ElMessage.error('登录已过期，请重新登录')
    return Promise.reject(refreshError)
  } finally {
    isRefreshing = false
  }
}

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

export function get<T = any>(url: string, params?: Record<string, any>, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'get', url, params: cleanParams(params), ...config })
}

export function post<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'post', url, data, ...config })
}

export function put<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'put', url, data, ...config })
}

export function patch<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'patch', url, data, ...config })
}

export function del<T = any>(url: string, params?: Record<string, any>, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'delete', url, params: cleanParams(params), ...config })
}

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
