/**
 * 公共接口：文件上传下载、日志、搜索等
 */
import { get, post } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 上传文件 */
export function uploadFiles(files: File[], directory?: string) {
  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))
  if (directory) formData.append('directory', directory)
  return post('/api/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 文件下载 */
export function downloadFile(fileId: number, filename?: string) {
  return get(`/api/files/${fileId}/download`, {}, { responseType: 'blob' })
}

/** 操作日志 */
export function getOperationLogs(params: {
  page: number
  page_size: number
  keyword?: string
  module_name?: string
  operation_type?: string
  start_time?: string
  end_time?: string
}) {
  return get<PageResult>('/api/logs', params)
}

/** 全文检索 */
export function fullTextSearch(params: {
  keyword: string
  page?: number
  page_size?: number
}) {
  return get('/api/search', params)
}

/** 重建索引 */
export function rebuildSearchIndex() {
  return post('/api/search/rebuild-index')
}

/** 健康检查 */
export function healthCheck() {
  return get('/api/health')
}
