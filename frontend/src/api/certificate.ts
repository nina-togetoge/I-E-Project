/**
 * 获奖证书接口
 *
 * 对应后端 /api/certificates，目前仅提供学生端「我的证书」查询。
 * 证书由校级比赛获奖后自动生成：每个获奖项目一张团队证书（项目成员均可见），
 * 每位成员再各生成一张个人证书。证书文件为 PDF，通过附件 ID 下载。
 * 调用方：views/certificate/MyCertificates.vue。
 * 约定：列表返回 PageResult，page 从 1 开始；未传分页时后端使用默认值。
 */
import { get } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/**
 * 我的证书列表项：团队证书与个人证书统一结构，
 * 后端按当前用户身份过滤可见范围（团队成员可见团队证书）。
 */
export interface CertificateItem {
  /** 证书主键 */
  id: number
  /** 证书编号，对外唯一，撤销后也不复用 */
  cert_no: string
  /** 证书类型：1 团队 / 2 个人 */
  cert_type: number
  /** 持证人姓名（团队证书为项目负责人或团队名） */
  holder_name: string
  /** 关联比赛名称 */
  competition_name: string
  /** 获奖项目名称 */
  project_name: string
  /** 获奖等级文案（一等奖/二等奖等） */
  award_level: string
  /** 颁奖单位，可能为空 */
  organizer: string | null
  /** 证书签发日期 */
  issue_date: string
  /** 证书 PDF 的附件 ID，用于下载/预览 */
  attachment_id: number
  /** 证书文件名 */
  file_name: string
  /** 累计下载次数 */
  download_count: number
  /** 当前用户是否已下载过（用于展示「已下载」标记） */
  downloaded: boolean
}

/**
 * 查询我的证书（分页）GET /api/certificates/my
 * @param params 可选分页参数，不传时后端按默认页返回
 * @returns PageResult<CertificateItem>，含证书编号、获奖信息与附件
 * 调用方：MyCertificates.vue 表格；仅学生角色可见该页面。
 */
export function getMyCertificates(params: { page?: number; page_size?: number } = {}) {
  return get<PageResult<CertificateItem>>('/api/certificates/my', params)
}
