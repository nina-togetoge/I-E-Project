/**
 * 站内通知接口
 *
 * 后端在审核结果、成果认定、项目状态流转等事件发生时写入通知表，
 * 前端由顶栏 NoticeBell 与 store/notice.ts 统一消费。
 * 已读状态由后端维护（is_read/read_time），与公告的本地 localStorage 已读区分。
 * 主要调用方：store/notice.ts（fetchNotices / markRead / markAllRead）。
 */
import { get, post } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/**
 * 站内业务通知项
 * 与公告不同，通知属于某个用户，可能带业务跳转链接。
 */
export interface NotificationItem {
  /** 通知主键 */
  id: number
  /** 接收用户 ID */
  user_id: number
  /** 通知标题 */
  title: string
  /** 通知正文，纯文本（公告才需要剥离 HTML） */
  content: string
  /** 级别：1-普通 2-警告 3-成功，决定前端颜色与优先级映射 */
  level: number // 1-普通 2-警告 3-成功
  /** 关联业务类型（project/achievement/expense 等），可为空 */
  biz_type: string | null
  /** 关联业务主键，与 biz_type 配合跳转 */
  biz_id: number | null
  /** 前端跳转路由，后端可直接下发 */
  link: string | null
  /** 是否已读：0 未读 / 1 已读 */
  is_read: number
  /** 已读时间，未读为空 */
  read_time: string | null
  /** 通知创建时间，用于列表倒序 */
  created_at: string
}

/**
 * 通知列表 GET /api/notifications
 * @param params 分页 + is_read 过滤（0未读/1已读，不传全部）
 * @returns PageResult<NotificationItem>
 * 调用方：notice store 拉取顶栏通知，固定 page_size=50。
 */
export function getNotificationList(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 已读筛选：0 未读 / 1 已读，不传返回全部 */
  is_read?: number
}) {
  return get<PageResult<NotificationItem>>('/api/notifications', params)
}

/**
 * 未读数量 GET /api/notifications/unread-count
 * @returns { count } 当前用户未读通知总数
 * 预留接口：顶栏角标目前由 store 根据已拉取列表本地统计，暂未调用。
 */
export function getUnreadCount() {
  return get<{ count: number }>('/api/notifications/unread-count')
}

/**
 * 标记单条已读 POST /api/notifications/{id}/read
 * 调用方：notice store 的 markRead；失败时 store 会回滚本地 isRead。
 */
export function markNotificationRead(id: number) {
  return post(`/api/notifications/${id}/read`)
}

/**
 * 全部标记已读 POST /api/notifications/read-all
 * 调用方：NoticeBell「全部已读」经 store 的 markAllRead 触发；
 * 公告的已读状态另存 localStorage，不经过此接口。
 */
export function markAllNotificationsRead() {
  return post('/api/notifications/read-all')
}
