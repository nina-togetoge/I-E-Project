/**
 * 防抖 / 节流工具
 *
 * 模块职责：
 *  - useDebounce：连续触发时只在停止触发 delay 毫秒后执行一次，典型用途是搜索框输入联想、
 *    表单字段远程校验，避免每敲一个字就发一次请求。
 *  - useThrottle：固定时间窗口内最多执行一次，典型用途是滚动监听、窗口 resize、按钮防连点。
 *
 * 关键约定：
 *  - 返回的函数保留原函数的 this 与参数，可直接作为事件处理器使用；
 *  - 额外提供 cancel() 用于组件卸载时清理定时器；防抖还提供 flush() 立即执行最后一次待执行调用。
 *  - 本模块不依赖 Vue，不自动随组件销毁，调用方需在 onBeforeUnmount 中手动 cancel。
 */

/** 任意函数类型，仅用于泛型约束 */
type AnyFn = (...args: any[]) => any

/** 防抖函数的返回值形态：可直接调用，并附带取消与立即执行能力 */
interface DebounceReturn<T extends AnyFn> {
  (...args: Parameters<T>): void
  /** 取消尚未执行的调用并清空暂存参数 */
  cancel: () => void
  /** 立即执行尚未执行的那次调用（若有） */
  flush: () => void
}

/** 节流函数的返回值形态：可直接调用，并附带取消能力 */
interface ThrottleReturn<T extends AnyFn> {
  (...args: Parameters<T>): void
  /** 取消尚未执行的尾部调用 */
  cancel: () => void
}

/**
 * 创建防抖函数。
 * @param fn 需要防抖的原函数
 * @param delay 等待时间（毫秒），默认 300
 * @returns 防抖包装函数，带 cancel / flush
 * 行为：每次调用都会重置计时器，只以最后一次调用的参数与 this 执行。
 */
export function useDebounce<T extends AnyFn>(fn: T, delay = 300): DebounceReturn<T> {
  let timer: ReturnType<typeof setTimeout> | null = null
  // 暂存最后一次调用的参数与 this，保证延迟结束后执行的是最新一次调用
  let lastArgs: Parameters<T> | null = null
  let lastThis: any = null

  const debounced = function (this: any, ...args: Parameters<T>) {
    // 记录本次调用的参数与 this，后续只有最后一次调用会被真正执行
    lastArgs = args
    lastThis = this
    // 取消上一次未执行的定时器，重新开始计时（这是防抖的核心）
    if (timer) {
      clearTimeout(timer)
    }
    timer = setTimeout(() => {
      // 延迟结束：用最后一次参数执行
      if (lastArgs) {
        fn.apply(lastThis, lastArgs)
      }
      // 执行完毕复位状态，避免 cancel/flush 误触发已完成的调用
      timer = null
      lastArgs = null
      lastThis = null
    }, delay)
  } as DebounceReturn<T>

  // 取消等待中的执行，并丢弃暂存参数；组件卸载时调用可防止回调操作已销毁的组件
  debounced.cancel = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
      lastArgs = null
      lastThis = null
    }
  }

  // 立即兑现等待中的那次调用，例如搜索框按下回车时无需再等防抖延迟
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

/**
 * 创建节流函数。
 * @param fn 需要节流的原函数
 * @param delay 时间窗口（毫秒），默认 300
 * @returns 节流包装函数，带 cancel
 * 行为：窗口内首次调用立即执行；窗口内的后续调用只保留最后一次，在窗口结束时补执行（尾部节流）。
 */
export function useThrottle<T extends AnyFn>(fn: T, delay = 300): ThrottleReturn<T> {
  let lastTime = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastArgs: Parameters<T> | null = null
  let lastThis: any = null

  const throttled = function (this: any, ...args: Parameters<T>) {
    const now = Date.now()
    // 距下一次允许执行还剩多少毫秒，小于等于 0 表示可以立即执行
    const remaining = delay - (now - lastTime)
    lastArgs = args
    lastThis = this

    // 距上次执行已超过窗口：清除尾部定时器，立即执行本次调用
    if (remaining <= 0) {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      lastTime = now
      fn.apply(lastThis, lastArgs)
    // 窗口内：只保留一个尾部定时器，确保最后一次调用不会丢失
    } else if (!timer) {
      timer = setTimeout(() => {
        // 窗口结束：补执行窗口内最后一次调用，并重置窗口起点
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

  // 取消尚未执行的尾部调用，并刷新上次执行时间戳的语义（下次调用将立即执行）
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
