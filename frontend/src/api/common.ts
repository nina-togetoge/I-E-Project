/**
 * 公共接口：文件上传下载、日志、搜索等
 */
import { get, post } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 上传文件（与后端对齐：biz_type 业务类型 + biz_id 业务ID + 单个 file） */
export function uploadFiles(file: File, bizType: string, bizId: number) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('biz_type', bizType)
  formData.append('biz_id', String(bizId))
  return post('/api/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 文件下载 */
export function downloadFile(fileId: number, filename?: string) {
  return get(`/api/files/download/${fileId}`, {}, { responseType: 'blob' })
}

/** 查询业务下的附件列表 */
export function listAttachments(bizType: string, bizId: number) {
  return get<Array<{
    id: number
    file_name: string
    file_size: number
    file_type: string
    uploader_name: string
    download_count: number
    created_at: string
    download_url: string
  }>>(`/api/files/list/${bizType}/${bizId}`)
}

/** 下载项目导入模板 */
export function downloadProjectTemplate() {
  return get('/api/excel/template/project', {}, { responseType: 'blob' })
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
  return get('/api/search/projects', params)
}

/** 重建索引 */
export function rebuildSearchIndex() {
  return post('/api/search/rebuild-index')
}

/** 健康检查 */
export function healthCheck() {
  return get('/health')
}
