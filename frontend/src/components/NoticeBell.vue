<!--
  ==== NoticeBell ====
  职责：系统通知铃铛组件，顶栏通知入口：铃铛 + 未读角标 + 点击弹出的通知列表弹窗。
        支持「全部已读」、优先级标签、相对时间、正文超长折叠。
  复用：全局布局顶栏的通知入口，学生/教师/专家/管理员各角色通用。
  契约：无 props、无 emit、无插槽；数据全部来自 Pinia 的 notice store，
        挂载时自动拉取管理员公告与站内业务通知（审核结果、成果认定等）。
  注意：1) 公告已读状态存 localStorage，站内通知已读状态由后端维护；
        2) 通知的 link 决定点击行为：有链接直接路由跳转，无链接则就地展开/收起正文；
        3) 角标最多显示 99，未读数为 0 时隐藏。
-->
<template>
  <!-- 区块：通知弹窗（trigger="click"，挂载到 body 下避免被顶栏溢出裁剪） -->
  <el-popover
    placement="bottom-end"
    :width="380"
    trigger="click"
    popper-class="notice-popover"
    :visible-arrow="false"
  >
    <!-- 触发区：铃铛图标外套未读角标，角标超过 99 显示为 99+ -->
    <template #reference>
      <el-badge :value="noticeStore.unreadCount" :hidden="noticeStore.unreadCount === 0" class="notice-badge" :max="99">
        <el-icon class="action-item" @click="popoverVisible = !popoverVisible">
          <Bell />
        </el-icon>
      </el-badge>
    </template>

    <div class="notice-panel">
      <!-- 区块：面板头部，未读为 0 时禁用「全部已读」 -->
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

      <!-- 区块：通知列表，固定最大高度内滚动；无数据时展示空状态插画 -->
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
            <!-- 左侧：类型色点（info/warning/success）与优先级标签 -->
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
            <!-- 右侧：标题、相对时间与正文；正文超过 60 字时提供展开/收起 -->
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

// ==================== 依赖与状态 ====================
/** 通知中心 store：负责拉取并合并公告/站内通知，维护已读状态与未读计数 */
const noticeStore = useNoticeStore()
/** 路由实例，用于处理通知中携带的业务跳转链接 */
const router = useRouter()
/** 弹窗可见性标记，供铃铛点击时手动翻转（与 popover 自身的 click 触发配合） */
const popoverVisible = ref(false)
/** 已展开正文的通知键集合（source-id），仅控制展示态，不持久化 */
const expandedSet = ref(new Set<string>())

// ==================== 生命周期 ====================
/** 挂载即拉取通知，保证进入系统后角标数量立即准确 */
onMounted(() => {
  noticeStore.fetchNotices()
})

// ==================== 展示格式化 ====================
/**
 * 优先级枚举转中文标签。
 * @param p high-高 / medium-中 / low-低
 * @returns 单字优先级文案
 */
function priorityLabel(p: NoticePriority): string {
  return { high: '高', medium: '中', low: '低' }[p]
}

/**
 * 优先级枚举映射为 Element Plus 标签色。
 * @param p 优先级；high 用 danger、medium 用 warning、low 用 info
 * @returns el-tag 的 type 值
 */
function priorityTagType(p: NoticePriority): string {
  return { high: 'danger', medium: 'warning', low: 'info' }[p]
}

/**
 * 把后端 ISO 时间格式化为相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前，
 * 超过 7 天回落为「MM-DD HH:mm」绝对时间。
 * @param iso 后端创建或发布时间
 * @returns 适合通知列表的短文案；解析失败时原样返回，避免展示空白
 */
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

/**
 * 截断正文，超出长度时追加省略号。
 * @param s 原始文本，空值返回空串
 * @param len 保留的最大字符数
 * @returns 截断后的展示文本
 */
function truncate(s: string, len: number): string {
  if (!s) return ''
  return s.length > len ? s.slice(0, len) + '...' : s
}

/**
 * 判断某条通知的正文当前是否处于展开态。
 * @param n 通知对象，用 store 提供的 source-id 复合键判定
 */
function isExpanded(n: Notice): boolean {
  return expandedSet.value.has(noticeStore.noticeKey(n))
}

/**
 * 切换某条通知正文的展开/收起状态。
 * 副作用：修改 expandedSet（Set 原地增删，依赖 ref 的浅层触发更新）。
 * @param n 通知对象
 */
function toggleExpand(n: Notice) {
  const key = noticeStore.noticeKey(n)
  if (expandedSet.value.has(key)) expandedSet.value.delete(key)
  else expandedSet.value.add(key)
}

/**
 * 点击通知项的统一处理：先标记已读，再按是否有业务链接决定跳转或就地展开。
 * @param n 被点击的通知
 * 副作用：可能调用 store.markRead（站内通知会请求后端）、路由跳转、修改展开状态。
 */
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
/* 触发区：铃铛整体可点击，深色模式下单独调整图标颜色保证对比度 */
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

/* 未读通知：浅蓝底 + 悬停加深，与已读项形成明显区分 */
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

/* 类型色点：info 蓝（普通通知）/ warning 橙（申报类）/ success 绿（结果公示） */
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

/* 未读小红点：绝对定位在条目右上角，不影响正文布局 */
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
