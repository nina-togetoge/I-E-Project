/**
 * 系统公告接口
 *
 * 覆盖管理员公告的增删改查，以及顶栏通知聚合所需的已发布公告列表。
 * 主要调用方：
 *   - views/announcement/AnnouncementManage.vue：公告管理表格与编辑弹窗；
 *   - store/notice.ts：拉取已发布公告（status=1）合并进顶栏通知。
 * 约定：列表返回 PageResult，page 从 1 开始；公告正文为 HTML，
 * 顶栏展示前由 notice store 的 stripHtml 去标签。
 */
import { get, post, put, del } from '@/utils/request'
import type { PageResult } from '@/utils/request'

/**
 * 公告列表项：管理端表格与顶栏通知共用
 * 类型、状态、优先级均为枚举值，后端同时回填 *_name 文案。
 */
export interface AnnouncementListItem {
  /** 公告主键 */
  id: number
  /** 公告标题 */
  title: string
  /** 公告正文（HTML 富文本） */
  content: string
  /** 公告类型：1 系统通知 / 2 申报通知 / 3 结果公示 / 4 其他 */
  announcement_type: number
  /** 类型文案 */
  announcement_type_name: string
  /** 状态：0 草稿 / 1 已发布 / 2 已下线 */
  status: number
  /** 状态文案 */
  status_name: string
  /** 优先级：1 普通 / 2 重要 / 3 紧急 */
  priority: number
  /** 优先级文案 */
  priority_name: string
  /** 发布时间，草稿为空 */
  publish_time: string | null
  /** 过期时间，过期后前端不再展示/后端自动下线 */
  expire_time: string | null
  /** 浏览次数 */
  view_count: number
  /** 创建人用户 ID，系统公告可能为空 */
  created_by: number | null
  /** 创建人姓名 */
  creator_name: string | null
  /** 创建时间 */
  created_at: string
}

/**
 * 公告详情：字段与列表项一致（后端独立 Schema，content 可能做增量处理）。
 */
export interface AnnouncementDetail extends AnnouncementListItem {
  /** 公告正文 HTML */
  content: string
}

/**
 * 公告创建/更新参数
 * 更新接口使用 Partial<AnnouncementForm>，允许只提交变更字段。
 */
export interface AnnouncementForm {
  /** 标题（必填） */
  title: string
  /** 正文 HTML（必填） */
  content: string
  /** 类型：1 系统通知 / 2 申报通知 / 3 结果公示 / 4 其他 */
  announcement_type: number
  /** 状态：0 草稿 / 1 已发布 / 2 已下线 */
  status: number
  /** 优先级：1 普通 / 2 重要 / 3 紧急 */
  priority: number
  /** 过期时间，null 表示永不过期 */
  expire_time: string | null
}

/**
 * 公告列表 GET /api/announcements
 * 管理端可查看全部状态；顶栏只取 status=1 已发布，且固定 page_size=50。
 * @param params 分页 + 标题关键字 + 类型/状态筛选
 * @returns PageResult<AnnouncementListItem>
 * 调用方：AnnouncementManage、notice store。
 */
export function getAnnouncementList(params: {
  /** 页码，从 1 开始 */
  page: number
  /** 每页条数 */
  page_size: number
  /** 标题/正文关键字模糊搜索 */
  keyword?: string
  /** 公告类型：1-4 */
  announcement_type?: number
  /** 状态：0 草稿 / 1 已发布 / 2 已下线 */
  status?: number
}) {
  return get<PageResult<AnnouncementListItem>>('/api/announcements', params)
}

/**
 * 公告详情 GET /api/announcements/{id}
 * 用于管理端查看/编辑回填；后端可能同时累加浏览次数。
 * 调用方：AnnouncementManage 详情与编辑。
 */
export function getAnnouncementDetail(id: number) {
  return get<AnnouncementDetail>(`/api/announcements/${id}`)
}

/**
 * 创建公告 POST /api/announcements
 * 仅管理员可调用；状态为 1 时后端写入发布时间并进入顶栏通知。
 * 调用方：AnnouncementManage 新建弹窗。
 */
export function createAnnouncement(data: AnnouncementForm) {
  return post<AnnouncementDetail>('/api/announcements', data)
}

/**
 * 更新公告 PUT /api/announcements/{id}
 * 支持部分字段更新（如仅切换状态/优先级），调用方：AnnouncementManage 编辑/上下线。
 */
export function updateAnnouncement(id: number, data: Partial<AnnouncementForm>) {
  return put<AnnouncementDetail>(`/api/announcements/${id}`, data)
}

/**
 * 删除公告 DELETE /api/announcements/{id}
 * 后端软删除；已发布公告删除后也会从顶栏通知中消失。
 * 调用方：AnnouncementManage，页面负责二次确认。
 */
export function deleteAnnouncement(id: number) {
  return del(`/api/announcements/${id}`)
}
