/**
 * Axios 请求封装
 * 统一处理：Token 携带、401自动刷新、错误提示、响应格式化
 * 增强功能：防重复提交、本地缓存、自动重试（指数退避）
 *
 * 模块职责：
 *  - 创建全局唯一的 axios 实例，业务 API 模块统一从这里导入 get/post/put/patch/del/upload/download，
 *    组件与 store 不直接使用 axios，保证鉴权、错误提示、缓存策略只在一处生效。
 *  - 约定后端统一响应体为 ApiResponse：code=200 视为成功，拦截器返回的是响应体本身（含 code/message/data/timestamp）。
 *
 * 关键约定：
 *  - baseURL 来自构建环境变量 VITE_API_BASE_URL，未配置时回退为 '/'（由开发代理或同源网关承接）。
 *  - 超时 30 秒；GET/HEAD 幂等请求失败自动重试最多 2 次，POST 等写操作不重试，避免重复落库。
 *  - accessToken 存于 user store，由请求拦截器注入 Authorization: Bearer <token>。
 *  - 401 统一走 refresh token 续期流程，续期期间其余请求排队，成功后携带新 token 重放。
 */
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import router from '@/router'
import { requestCache, CACHE_WHITELIST_REGEX, CACHE_BLACKLIST_REGEX } from '@/utils/cache'

/**
 * 后端统一响应结构。
 * 所有接口（含业务异常）均返回该结构，HTTP 状态通常为 200，业务结果看 code。
 * - code：业务状态码，200 成功；401 登录过期；403 权限不足；其余为业务失败
 * - message：面向用户的提示文案，失败时由响应拦截器统一弹窗
 * - data：真正的业务数据，分页接口对应 PageResult
 * - timestamp：服务端生成时间，便于排查时序问题
 */
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
  timestamp: string
}

/**
 * 通用分页响应体（对应后端 PageResult）。
 * - total：符合条件的总记录数
 * - items：当前页数据列表
 * - page：当前页码（从 1 开始）
 * - page_size：每页条数
 */
export interface PageResult<T = any> {
  total: number
  items: T[]
  page: number
  page_size: number
}

/**
 * 挂在 axios config 上的重试元信息（仅内部使用，下划线前缀避免与业务字段冲突）。
 * - _retryCount：已重试次数
 * - maxRetries：最大重试次数，幂等请求为 2，写操作为 0
 * - _startTime：首次发起时间戳，便于统计整条请求链耗时
 */
interface RetryConfig {
  _retryCount?: number
  maxRetries?: number
  _startTime?: number
}

// 接口根地址：优先读取 .env 中的 VITE_API_BASE_URL；未配置时用 '/'，交由 Vite 代理或同源网关转发
const baseURL = import.meta.env.VITE_API_BASE_URL || '/'

