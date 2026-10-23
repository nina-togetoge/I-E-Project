/**
 * 获奖证书接口
 */
import { get } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 我的证书列表项 */
export interface CertificateItem {
  id: number
  cert_no: string
  cert_type: number
  holder_name: string
  competition_name: string
  project_name: string
  award_level: string
  organizer: string | null
  issue_date: string
  attachment_id: number
  file_name: string
  download_count: number
  downloaded: boolean
}

/** 我的证书（分页） */
export function getMyCertificates(params: { page?: number; page_size?: number } = {}) {
  return get<PageResult<CertificateItem>>('/api/certificates/my', params)
}
