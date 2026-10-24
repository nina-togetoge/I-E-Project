/**
 * 请求级内存缓存（近似 LRU + TTL）
 *
 * 模块职责：
 *  - 为 GET 查询提供短时缓存，减少重复拉取列表/字典/统计等低频变化数据。
 *  - 仅由 utils/request.ts 的拦截器读写，业务代码不直接使用；写操作（新增/修改/删除）会整体清空缓存。
 *
 * 关键约定：
 *  - 缓存存放于内存 Map，页面刷新即失效，不落 localStorage，避免脏数据跨会话残留。
 *  - 每个条目带过期时间 expireAt，读取时惰性判断并删除过期项。
 *  - 容量达到 maxSize 时淘汰最早插入的 key（Map 迭代顺序即插入顺序），非严格 LRU。
 */

/** 单条缓存记录 */
interface CacheEntry<T = any> {
  /** 缓存的实际值（本项目存的是后端响应中的 data 片段） */
  value: T
  /** 过期时间戳（毫秒），读取时与此值比较 */
  expireAt: number
}

/**
 * 内存请求缓存实现。
 * 会被 request.ts 以单例 requestCache 使用，也可在测试中独立实例化。
 */
export class RequestCache {
  private data: Map<string, CacheEntry> = new Map()
  private maxSize: number
  private ttl: number

  /**
   * @param maxSize 最多缓存的 key 数量，默认 50
   * @param ttl 条目存活时间（毫秒），默认 60 秒
   */
  constructor(maxSize = 50, ttl = 60000) {
    this.maxSize = maxSize
    this.ttl = ttl
  }

  /**
   * 读取缓存；命中过期条目时顺手删除并返回 undefined。
   * @returns 缓存值，未命中或已过期返回 undefined
   */
  get<T = any>(key: string): T | undefined {
    const entry = this.data.get(key)
    if (!entry) return undefined
    if (Date.now() > entry.expireAt) {
      this.data.delete(key)
      return undefined
    }
    return entry.value as T
  }

  /**
   * 写入缓存并重置该条目的过期时间；容量已满时先淘汰最早插入的 key。
   */
  set<T = any>(key: string, value: T): void {
    if (this.data.size >= this.maxSize) {
      const firstKey = this.data.keys().next().value
      if (firstKey !== undefined) {
        this.data.delete(firstKey)
      }
    }
    this.data.set(key, {
      value,
      expireAt: Date.now() + this.ttl,
    })
  }

  /** 判断 key 是否存在且未过期（复用 get 的惰性清理逻辑） */
  has(key: string): boolean {
    return this.get(key) !== undefined
  }

  /** 删除指定 key，返回是否真的删除了条目 */
  delete(key: string): boolean {
    return this.data.delete(key)
  }

  /** 清空全部缓存，写操作发生后由请求拦截器调用 */
  clear(): void {
    this.data.clear()
  }

  /**
   * 生成缓存 key：method:url:params。
   * params 会先按 key 排序再序列化，保证 {a:1,b:2} 与 {b:2,a:1} 命中同一条缓存。
   * @param url 已剥离 query string 的接口路径
   * @param params 查询参数
   * @param method 请求方法，默认 GET
   */
  genKey(url: string, params?: Record<string, any>, method = 'GET'): string {
    const sortedParams = params
      ? Object.keys(params)
          .sort()
          .reduce((acc: Record<string, any>, k) => {
            acc[k] = params[k]
            return acc
          }, {})
      : {}
    return `${method.toUpperCase()}:${url}:${JSON.stringify(sortedParams)}`
  }

  /** 当前缓存条目数量（含尚未惰性清理的过期条目） */
  size(): number {
    return this.data.size
  }
}

/** 全局缓存单例：最多 50 条，单条存活 60 秒，由 request.ts 统一读写 */
export const requestCache = new RequestCache(50, 60000)

/**
 * 缓存白名单：只有路径形态匹配的 GET 接口才允许写入/读取缓存。
 * 覆盖项目、用户、评审、经费、公共字典、学院、后台管理等只读查询的子路径；
 * 末尾 (?=$|\?) 确保匹配到路径边界，避免 /projects/xxx 之类的详情路径被误判。
 */
export const CACHE_WHITELIST_REGEX =
  /^\/api\/(projects?|users?|reviews?|expenses?|common|colleges?|admin)(?:\/(list|get|detail|search|statistics|colleges|records|trend|info|count|summary|options|overview|dict))?(?=$|\?)/

/**
 * 缓存黑名单：鉴权、导入导出、上传下载及所有写动作路径一律不缓存。
 * 即使误落入白名单前缀（如 admin 导出），也会因命中黑名单而被排除。
 */
export const CACHE_BLACKLIST_REGEX =
  /\/api\/(auth|login|logout|import|export|excel|upload|download|submit|approve|reject|delete|create|update|patch|assign)/
