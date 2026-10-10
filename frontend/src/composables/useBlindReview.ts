export function useBlindReview(isBlind: boolean | (() => boolean)) {
  const getIsBlind = () => (typeof isBlind === 'function' ? isBlind() : isBlind)

  function maskName(name?: string | null): string {
    if (!getIsBlind()) return name || ''
    if (!name) return ''
    if (name.length <= 1) return name
    return name[0] + '*'.repeat(Math.max(name.length - 1, 2))
  }

  function maskCollege(college?: string | null): string {
    if (!getIsBlind()) return college || ''
    if (!college) return ''
    return '学院已屏蔽'
  }

  function maskIdNumber(id?: string | null): string {
    if (!getIsBlind()) return id || ''
    if (!id) return ''
    if (id.length <= 4) return '*'.repeat(id.length)
    return id.slice(0, 2) + '*'.repeat(Math.max(id.length - 4, 2)) + id.slice(-2)
  }

  function maskAvatar(avatar?: string | null): undefined {
    if (!getIsBlind()) return avatar as undefined
    return undefined
  }

  function maskSensitive<T extends Record<string, any>>(
    obj: T | null | undefined,
    fields: {
      names?: (keyof T)[]
      colleges?: (keyof T)[]
      ids?: (keyof T)[]
      avatars?: (keyof T)[]
    }
  ): T {
    if (!obj) return {} as T
    if (!getIsBlind()) return obj
    const result = { ...obj }
    fields.names?.forEach((f) => {
      if (result[f] != null) (result as any)[f] = maskName(String(result[f]))
    })
    fields.colleges?.forEach((f) => {
      if (result[f] != null) (result as any)[f] = maskCollege(String(result[f]))
    })
    fields.ids?.forEach((f) => {
      if (result[f] != null) (result as any)[f] = maskIdNumber(String(result[f]))
    })
    fields.avatars?.forEach((f) => {
      if (result[f] != null) (result as any)[f] = maskAvatar(String(result[f]))
    })
    return result
  }

  return {
    maskName,
    maskCollege,
    maskIdNumber,
    maskAvatar,
    maskSensitive,
  }
}
