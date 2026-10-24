/**
 * 通用格式化工具函数集
 * 集中消除各 Vue 文件中重复的 formatSize / formatFileSize 实现
 *
 * 模块职责：
 *  - 纯展示层格式化，不依赖 Vue / Element Plus，可在任意组件、store、工具模块中复用。
 *  - 被附件列表、项目详情、后台统计等页面用于展示文件大小与时间。
 *
 * 关键约定：
 *  - 所有函数对空值/非法值都返回安全字符串（'' 或 '0 B'），调用方无需重复判空。
 *  - 日期格式化按本地时区展示，不做 UTC 转换；后端返回的时间字符串应带时区或已被标准化。
 */

/**
 * 文件字节大小 → 可读字符串（B/KB/MB/GB/TB）
 * @param bytes 字节数
 * @param decimals 保留小数位，默认 2
 * @returns 如 "1.5 MB"；非有限数或非正数一律返回 "0 B"
 */
export function formatSize(bytes: number, decimals = 2): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const k = 1024
  // 单位阶梯按 1024 进制，索引由 log 计算得出，PB 为兜底最大单位
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const value = bytes / Math.pow(k, i)
  return `${value.toFixed(value % 1 === 0 ? 0 : decimals)} ${units[i]}`
}

/**
 * 文件字节大小 → MB 数值（不做单位换算展示，通常用于上传前阈值比较）。
 * @param bytes 字节数
 * @returns 以 MB 为单位的浮点数，调用方自行决定四舍五入与提示
 */
export function bytesToMB(bytes: number): number {
  return bytes / 1024 / 1024
}

/**
 * 日期时间格式化（默认 YYYY-MM-DD HH:mm:ss）。
 * @param value 日期对象、时间字符串，或 null/undefined
 * @param pattern 占位符模板，支持 YYYY/MM/DD/HH/mm/ss
 * @returns 格式化结果；空值或非法日期返回空字符串，避免页面出现 Invalid Date
 * 说明：模板替换使用正则一次性匹配占位符，因此 pattern 中除占位符外的文字会被原样保留。
 */
export function formatDateTime(
  value: string | Date | null | undefined,
  pattern = 'YYYY-MM-DD HH:mm:ss',
): string {
  if (!value) return ''
  // 字符串交给 Date 解析（建议后端返回 ISO 格式）；Date 对象直接使用
  const d = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(d.getTime())) return ''
  // 统一左补零，保证 1 月/9 点展示为 01/09
  const pad = (n: number) => n.toString().padStart(2, '0')
  // 占位符 → 实际值映射；月份需 +1，因为 getMonth 从 0 开始
  const map: Record<string, string> = {
    YYYY: d.getFullYear().toString(),
    MM: pad(d.getMonth() + 1),
    DD: pad(d.getDate()),
    HH: pad(d.getHours()),
    mm: pad(d.getMinutes()),
    ss: pad(d.getSeconds()),
  }
  return pattern.replace(/YYYY|MM|DD|HH|mm|ss/g, (k) => map[k])
}

/**
 * 日期格式化（YYYY-MM-DD），常用于列表页只展示年月日。
 */
export function formatDate(value: string | Date | null | undefined): string {
  return formatDateTime(value, 'YYYY-MM-DD')
}
