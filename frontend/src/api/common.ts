/**
 * 公共接口：附件上传下载、Excel 模板、操作日志与健康检查
 *
 * 附件统一走 /api/files，上传时需携带业务类型 biz_type 与业务 ID biz_id，
 * 业务表单只保存返回的附件 ID，再通过 attachment_ids 关联。
 * 主要调用方：
 *   - components/FileUpload.vue、RichEditor.vue（图片插入）；
 *   - views/project/ProjectCreate、MyProjects、MidtermCheck、FinalCheck（项目/中期/结题附件）；
 *   - components/AchievementPanel.vue（成果证明材料）；
 *   - views/admin/OperationLogs.vue（操作日志）。
 * 约定：上传/下载为 multipart 或 blob，响应拦截器对 blob 直接透传，不做 code 解包。
 */
import { get, post, del } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/**
 * 上传单个文件 POST /api/files/upload
 * @param file 浏览器 File 对象
 * @param bizType 业务类型：project/midterm/achievement/expense/editor 等
 * @param bizId 业务主键；新建尚未保存时传 0，由后端按临时附件处理
 * @returns 附件记录（id/file_name/file_size/download_url 等）
 * 调用方：FileUpload 组件、RichEditor 图片上传；失败由拦截器统一提示。
 */
export function uploadFiles(file: File, bizType: string, bizId: number) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('biz_type', bizType)
  formData.append('biz_id', String(bizId))
  return post('/api/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/**
 * 下载文件 GET /api/files/download/{fileId}
 * responseType=blob，返回的 res.data 为二进制，调用方需自行创建下载链接。
 * @param filename 仅作调用方命名参考，本函数不触发浏览器下载
 * 预留接口：当前页面多直接用附件的 download_url，暂未调用。
 */
export function downloadFile(fileId: number, filename?: string) {
  return get(`/api/files/download/${fileId}`, {}, { responseType: 'blob' })
}

/**
 * 查询某业务下的附件列表 GET /api/files/list/{bizType}/{bizId}
 * @param bizType 业务类型，需与上传时一致
 * @param bizId 业务主键
 * @returns 附件数组，含下载次数与直链
 * 预留接口：列表接口通常已内嵌 attachments，暂未额外调用。
 */
export function listAttachments(bizType: string, bizId: number) {
  return get<Array<{
    /** 附件主键 */
    id: number
    /** 原始文件名 */
    file_name: string
    /** 文件大小（字节） */
    file_size: number
    /** MIME 类型 */
    file_type: string
    /** 上传者姓名 */
    uploader_name: string
    /** 累计下载次数 */
    download_count: number
    /** 上传时间 */
    created_at: string
    /** 下载直链 */
    download_url: string
  }>>(`/api/files/list/${bizType}/${bizId}`)
}

/**
 * 删除附件 DELETE /api/files/{fileId}
 * 后端软删除，仅上传者或管理员可操作；业务提交前删除临时附件不会影响已保存数据。
 * 调用方：AchievementPanel、MyProjects、MidtermCheck 的附件删除按钮。
 */
export function deleteAttachment(fileId: number) {
  return del(`/api/files/${fileId}`)
}

/**
 * 下载项目导入模板 GET /api/excel/template/project
 * responseType=blob，返回 Excel 二进制；预留接口，页面暂未接入。
 */
export function downloadProjectTemplate() {
  return get('/api/excel/template/project', {}, { responseType: 'blob' })
}

/**
 * 操作日志列表 GET /api/logs（管理员）
 * 后端按当前登录人数据范围过滤；多选筛选项以英文逗号拼接后透传。
 * @param params 分页 + 关键字 + 模块/操作类型/时间区间 + 多选条件
 * 调用方：views/admin/OperationLogs.vue 表格。
 */
export function getOperationLogs(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 操作人/内容关键字 */
  keyword?: string
  /** 单模块筛选（与 modules 二选一，保留兼容） */
  module_name?: string
  /** 单操作类型筛选（与 operation_types 二选一） */
  operation_type?: string
  /** 起始时间，ISO 字符串 */
  start_time?: string
  /** 结束时间，ISO 字符串 */
  end_time?: string
  /** 多选模块，逗号分隔 */
  modules?: string
  /** 多选操作类型，逗号分隔 */
  operation_types?: string
  /** 多选角色，逗号分隔 */
  user_roles?: string
  /** 多选状态，逗号分隔 */
  statuses?: string
}) {
  return get<PageResult>('/api/logs', params)
}

/**
 * 健康检查 GET /health
 * 用于部署探活/前端启动自检，无需登录；预留接口，页面暂未调用。
 */
export function healthCheck() {
  return get('/health')
}