// 全局唯一 axios 实例：30 秒超时，默认 JSON 请求体；上传/下载会在调用处覆盖 Content-Type 或 responseType
const service: AxiosInstance = axios.create({
  baseURL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// token 刷新状态机：isRefreshing 为 true 时，新来的 401 请求进入 pendingRequests 队列，
// 待刷新成功后携带新 token 重放；刷新失败则统一 reject，避免页面 loading 永久卡死。
let isRefreshing = false
let pendingRequests: Array<{
  resolve: (value: any) => void
  reject: (reason?: any) => void
  config: AxiosRequestConfig
}> = []

// 防重复提交登记表：key 为请求指纹，value 为该指纹最近一次发起时间。
// 只对 POST/PUT/DELETE/PATCH 生效，窗口期 500ms，用于拦截用户双击导致的重复提交。
const pendingMap = new Map<string, number>()
const PENDING_WINDOW_MS = 500 // 仅拦截极短时间内的用户双击提交

/**
 * 生成请求指纹，用于判断短时间内的重复提交。
 * 只取前 5 个 params/data 字段参与拼接以控制 key 长度；JSON 解析失败时按空对象处理，保证不抛异常。
 * @param config axios 请求配置
 * @returns method:url:params:data 形式的字符串 key
 */
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

/**
 * 登记写请求并判断是否为短时间内的重复提交。
 * 幂等请求（GET/HEAD）直接放行、不登记，保证并发查询互不干扰。
 * @returns 命中重复时返回请求 key（调用方据此拦截），否则登记后返回 null
 */
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

/**
 * 请求结束（成功/失败/取消）后从登记表移除，释放 key，使同名请求后续可以再次提交。
 */
function removePendingRequest(config: AxiosRequestConfig): void {
  if (isIdempotentMethod(config.method)) return
  const key = getRequestKey(config)
  pendingMap.delete(key)
}

/**
 * 判断请求方法是否幂等（GET/HEAD）。
 * 幂等请求允许并发、允许自动重试；非幂等写操作不重试，防止重复产生业务数据。
 */
function isIdempotentMethod(method?: string): boolean {
  const m = (method || 'GET').toUpperCase()
  return m === 'GET' || m === 'HEAD'
}

/**
 * 判断错误是否值得重试：服务端 5xx 或网络层错误（断网、超时、连接被中断）。
 * 4xx（尤其是 400/401/403/409）属于业务或鉴权错误，重试无意义。
 */
function isRetriableError(error: any): boolean {
  if (error.response) {
    const status = error.response.status
    return status >= 500 && status <= 599
  }
  const code = error.code || ''
  return code === 'ERR_NETWORK' || code === 'ETIMEDOUT' || code === 'ECONNABORTED'
}

/**
 * 指数退避计算重试等待时间：1s、2s、4s…，额外叠加 0~500ms 随机抖动，避免多请求同时重试造成雪崩。
 */
function calcRetryDelay(retryCount: number): number {
  return 1000 * Math.pow(2, retryCount) + Math.floor(Math.random() * 500)
}

// 请求拦截器，按顺序处理：1) 注入 token 2) 拦截重复提交 3) GET 命中本地缓存则短路返回
// 4) 写请求使缓存失效 5) 初始化重试元信息
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 从 pinia 用户 store 读取 accessToken，统一注入 Bearer 头；未登录时由后端返回 401
    const userStore = useUserStore()
    if (userStore.accessToken) {
      config.headers.Authorization = `Bearer ${userStore.accessToken}`
    }

    // 防重复提交：命中 500ms 窗口内的相同写请求时直接 reject，不再发往网络
    const duplicateKey = addPendingRequest(config)
    if (duplicateKey) {
      removePendingRequest(config)
      return Promise.reject(new Error('重复请求被拦截'))
    }

    const method = (config.method || 'GET').toUpperCase()
    // 先剥离 query string，只用 path 部分匹配黑白名单，避免 ?page=... 影响正则判定
    const rawUrl = config.url || ''
    const url = rawUrl.split('?')[0]

    // GET 查询缓存：仅当路径命中白名单且不在黑名单内时才读内存缓存；
    // 命中则构造伪响应短路返回，调用方无需感知，结构与真实响应一致（message 标记为 from cache）
    if (method === 'GET' && !CACHE_BLACKLIST_REGEX.test(url) && CACHE_WHITELIST_REGEX.test(url)) {
      const cacheKey = requestCache.genKey(rawUrl.split('?')[0], config.params, method)
      const cached = requestCache.get<ApiResponse>(cacheKey)
      if (cached) {
        // 命中缓存：构造伪响应直接短路，不再走网络；message 标记为 from cache 便于排查
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

    // 写操作一旦发出即清空全部 GET 缓存，保证提交后列表/详情能读到最新数据（简单但一致）
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
      requestCache.clear()
    }

    // 首次发起时初始化重试元信息；后续重试复用同一 config，计数得以累加
    const retryCfg = config as RetryConfig
    if (retryCfg._retryCount === undefined) {
      retryCfg._retryCount = 0
      retryCfg.maxRetries = isIdempotentMethod(config.method) ? 2 : 0
      retryCfg._startTime = Date.now()
    }

    return config
  },
  // 请求阶段异常（如请求体序列化失败）：同样清理登记表，防止 key 长期占用
  (error) => {
    if (error.config) removePendingRequest(error.config)
    return Promise.reject(error)
  }
)

// 响应拦截器：统一拆包、缓存与错误提示。
// 注意：成功分支返回的是 ApiResponse 响应体本身（而非 axios 的 response），业务层拿到的即后端 JSON
service.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    removePendingRequest(response.config)

    // 文件流（下载/导出）不做 JSON 拆包，原样返回 response，由 download/previewFileById 自行处理 Blob
    if (response.config.responseType === 'blob') {
      return response as any
    }

    const res = response.data
    const config = response.config as AxiosRequestConfig
    const method = (config.method || 'GET').toUpperCase()
    // 同 request 拦截器：剥离 query 再匹配
    const rawUrl = config.url || ''
    const url = rawUrl.split('?')[0]

    // 业务成功：GET 且命中白名单时写入本地缓存；随后把整个响应体交给调用方
    if (res.code === 200) {
      if (method === 'GET' && !CACHE_BLACKLIST_REGEX.test(url) && CACHE_WHITELIST_REGEX.test(url)) {
        const cacheKey = requestCache.genKey(rawUrl.split('?')[0], config.params, method)
        requestCache.set(cacheKey, { data: res.data })
      }
      return res
    }

    // 业务码 401：accessToken 过期，交给 handleTokenExpired 尝试静默续期并重放原请求
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

    // 403：已登录但角色/权限不足，不触发续期，直接提示并 reject
    if (res.code === 403) {
      ElMessage.error('权限不足，无法执行此操作')
      return Promise.reject(new Error(res.message))
    }

    // 其余业务码：统一 toast 后端 message，调用方只需处理 reject
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

    // 幂等请求 + 可重试错误 + 未超过次数上限：指数退避后重新发起同一请求
    const config = error.config as (AxiosRequestConfig & RetryConfig) | undefined
    if (
      config &&
      isIdempotentMethod(config.method) &&
      isRetriableError(error) &&
      (config._retryCount || 0) < (config.maxRetries || 0)
    ) {
      config._retryCount = (config._retryCount || 0) + 1
      const delay = calcRetryDelay(config._retryCount)
      // 等待退避时间后重放；_retryCount 已自增，下一次失败会继续拉长间隔
      await new Promise((resolve) => setTimeout(resolve, delay))
      return service(config)
    }

    // 兜底提示：优先展示后端错误信息，其次 axios 原生 message，最后统一为“网络异常”
    const msgFinal = error.response?.data?.message || error.message || '网络异常'
    ElMessage.error(msgFinal)
    return Promise.reject(error)
  }
)

