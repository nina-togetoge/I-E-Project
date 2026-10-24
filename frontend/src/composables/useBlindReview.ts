/**
 * 盲审脱敏组合式函数
 *
 * 模块职责：
 *  - 专家评审环节采用盲审：评审列表/详情页在渲染前，用这里的掩码方法隐藏申报人姓名、
 *    学院、学号/证件号与头像，避免专家根据身份信息产生倾向性评分。
 *  - 评审页同时会隐藏其他专家的互评信息（他人评分、评语），该部分由页面层控制；
 *    本模块只负责“身份字段”的展示脱敏。
 *
 * 关键约定：
 *  - isBlind 支持布尔值或 getter：传函数可让脱敏状态随路由/角色响应式变化，每次调用时实时读取。
 *  - 非盲审状态原样返回数据，调用方无需写两套模板。
 *  - 掩码只影响前端展示，不改变接口返回的原始数据，也不替代后端字段级权限控制。
 */

/**
 * 创建盲审脱敏工具集。
 * @param isBlind 是否处于盲审模式；传函数时每次脱敏前重新求值
 * @returns 姓名/学院/证件号/头像的掩码方法，以及按字段批量脱敏的 maskSensitive
 */
export function useBlindReview(isBlind: boolean | (() => boolean)) {
  // 统一读取当前盲审状态，兼容布尔值与 getter 两种入参
  const getIsBlind = () => (typeof isBlind === 'function' ? isBlind() : isBlind)

  /**
   * 姓名掩码：保留首字，其余用 * 代替，且至少补足 2 个星号。
   * 单字姓名无法保留首字又隐藏（保留即等于暴露），因此原样返回。
   */
  function maskName(name?: string | null): string {
    if (!getIsBlind()) return name || ''
    if (!name) return ''
    if (name.length <= 1) return name
    return name[0] + '*'.repeat(Math.max(name.length - 1, 2))
  }

  /**
   * 学院掩码：盲审时统一替换为固定文案，避免通过学院推断申报人身份。
   */
  function maskCollege(college?: string | null): string {
    if (!getIsBlind()) return college || ''
    if (!college) return ''
    return '学院已屏蔽'
  }

  /**
   * 学号/证件号掩码：保留前 2 位与后 2 位，中间用 * 覆盖（至少 2 个星号）；
   * 长度不超过 4 位时全部替换为 *，防止保留位已能唯一识别。
   */
  function maskIdNumber(id?: string | null): string {
    if (!getIsBlind()) return id || ''
    if (!id) return ''
    if (id.length <= 4) return '*'.repeat(id.length)
    return id.slice(0, 2) + '*'.repeat(Math.max(id.length - 4, 2)) + id.slice(-2)
  }

  /**
   * 头像处理：盲审时不返回地址，让模板回退到默认占位头像，避免照片泄露身份。
   * 非盲审时原样返回；返回类型标注为 undefined 是历史调用约定，实际值仍为字符串。
   */
  function maskAvatar(avatar?: string | null): undefined {
    if (!getIsBlind()) return avatar as undefined
    return undefined
  }

  /**
   * 按字段批量脱敏：对对象中的指定字段分别应用姓名/学院/证件号/头像掩码。
   * @param obj 原始业务对象，null/undefined 时返回空对象
   * @param fields 各掩码类型对应的字段名列表，未列出的字段保持不变
   * @returns 脱敏后的新对象（浅拷贝）；非盲审模式直接返回原对象引用
   * 注意：只处理顶层字段，嵌套结构需调用方自行展开。
   */
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
