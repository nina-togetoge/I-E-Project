/**
 * 系统公告接口
 */
import { get, post, put, del, patch } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 公告列表项 */
export interface AnnouncementListItem {
  id: number
  title: string
  content: string
  announcement_type: number
  announcement_type_name: string
  status: number
  status_name: string
  priority: number
  priority_name: string
  publish_time: string | null
  expire_time: string | null
  view_count: number
  created_by: number | null
  creator_name: string | null
  created_at: string
}

/** 公告详情 */
export interface AnnouncementDetail extends AnnouncementListItem {
  content: string
}

/** 公告创建/更新参数 */
export interface AnnouncementForm {
  title: string
  content: string
  announcement_type: number
  status: number
  priority: number
  expire_time: string | null
}

/** 公告列表 */
export function getAnnouncementList(params: {
  page: number
  page_size: number
  keyword?: string
  announcement_type?: number
  status?: number
}) {
  return get<PageResult<AnnouncementListItem>>('/api/announcements', params)
}

/** 公告详情 */
export function getAnnouncementDetail(id: number) {
  return get<AnnouncementDetail>(`/api/announcements/${id}`)
}

/** 创建公告 */
export function createAnnouncement(data: AnnouncementForm) {
  return post<AnnouncementDetail>('/api/announcements', data)
}

/** 更新公告 */
export function updateAnnouncement(id: number, data: Partial<AnnouncementForm>) {
  return put<AnnouncementDetail>(`/api/announcements/${id}`, data)
}

/** 删除公告 */
export function deleteAnnouncement(id: number) {
  return del(`/api/announcements/${id}`)
}

/** 修改公告状态 */
export function updateAnnouncementStatus(id: number, status: number) {
  return patch<AnnouncementDetail>(`/api/announcements/${id}/status`, { status })
}