/**
 * 处理 accessToken 过期：用 refreshToken 续期后重放原请求。
 *
 * 边界与副作用：
 * - 无 refreshToken：清空登录态并跳转登录页。
 * - 已有刷新在进行：当前请求挂起排队，避免并发刷新导致 refresh token 被一次性消费。
 * - 刷新成功：为排队请求统一替换 Authorization 头后重放。
 * - 刷新失败：显式 reject 所有排队请求（否则其 Promise 永不 settle），清登录态并提示。
 * @param config 触发 401 的原始请求配置
 * @returns 原请求（或排队后重放请求）的响应 Promise
 */
async function handleTokenExpired(config: AxiosRequestConfig): Promise<any> {
  const userStore = useUserStore()

  if (!userStore.refreshToken) {
    userStore.clearAuth()
    // 延迟跳转，避免在导航守卫中调用 router.push 导致路由状态混乱
    setTimeout(() => router.push('/login'), 0)
    return Promise.reject(new Error('未登录'))
  }

  if (isRefreshing) {
    // 刷新进行中：将当前请求排队，等刷新结束后统一重放（成功）或统一拒绝（失败）
    return new Promise((resolve, reject) => {
      pendingRequests.push({ resolve, reject, config })
    })
  }

  isRefreshing = true
  try {
    // 刷新成功：先回填原请求的鉴权头，再统一重放排队请求
    await userStore.doRefreshToken()
    if (config.headers) {
      config.headers.Authorization = `Bearer ${userStore.accessToken}`
    }
    // 逐条替换 token 后重放；重放结果直接作为各自排队 Promise 的结果
    pendingRequests.forEach(({ resolve, config: cfg }) => {
      if (cfg.headers) cfg.headers.Authorization = `Bearer ${userStore.accessToken}`
      resolve(service(cfg))
    })
    pendingRequests = []
    return service(config)
  } catch (refreshError) {
    // 刷新失败：必须显式拒绝所有排队请求，否则它们的 Promise 永不 settle，页面 loading 会卡死
    pendingRequests.forEach(({ reject }) => reject(refreshError))
    pendingRequests = []
    userStore.clearAuth()
    // 延迟跳转，避免在导航守卫中调用 router.push 导致路由状态混乱
    setTimeout(() => router.push('/login'), 0)
    ElMessage.error('登录已过期，请重新登录')
    return Promise.reject(refreshError)
  } finally {
    isRefreshing = false
  }
}

