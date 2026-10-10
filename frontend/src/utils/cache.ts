interface CacheEntry<T = any> {
  value: T
  expireAt: number
}

export class RequestCache {
  private data: Map<string, CacheEntry> = new Map()
  private maxSize: number
  private ttl: number

  constructor(maxSize = 50, ttl = 60000) {
    this.maxSize = maxSize
    this.ttl = ttl
  }

  get<T = any>(key: string): T | undefined {
    const entry = this.data.get(key)
    if (!entry) return undefined
    if (Date.now() > entry.expireAt) {
      this.data.delete(key)
      return undefined
    }
    return entry.value as T
  }

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

  has(key: string): boolean {
    return this.get(key) !== undefined
  }

  delete(key: string): boolean {
    return this.data.delete(key)
  }

  clear(): void {
    this.data.clear()
  }

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

  size(): number {
    return this.data.size
  }
}

export const requestCache = new RequestCache(50, 60000)

export const CACHE_WHITELIST_REGEX =
  /^\/api\/(projects?|users?|reviews?|expenses?|common|colleges?|admin)(?:\/(list|get|detail|search|statistics|colleges|records|trend|info|count|summary|options|overview|dict))?(?=$|\?)/

export const CACHE_BLACKLIST_REGEX =
  /\/api\/(auth|login|logout|import|export|excel|upload|download|submit|approve|reject|delete|create|update|patch|assign)/
