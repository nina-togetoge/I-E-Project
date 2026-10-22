<!--
  系统通知铃铛组件
  顶栏通知入口：铃铛 + 未读角标 + 弹窗列表
-->
<template>
  <el-popover
    placement="bottom-end"
    :width="380"
    trigger="click"
    popper-class="notice-popover"
    :visible-arrow="false"
  >
    <template #reference>
      <el-badge :value="noticeStore.unreadCount" :hidden="noticeStore.unreadCount === 0" class="notice-badge" :max="99">
        <el-icon class="action-item" @click="popoverVisible = !popoverVisible">
          <Bell />
        </el-icon>
      </el-badge>
    </template>

    <div class="notice-panel">
      <div class="notice-header">
        <span class="notice-title">系统通知</span>
        <el-button
          type="primary"
          link
          size="small"
          :disabled="noticeStore.unreadCount === 0"
          @click="noticeStore.markAllRead()"
        >
          全部已读
        </el-button>
      </div>

      <el-scrollbar max-height="380px">
        <div v-if="noticeStore.notices.length === 0" class="notice-empty">
          <EmptyIllustration type="default" description="暂无通知" />
        </div>
        <ul v-else class="notice-list">
          <li
            v-for="n in noticeStore.notices"
            :key="noticeStore.noticeKey(n)"
            class="notice-item"
            :class="{ unread: !n.isRead }"
            @click="handleClick(n)"
          >
            <div class="notice-left">
              <span
                class="notice-dot"
                :class="{
                  'dot-info': n.type === 'info',
                  'dot-warning': n.type === 'warning',
                  'dot-success': n.type === 'success',
                }"
              />
              <el-tag
                size="small"
                :type="priorityTagType(n.priority)"
                effect="light"
                class="notice-priority"
              >
                {{ priorityLabel(n.priority) }}
              </el-tag>
            </div>
            <div class="notice-body">
              <div class="notice-top">
                <span class="notice-item-title">{{ n.title }}</span>
                <span class="notice-time">{{ formatTime(n.created_at) }}</span>
              </div>
              <div class="notice-item-content">
                <span v-if="!isExpanded(n)">{{ truncate(n.content, 60) }}</span>
                <span v-else>{{ n.content }}</span>
                <el-button
                  v-if="n.content.length > 60"
                  link
                  type="primary"
                  size="small"
                  class="expand-btn"
                  @click.stop="toggleExpand(n)"
                >
                  {{ isExpanded(n) ? '收起' : '展开' }}
                </el-button>
              </div>
            </div>
            <span v-if="!n.isRead" class="unread-badge" />
          </li>
        </ul>
      </el-scrollbar>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import { useNoticeStore, type Notice, type NoticePriority } from '@/store/notice'
import dayjs from 'dayjs'

const noticeStore = useNoticeStore()
const router = useRouter()
const popoverVisible = ref(false)
const expandedSet = ref(new Set<string>())

onMounted(() => {
  noticeStore.fetchNotices()
})

function priorityLabel(p: NoticePriority): string {
  return { high: '高', medium: '中', low: '低' }[p]
}

function priorityTagType(p: NoticePriority): string {
  return { high: 'danger', medium: 'warning', low: 'info' }[p]
}

function formatTime(iso: string): string {
  try {
    const d = dayjs(iso)
    const now = dayjs()
    const diffMins = now.diff(d, 'minute')
    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return `${diffMins}分钟前`
    const diffH = now.diff(d, 'hour')
    if (diffH < 24) return `${diffH}小时前`
    const diffD = now.diff(d, 'day')
    if (diffD < 7) return `${diffD}天前`
    return d.format('MM-DD HH:mm')
  } catch {
    return iso
  }
}

function truncate(s: string, len: number): string {
  if (!s) return ''
  return s.length > len ? s.slice(0, len) + '...' : s
}

function isExpanded(n: Notice): boolean {
  return expandedSet.value.has(noticeStore.noticeKey(n))
}

function toggleExpand(n: Notice) {
  const key = noticeStore.noticeKey(n)
  if (expandedSet.value.has(key)) expandedSet.value.delete(key)
  else expandedSet.value.add(key)
}

function handleClick(n: Notice) {
  if (!n.isRead) {
    noticeStore.markRead(n)
  }
  if (n.link) {
    router.push(n.link)
    return
  }
  toggleExpand(n)
}
</script>

<style scoped>
.notice-badge {
  cursor: pointer;
}

.action-item {
  font-size: 18px;
  cursor: pointer;
  color: #5a5e66;
  transition: color 0.2s;
}

:deep(html.dark) .action-item {
  color: #cfd3dc;
}

.notice-panel {
  padding: 0;
}

.notice-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
}

.notice-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.notice-empty {
  padding: 32px 16px;
}

.notice-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.notice-item {
  position: relative;
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #f2f3f5;
  cursor: pointer;
  transition: background 0.15s;
}

.notice-item:hover {
  background: #f5f7fa;
}

.notice-item.unread {
  background: #ecf5ff;
}

.notice-item.unread:hover {
  background: #d9ecff;
}

.notice-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding-top: 2px;
}

.notice-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
}

.dot-info {
  background: #409eff;
}
.dot-warning {
  background: #e6a23c;
}
.dot-success {
  background: #67c23a;
}

.notice-priority {
  flex-shrink: 0;
}

.notice-body {
  flex: 1;
  min-width: 0;
}

.notice-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}

.notice-item-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.notice-time {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
}

.notice-item-content {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  word-break: break-word;
}

.expand-btn {
  margin-left: 4px;
}

.unread-badge {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f56c6c;
  flex-shrink: 0;
}
</style>