/**
 * 过滤查询参数中的 undefined/null/空字符串，避免拼出 ?a=&b= 这类无效 query。
 * 清洗后为空对象时返回 undefined，让 axios 不再追加问号。
 */
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

/**
 * GET 查询。params 会先经 cleanParams 清洗；config 可覆盖超时、headers 等。
 * @returns 后端 ApiResponse<T>，业务数据在 .data
 */
export function get<T = any>(url: string, params?: Record<string, any>, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'get', url, params: cleanParams(params), ...config })
}

/**
 * POST 创建/提交。属写操作：会清空 GET 缓存，并在 500ms 内拦截重复提交。
 */
export function post<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'post', url, data, ...config })
}

/**
 * PUT 全量更新。属写操作，不自动重试，避免重复覆盖业务数据。
 */
export function put<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'put', url, data, ...config })
}

/**
 * PATCH 局部更新。属写操作，不自动重试。
 */
export function patch<T = any>(url: string, data?: object, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'patch', url, data, ...config })
}

/**
 * DELETE 删除。params 走 query 传参，同样会清空 GET 缓存。
 */
export function del<T = any>(url: string, params?: Record<string, any>, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  return service({ method: 'delete', url, params: cleanParams(params), ...config })
}

/**
 * 文件上传：单文件字段名为 file，多文件字段名为 files（与后端接口约定一致）。
 * 使用 multipart/form-data，boundary 由浏览器自动补齐，调用方不要手动指定该请求头。
 * @param file 单个 File 或 File 数组
 * @returns 上传结果，通常包含附件 id / 文件 URL，供后续预览与关联业务使用
 */
export function upload<T = any>(url: string, file: File | File[], config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
  const formData = new FormData()
  if (Array.isArray(file)) {
    // 多文件：后端按 files 数组接收
    file.forEach((f) => formData.append('files', f))
  } else {
    // 单文件：字段名固定为 file
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

/**
 * 以 Blob 方式下载文件并触发浏览器保存。
 * @param url 下载接口地址
 * @param params 查询参数（如文件 id）
 * @param filename 保存文件名，缺省为 download
 * 依赖 responseType='blob'；响应拦截器对 blob 会跳过 JSON 拆包，这里直接读 res.data。
 * 注意：创建的 objectURL 在触发点击后立即释放，下载行为由浏览器接管。
 */
export async function download(url: string, params?: Record<string, any>, filename?: string): Promise<void> {
  const res = await service({ method: 'get', url, params: cleanParams(params), responseType: 'blob' })
  const blob = new Blob([res.data])
  // 借助临时 <a> 触发浏览器下载，不打开新窗口
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename || 'download'
  link.click()
  URL.revokeObjectURL(link.href)
}

// 默认导出原始 axios 实例，供需要自定义拦截器、AbortController 取消令牌等高级场景使用
export default service
