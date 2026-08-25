/**
 * 通用格式化工具函数集
 * 集中消除各 Vue 文件中重复的 formatSize / formatFileSize 实现
 */

/**
 * 文件字节大小 → 可读字符串（B/KB/MB/GB/TB）
 * @param bytes 字节数
 * @param decimals 保留小数位，默认 2
 */
export function formatSize(bytes: number, decimals = 2): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const k = 1024
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const value = bytes / Math.pow(k, i)
  return `${value.toFixed(value % 1 === 0 ? 0 : decimals)} ${units[i]}`
}

/**
 * 文件字节大小 → 指定单位（通常用于上传前大小校验场景）
 */
export function bytesToMB(bytes: number): number {
  return bytes / 1024 / 1024
}

/**
 * 日期时间格式化（默认 YYYY-MM-DD HH:mm:ss）
 */
export function formatDateTime(
  value: string | Date | null | undefined,
  pattern = 'YYYY-MM-DD HH:mm:ss',
): string {
  if (!value) return ''
  const d = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => n.toString().padStart(2, '0')
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
