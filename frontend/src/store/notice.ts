/**
 * 系统公告/通知状态管理（Pinia）
 * 管理系统通知列表、已读状态、未读计数
 * 通知来源：管理员发布的公告（从后端 API 拉取已发布状态的公告）
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getAnnouncementList, type AnnouncementListItem } from '@/api/announcement'

export type NoticeType = 'info' | 'warning' | 'success'
export type NoticePriority = 'high' | 'medium' | 'low'

export interface Notice {
  id: number
  title: string
  content: string
  type: NoticeType
  priority: NoticePriority
  created_at: string
  isRead: boolean
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

  /** 从后端拉取已发布公告并转换为通知 */
  async function fetchNotices() {
    loading.value = true
    try {
      const res = await getAnnouncementList({ page: 1, page_size: 50, status: 1 })
      const data = (res as any).data ?? res
      const items: AnnouncementListItem[] = data.items || []
      notices.value = items.map((a) => ({
        id: a.id,
        title: a.title,
        content: stripHtml(a.content || ''),
        type: mapType(a.announcement_type),
        priority: mapPriority(a.priority),
        created_at: a.publish_time || a.created_at,
        isRead: readIds.value.has(a.id),
      }))
    } catch {
      // 拉取失败时保持空列表
      notices.value = []
    } finally {
      loading.value = false
    }
  }

  function markRead(id: number) {
    const n = notices.value.find((x) => x.id === id)
    if (n && !n.isRead) {
      n.isRead = true
      readIds.value.add(id)
      saveReadIds(readIds.value)
    }
  }

  function markAllRead() {
    let changed = false
    for (const n of notices.value) {
      if (!n.isRead) {
        n.isRead = true
        readIds.value.add(n.id)
        changed = true
      }
    }
    if (changed) saveReadIds(readIds.value)
  }

  return {
    notices,
    unreadCount,
    loading,
    fetchNotices,
    markRead,
    markAllRead,
  }
})
