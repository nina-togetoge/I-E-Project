/**
 * 文件预览 / 下载组合式函数
 * 统一处理：文件下载、新窗口预览、图片/PDF 可预览文件判断
 * 替代各 Vue 文件中重复的 window.open / URL.createObjectURL 片段
 */
import { get } from '@/utils/request'

/** 可直接在浏览器中打开预览的扩展名 */
const PREVIEWABLE_EXT = new Set([
  '.pdf',
  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg',
  '.txt', '.md', '.csv', '.json',
  '.mp4', '.webm', '.mp3', '.wav',
])

export function useFilePreview() {
  /**
   * 根据扩展名判断是否可以直接在浏览器中预览
   */
  function isPreviewable(filename: string): boolean {
    const ext = '.' + (filename.split('.').pop() ?? '').toLowerCase()
    return PREVIEWABLE_EXT.has(ext)
  }

  /**
   * 预览 / 下载文件：
   * - 可预览类型：新窗口打开预览
   * - 不可预览类型：触发浏览器下载
   * @param url 文件 URL（后端文件服务或 download_url）
   * @param filename 文件名，用于决定预览方式与下载命名
   */
  function previewFile(url: string, filename = ''): void {
    if (!url) return
    if (filename && isPreviewable(filename)) {
      window.open(url, '_blank', 'noopener,noreferrer')
    } else {
      const link = document.createElement('a')
      link.href = url
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      if (filename) link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }

  /**
   * 通过文件 ID 从后端下载并预览（Blob 方式）
   * 适用于受鉴权保护的文件接口
   */
  async function previewFileById(fileId: number, filename?: string): Promise<void> {
    const res = await get<Blob>(`/api/files/download/${fileId}`, {}, { responseType: 'blob' })
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data as any])
    const objectUrl = URL.createObjectURL(blob)
    try {
      previewFile(objectUrl, filename ?? `file-${fileId}`)
    } finally {
      // 延迟释放，避免某些浏览器在预览前就 revoke
      setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
    }
  }

  return {
    isPreviewable,
    previewFile,
    previewFileById,
  }
}
