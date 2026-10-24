/**
 * 系统公告/通知状态管理（Pinia）
 *
 * 管理顶栏通知列表：管理员公告 + 站内业务通知（审核结果、成果认定、经费审批等）。
 * 生命周期：NoticeBell 挂载时调用 fetchNotices 拉取一次，不做轮询；
 * 用户点击通知时 markRead，点击「全部已读」时 markAllRead，页面刷新后重新拉取。
 *
 * 已读状态的两种持久化方式：
 *   - 公告：后端无 per-user 已读表，前端把公告 ID 集合存 localStorage
 *     （key=system_notices_read），仅在本机生效；
 *   - 站内通知：is_read/read_time 由后端维护，调用标记已读接口后即时生效。
 *
 * 合并策略：公告取已发布(status=1)前 50 条，通知取前 50 条，
 * 统一映射为 Notice 后按 created_at 倒序；任一侧失败不阻塞另一侧（Promise.allSettled）。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getAnnouncementList, type AnnouncementListItem } from '@/api/announcement'
import {
  getNotificationList,
  markNotificationRead,
  markAllNotificationsRead,
} from '@/api/notification'

/** 通知视觉类型：info 普通 / warning 警告 / success 成功，决定圆点与标签颜色 */
export type NoticeType = 'info' | 'warning' | 'success'
/** 通知优先级：high 高 / medium 中 / low 低，顶栏标签文案与颜色使用 */
export type NoticePriority = 'high' | 'medium' | 'low'
/** 通知来源：announcement 管理员公告 / notification 站内业务通知，决定已读实现方式 */
export type NoticeSource = 'announcement' | 'notification'

/**
 * 顶栏统一通知视图：由公告与站内通知映射而来。
 * 注意 id 在不同 source 下可能重复，列表 key 必须用 noticeKey(source-id)。
 */
export interface Notice {
  /** 来源表主键 */
  id: number
  /** 来源类型，决定已读状态存 localStorage 还是调后端 */
  source: NoticeSource
  /** 标题 */
  title: string
  /** 纯文本正文（公告已剥离 HTML） */
  content: string
  /** 视觉类型，映射自公告类型或通知 level */
  type: NoticeType
  /** 优先级，映射自公告 priority 或通知 level */
  priority: NoticePriority
  /** 发布时间/通知创建时间，用于倒序与相对时间展示 */
  created_at: string
  /** 当前用户是否已读 */
  isRead: boolean
  /** 点击跳转路由，公告通常为空 */
  link?: string | null
}

/** localStorage 中公告已读 ID 集合的键名（仅本机生效） */
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
  /** 合并后的通知列表，按时间倒序；NoticeBell 列表直接渲染 */
  const notices = ref<Notice[]>([])
  /** 本机已读公告 ID 集合，初始化时从 localStorage 恢复 */
  const readIds = ref<Set<number>>(loadReadIds())
  /** 拉取中标记，控制顶栏「暂无通知/加载中」展示 */
  const loading = ref(false)

  /** 未读数：由 notices 派生，任一条 isRead=false 即计数；驱动铃铛角标 */
  const unreadCount = computed(() => notices.value.filter((n) => !n.isRead).length)

  /**
   * 生成列表唯一键：source + id，避免公告与通知 ID 相同时 key 冲突。
   * 供 NoticeBell 的 v-for key 与 markRead 查找使用。
   */
  function noticeKey(n: Notice): string {
    return `${n.source}-${n.id}`
  }

  /**
   * 拉取公告 + 站内通知并合并
   * 请求：getAnnouncementList(status=1, 50) 与 getNotificationList(50) 并行，
   * 用 allSettled 保证单侧失败时另一侧仍可展示；公告正文去 HTML 后放入 content。
   * 结果按 created_at 倒序写回 notices，loading 在结束时复位。
   * 调用方：NoticeBell 的 onMounted。
   */
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

  /**
   * 标记单条已读
   * @param target 通知对象或其 source-id 键（NoticeBell 点击时传对象）
   * 公告：写入 readIds 并持久化 localStorage；
   * 站内通知：调用 POST /api/notifications/{id}/read，失败回滚 isRead 等下次刷新。
   * 已读的记录直接返回，避免重复请求。
   */
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

  /**
   * 全部标记已读
   * 本地先把公告 ID 写入 readIds/localStorage，并即时更新所有 isRead（乐观更新）；
   * 若含站内通知，再调用 POST /api/notifications/read-all 同步后端，失败静默忽略。
   * 调用方：NoticeBell 顶部「全部已读」；无未读时直接返回，不发请求。
   */
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
