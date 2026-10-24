/**
 * 数字滚动动画工具
 *
 * 模块职责：
 *  - 基于 requestAnimationFrame 把数值从 0 平滑过渡到目标值，用于统计卡片、评分看板等展示。
 *  - 不依赖任何框架，可被 Vue 组件在 onMounted 时调用，并把返回的取消函数存到 onBeforeUnmount。
 *
 * 关键约定：
 *  - 每帧通过 callback 回传当前值，由调用方决定如何格式化与渲染；
 *  - 组件卸载或重复触发前必须调用返回的取消函数，避免遗留 rAF 回调造成内存与性能问题。
 */

/**
 * 数字缓动动画。
 * @param target 目标数值
 * @param duration 动画时长（毫秒），默认 1500
 * @param callback 每帧回调，参数为当前进度对应的数值
 * @returns 取消函数；调用后停止动画且不再触发 callback
 * 边界：duration 为 0 时首帧即到达目标值；target 为负数同样按比例缓动。
 */
export function animateNumber(
  target: number,
  duration: number = 1500,
  callback: (v: number) => void,
): () => void {
  /** 缓动函数：easeOutCubic，先快后慢，接近目标时更平缓 */
  const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3)
  const start = performance.now()
  let rafId: number | null = null

  /**
   * 单帧推进：计算线性进度并映射为缓动后的数值，未完成则继续申请下一帧。
   * @param now requestAnimationFrame 传入的高精度时间戳
   */
  function step(now: number) {
    const elapsed = now - start
    const progress = Math.min(elapsed / duration, 1)
    const eased = easeOutCubic(progress)
    callback(target * eased)
    if (progress < 1) {
      rafId = requestAnimationFrame(step)
    }
  }

  // 启动动画；首帧时间戳由浏览器提供，与 performance.now() 同源
  rafId = requestAnimationFrame(step)

  // 返回取消句柄：幂等调用，已停止时再次调用不会报错
  return () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }
}
