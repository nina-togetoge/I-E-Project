/**
 * 文件预览 / 下载组合式函数
 * 统一处理：文件下载、新窗口预览、图片/PDF 可预览文件判断
 * 替代各 Vue 文件中重复的 window.open / URL.createObjectURL 片段
 *
 * 模块职责：
 *  - 项目附件、结题材料、评审附件的实体文件存放在后端，前端只拿到 URL 或附件 id；
 *    本模块根据文件类型决定“浏览器内预览”还是“下载兜底”。
 *
 * 预览策略：
 *  - 图片 / PDF / 纯文本 / 音视频：浏览器可原生渲染，新窗口打开 URL 直接预览；
 *  - Office 文档（doc/docx/xls/xlsx/ppt/pptx）及其他浏览器无法内联渲染的类型：
 *    不做在线转换，统一走下载，由用户本地应用打开（降级兜底）；
 *  - 通过附件 id 访问时，先带鉴权请求取回 Blob，再生成 objectURL 预览，最后延迟释放。
 *
 * 关键约定：
 *  - 预览 URL 必须由后端提供或经鉴权接口获取，前端不拼接实体存储路径；
 *  - 新窗口打开统一带 noopener/noreferrer，避免被预览页反向控制原页面。
 */
import { get } from '@/utils/request'

/**
 * 浏览器可直接内联预览的扩展名集合。
 * 不含 doc/docx/xls/xlsx/ppt/pptx：这些类型浏览器无法原生渲染，需要走下载兜底。
 */
const PREVIEWABLE_EXT = new Set([
  '.pdf',
  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg',
  '.txt', '.md', '.csv', '.json',
  '.mp4', '.webm', '.mp3', '.wav',
])

/**
 * 创建文件预览工具集。
 * 返回的方法均为无状态工具函数，可在任意组件中按需调用。
 */
export function useFilePreview() {
  /**
   * 根据扩展名判断是否可以直接在浏览器中预览。
   * @param filename 文件名（需包含扩展名）
   * @returns 属于图片/PDF/文本/音视频等可内联渲染类型时返回 true
   * 边界：无扩展名、仅有点号、大小写混写均安全处理；扩展名比较已转小写。
   */
  function isPreviewable(filename: string): boolean {
    const ext = '.' + (filename.split('.').pop() ?? '').toLowerCase()
    return PREVIEWABLE_EXT.has(ext)
  }

  /**
   * 预览 / 下载文件：
   * - 可预览类型：新窗口打开预览；
   * - 不可预览类型（含 Office 文档）：创建临时 <a download> 触发浏览器下载，作为降级兜底。
   * @param url 文件 URL（后端文件服务地址或接口返回的 download_url）
   * @param filename 文件名，用于决定预览方式与下载命名；为空时一律按下载处理
   * 注意：跨域 URL 的 download 属性可能被浏览器忽略，此时表现为新窗口打开。
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
   * 通过附件 ID 从后端取回文件并预览（Blob 方式）。
   * 适用于需要鉴权、不能直接暴露公网 URL 的附件接口。
   * @param fileId 附件 id
   * @param filename 文件名；缺省时用 file-<id>，此时无法判断类型，会走下载兜底
   * 异常：请求失败由 request.ts 统一提示并 reject，调用方可按需 catch。
   * 副作用：生成 objectURL 并在 60 秒后释放，给浏览器留出足够的预览/下载时间。
   */
  async function previewFileById(fileId: number, filename?: string): Promise<void> {
    const res = await get<Blob>(`/api/files/download/${fileId}`, {}, { responseType: 'blob' })
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data as any])
    const objectUrl = URL.createObjectURL(blob)
    try {
      previewFile(objectUrl, filename ?? `file-${fileId}`)
    } finally {
      // 延迟释放，避免某些浏览器在预览/下载真正开始前就被 revoke
      setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
    }
  }

  return {
    /** 判断文件名是否可被浏览器内联预览 */
    isPreviewable,
    /** 按文件名选择新窗口预览或下载兜底 */
    previewFile,
    /** 通过附件 id 鉴权拉取 Blob 后预览 */
    previewFileById,
  }
}
