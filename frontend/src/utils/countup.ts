export function animateNumber(
  target: number,
  duration: number = 1500,
  callback: (v: number) => void,
): () => void {
  const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3)
  const start = performance.now()
  let rafId: number | null = null

  function step(now: number) {
    const elapsed = now - start
    const progress = Math.min(elapsed / duration, 1)
    const eased = easeOutCubic(progress)
    callback(target * eased)
    if (progress < 1) {
      rafId = requestAnimationFrame(step)
    }
  }

  rafId = requestAnimationFrame(step)

  return () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }
}
