type AnyFn = (...args: any[]) => any

interface DebounceReturn<T extends AnyFn> {
  (...args: Parameters<T>): void
  cancel: () => void
  flush: () => void
}

interface ThrottleReturn<T extends AnyFn> {
  (...args: Parameters<T>): void
  cancel: () => void
}

export function useDebounce<T extends AnyFn>(fn: T, delay = 300): DebounceReturn<T> {
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastArgs: Parameters<T> | null = null
  let lastThis: any = null

  const debounced = function (this: any, ...args: Parameters<T>) {
    lastArgs = args
    lastThis = this
    if (timer) {
      clearTimeout(timer)
    }
    timer = setTimeout(() => {
      if (lastArgs) {
        fn.apply(lastThis, lastArgs)
      }
      timer = null
      lastArgs = null
      lastThis = null
    }, delay)
  } as DebounceReturn<T>

  debounced.cancel = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
      lastArgs = null
      lastThis = null
    }
  }

  debounced.flush = () => {
    if (timer && lastArgs) {
      clearTimeout(timer)
      fn.apply(lastThis, lastArgs)
      timer = null
      lastArgs = null
      lastThis = null
    }
  }

  return debounced
}

export function useThrottle<T extends AnyFn>(fn: T, delay = 300): ThrottleReturn<T> {
  let lastTime = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastArgs: Parameters<T> | null = null
  let lastThis: any = null

  const throttled = function (this: any, ...args: Parameters<T>) {
    const now = Date.now()
    const remaining = delay - (now - lastTime)
    lastArgs = args
    lastThis = this

    if (remaining <= 0) {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      lastTime = now
      fn.apply(lastThis, lastArgs)
    } else if (!timer) {
      timer = setTimeout(() => {
        lastTime = Date.now()
        timer = null
        if (lastArgs) {
          fn.apply(lastThis, lastArgs)
        }
        lastArgs = null
        lastThis = null
      }, remaining)
    }
  } as ThrottleReturn<T>

  throttled.cancel = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
      lastArgs = null
      lastThis = null
    }
  }

  return throttled
}
