/**
 * 系统公告/通知状态管理（Pinia）
 * 管理顶栏通知列表：管理员公告 + 站内业务通知（审核结果、成果认定等）
 * 公告已读状态存 localStorage；站内通知已读状态由后端维护
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getAnnouncementList, type AnnouncementListItem } from '@/api/announcement'
import {
  getNotificationList,
  markNotificationRead,
  markAllNotificationsRead,
} from '@/api/notification'

export type NoticeType = 'info' | 'warning' | 'success'
export type NoticePriority = 'high' | 'medium' | 'low'
export type NoticeSource = 'announcement' | 'notification'

export interface Notice {
  id: number
  source: NoticeSource
  title: string
  content: string
  type: NoticeType
  priority: NoticePriority
  created_at: string
  isRead: boolean
  link?: string | null
}

const READ_STORAGE_KEY = 'system_notices_read'

/** 公告类型 → 通知类型映射 */
function mapType(announcementType: number): NoticeType {
  // 1-系统通知 2-申报通知 3-结果公示 4-其他
  switch (announcementType) {
    case 1: return 'warning'
    case 3: return 'success'
    default: return 'info'
  }
}

/** 公告优先级 → 通知优先级映射 */
function mapPriority(priority: number): NoticePriority {
  // 1-普通 2-重要 3-紧急
  switch (priority) {
    case 3: return 'high'
    case 2: return 'medium'
    default: return 'low'
  }
}

/** 站内通知级别 → 通知类型映射 */
function mapLevelType(level: number): NoticeType {
  switch (level) {
    case 2: return 'warning'
    case 3: return 'success'
    default: return 'info'
  }
}

/** 站内通知级别 → 优先级映射 */
function mapLevelPriority(level: number): NoticePriority {
  switch (level) {
    case 2: return 'high'
    case 3: return 'medium'
    default: return 'low'
  }
}

/** 去除 HTML 标签，保留纯文本 */
function stripHtml(html: string): string {
  if (!html) return ''
  const tmp = document.createElement('div')
  tmp.innerHTML = html
  return (tmp.textContent || tmp.innerText || '').replace(/\s+/g, ' ').trim()
}

function loadReadIds(): Set<number> {
  try {
    const raw = localStorage.getItem(READ_STORAGE_KEY)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr)) return new Set(arr.map(Number))
    }
  } catch {
    // ignore
  }
  return new Set()
}

function saveReadIds(ids: Set<number>) {
  try {
    localStorage.setItem(READ_STORAGE_KEY, JSON.stringify([...ids]))
  } catch {
    // ignore
  }
}

export const useNoticeStore = defineStore('notice', () => {
  const notices = ref<Notice[]>([])
  const readIds = ref<Set<number>>(loadReadIds())
  const loading = ref(false)

  const unreadCount = computed(() => notices.value.filter((n) => !n.isRead).length)

  function noticeKey(n: Notice): string {
    return `${n.source}-${n.id}`
  }

  /** 拉取公告 + 站内通知，合并后按时间倒序 */
  async function fetchNotices() {
    loading.value = true
    const results = await Promise.allSettled([
      getAnnouncementList({ page: 1, page_size: 50, status: 1 }),
      getNotificationList({ page: 1, page_size: 50 }),
    ])

    const merged: Notice[] = []

    // 公告
    if (results[0].status === 'fulfilled') {
      const data = (results[0].value as any).data ?? results[0].value
      const items: AnnouncementListItem[] = data.items || []
      for (const a of items) {
        merged.push({
          id: a.id,
          source: 'announcement',
          title: a.title,
          content: stripHtml(a.content || ''),
          type: mapType(a.announcement_type),
          priority: mapPriority(a.priority),
          created_at: a.publish_time || a.created_at,
          isRead: readIds.value.has(a.id),
        })
      }
    }

    // 站内通知
    if (results[1].status === 'fulfilled') {
      const data = (results[1].value as any).data ?? results[1].value
      const items = data.items || []
      for (const n of items) {
        merged.push({
          id: n.id,
          source: 'notification',
          title: n.title,
          content: n.content,
          type: mapLevelType(n.level),
          priority: mapLevelPriority(n.level),
          created_at: n.created_at,
          isRead: n.is_read === 1,
          link: n.link,
        })
      }
    }

    merged.sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0))
    notices.value = merged
    loading.value = false
  }

  async function markRead(target: Notice | string) {
    const n = typeof target === 'string'
      ? notices.value.find((x) => noticeKey(x) === target)
      : notices.value.find((x) => noticeKey(x) === noticeKey(target))
    if (!n || n.isRead) return
    n.isRead = true
    if (n.source === 'notification') {
      try {
        await markNotificationRead(n.id)
      } catch {
        // 失败时回滚状态，等待下次刷新
        n.isRead = false
      }
    } else {
      readIds.value.add(n.id)
      saveReadIds(readIds.value)
    }
  }

  async function markAllRead() {
    const unread = notices.value.filter((n) => !n.isRead)
    if (unread.length === 0) return
    const hasNotification = unread.some((n) => n.source === 'notification')
    for (const n of unread) {
      if (n.source === 'announcement') {
        readIds.value.add(n.id)
      }
      n.isRead = true
    }
    saveReadIds(readIds.value)
    if (hasNotification) {
      try {
        await markAllNotificationsRead()
      } catch {
        // 忽略失败，下次刷新会同步真实状态
      }
    }
  }

  return {
    notices,
    unreadCount,
    loading,
    noticeKey,
    fetchNotices,
    markRead,
    markAllRead,
  }
})
