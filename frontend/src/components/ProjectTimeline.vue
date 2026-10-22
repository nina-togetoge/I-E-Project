<template>
  <el-timeline>
    <el-timeline-item
      v-for="(item, idx) in timelineEvents"
      :key="idx"
      :timestamp="item.timestamp"
      placement="top"
      :type="item.type"
    >
      <h4>{{ item.title }}</h4>
      <p v-if="item.subtitle">{{ item.subtitle }}</p>
      <p v-if="item.content">{{ item.content }}</p>
      <p v-if="item.score">评分：{{ item.score }}</p>
      <p v-if="item.dimScores">分项：{{ dimScoreText(item.dimScores) }}</p>
      <el-tag
        v-if="item.resultTag"
        size="small"
        :type="item.type === 'danger' ? 'danger' : item.type === 'success' ? 'success' : 'info'"
      >
        {{ item.resultTag }}
      </el-tag>
      <div v-if="item.hasAttachment" style="margin-top: 8px;">
        <el-button link type="primary" size="small" @click="handleAttachmentClick(item)">
          📎 审核附件
        </el-button>
      </div>
    </el-timeline-item>
  </el-timeline>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { formatDateTime } from '@/utils/format'
import { scoringCriteria } from '@/data/scoringCriteria'

interface TimelineEvent {
  timestamp: string
  type: 'primary' | 'success' | 'warning' | 'danger'
  title: string
  subtitle?: string
  content?: string
  score?: number
  dimScores?: Record<string, number>
  resultTag?: string
  hasAttachment?: boolean
  attachmentId?: number
}

const props = defineProps<{
  project: any
  reviewHistory: any[]
}>()

/** 专家分项得分文案：创新性 90 · 可行性 85 · ... */
function dimScoreText(dim: Record<string, number>) {
  return scoringCriteria.map((c) => `${c.name} ${dim[c.key] ?? 0}`).join(' · ')
}

const timelineEvents = computed<TimelineEvent[]>(() => {
  const events: TimelineEvent[] = []
  const p = props.project
  if (!p) return events

  if (p.created_at) {
    events.push({
      timestamp: formatDateTime(p.created_at),
      type: 'primary',
      title: '创建项目草稿',
    })
  }

  if (p.submitted_at || p.submit_time) {
    events.push({
      timestamp: formatDateTime(p.submitted_at || p.submit_time),
      type: 'warning',
      title: '提交审核，等待指导教师确认',
    })
  }

  const reviews = props.reviewHistory || []
  reviews.forEach((review) => {
    const time = review.review_time || review.created_at
    const isPass = review.review_result === 1
    events.push({
      timestamp: formatDateTime(time),
      type: isPass ? 'success' : 'danger',
      title: review.review_stage_name || '审核',
      subtitle: `审核人：${review.reviewer_name || '待分配'}`,
      content: review.review_comment ? `意见：${review.review_comment}` : undefined,
      score: review.score || undefined,
      dimScores: review.dim_scores || undefined,
      resultTag: review.review_result_name || (isPass ? '通过' : '驳回'),
      hasAttachment: !!review.attachment_id,
      attachmentId: review.attachment_id,
    })
  })

  const hasApprovedInReview = reviews.some(
    (r) => r.review_stage_name && r.review_stage_name.includes('立项') && r.review_result === 1
  )

  if (p.approved_at && !hasApprovedInReview) {
    events.push({
      timestamp: formatDateTime(p.approved_at),
      type: 'success',
      title: '项目正式立项',
    })
  }

  if (p.finished_at) {
    events.push({
      timestamp: formatDateTime(p.finished_at),
      type: 'success',
      title: '项目完成结项',
    })
  }

  if (p.rejected_at) {
    events.push({
      timestamp: formatDateTime(p.rejected_at),
      type: 'danger',
      title: '项目被驳回',
      content: p.reject_reason ? `原因：${p.reject_reason}` : undefined,
    })
  }

  events.sort((a, b) => {
    const ta = new Date(a.timestamp).getTime()
    const tb = new Date(b.timestamp).getTime()
    return ta - tb
  })

  return events
})

function handleAttachmentClick(item: TimelineEvent) {
  if (item.attachmentId) {
    ElMessage.info(`附件ID: ${item.attachmentId}，请联系管理员下载`)
  }
}
</script>
