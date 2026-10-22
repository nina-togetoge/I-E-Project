/**
 * 站内通知接口
 */
import { get, post } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/** 站内通知项 */
export interface NotificationItem {
  id: number
  user_id: number
  title: string
  content: string
  level: number // 1-普通 2-警告 3-成功
  biz_type: string | null
  biz_id: number | null
  link: string | null
  is_read: number
  read_time: string | null
  created_at: string
}

/** 通知列表 */
export function getNotificationList(params: {
  page: number
  page_size: number
  is_read?: number
}) {
  return get<PageResult<NotificationItem>>('/api/notifications', params)
}

/** 未读数量 */
export function getUnreadCount() {
  return get<{ count: number }>('/api/notifications/unread-count')
}

/** 标记单条已读 */
export function markNotificationRead(id: number) {
  return post(`/api/notifications/${id}/read`)
}

/** 全部标记已读 */
export function markAllNotificationsRead() {
  return post('/api/notifications/read-all')
}
