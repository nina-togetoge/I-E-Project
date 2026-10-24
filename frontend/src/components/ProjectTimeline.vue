<!--
  项目审核时间轴（ProjectTimeline）
  面向角色：项目负责人、指导教师、学院/校级管理员、评审专家（详情页所有可查看用户）。
  核心功能：把项目生命周期中的关键节点合并为一条按时间正序的时间轴，包括：
           创建草稿、提交审核、各阶段审核记录、正式立项、完成结项、被驳回。
  数据来源：父组件传入 project（项目详情）与 reviewHistory（审核流程记录），
           本组件不再发起请求，不做任何写操作。
  关键约束：
    1. 审核记录中 review_result=1 视为通过（绿色），其余按驳回（红色）展示；
    2. 若审核历史里已有「立项」通过记录，则不再重复追加 approved_at 立项节点，
       避免时间轴上出现两行含义相同的事件；
    3. 时间可能来自不同字段（submitted_at / submit_time、review_time / created_at），
       取到第一个有效值即可，缺失时由 formatDateTime 统一处理。
  特别注意：审核附件按钮目前仅展示附件 ID 并提示联系管理员，不直接下载，
           属于历史占位交互，修改前需先确认附件鉴权方案。
-->
<template>
  <!-- 时间轴主体：空数据时 Element Plus 渲染为空容器，父组件负责详情加载态 -->
  <el-timeline>
    <!-- 事件节点：所有可选内容（副标题、意见、评分、分项、结果、附件）均按存在性渲染 -->
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
      <!-- 专家评分只在专家评审记录上出现，普通审核没有 score 字段 -->
      <p v-if="item.score">评分：{{ item.score }}</p>
      <!-- 分项得分：按 scoringCriteria 顺序拼成一行，缺失维度按 0 显示 -->
      <p v-if="item.dimScores">分项：{{ dimScoreText(item.dimScores) }}</p>
      <!-- 结果标签颜色跟随事件类型：驳回红、通过绿、其余灰；不改变已有语义 -->
      <el-tag
        v-if="item.resultTag"
        size="small"
        :type="item.type === 'danger' ? 'danger' : item.type === 'success' ? 'success' : 'info'"
      >
        {{ item.resultTag }}
      </el-tag>
      <!-- 审核附件入口：仅审核记录携带 attachment_id 时显示 -->
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

/** 时间轴单条事件的内部结构，仅用于渲染，不对外暴露 */
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

// ==================== Props ====================

const props = defineProps<{
  /** 项目详情对象，提供各关键时间点与驳回原因 */
  project: any
  /** 审核流程记录，来源为项目详情接口返回的历史列表 */
  reviewHistory: any[]
}>()

// ==================== 展示辅助 ====================

/**
 * 专家分项得分文案：创新性 90 · 可行性 85 · ...
 * @param dim 维度得分映射，缺失的维度按 0 兜底，保证文案长度稳定
 */
function dimScoreText(dim: Record<string, number>) {
  return scoringCriteria.map((c) => `${c.name} ${dim[c.key] ?? 0}`).join(' · ')
}

// ==================== 时间轴数据 ====================

/**
 * 合并项目关键节点与审核记录，并按时间升序排列。
 * 副作用：无，纯派生数据；project 为空时返回空数组，避免父组件异步加载期间报错。
 * 说明：审核记录直接平铺，不再按阶段分组，保留完整历史便于追溯。
 */
const timelineEvents = computed<TimelineEvent[]>(() => {
  const events: TimelineEvent[] = []
  const p = props.project
  if (!p) return events

  // 创建节点：草稿产生的起点，没有该时间则说明数据缺失，直接跳过
  if (p.created_at) {
    events.push({
      timestamp: formatDateTime(p.created_at),
      type: 'primary',
      title: '创建项目草稿',
    })
  }

  // 提交节点：兼容新旧字段名，submitted_at 优先，旧数据回退 submit_time
  if (p.submitted_at || p.submit_time) {
    events.push({
      timestamp: formatDateTime(p.submitted_at || p.submit_time),
      type: 'warning',
      title: '提交审核，等待指导教师确认',
    })
  }

  // 审核记录：每条记录生成一个节点，review_result=1 为通过，其它值按驳回着色
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

  // 立项去重：审核历史中已有「立项」通过记录时，不再用 approved_at 追加同义节点
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

  // 结项完成：只有真正归档后 finished_at 才有值
  if (p.finished_at) {
    events.push({
      timestamp: formatDateTime(p.finished_at),
      type: 'success',
      title: '项目完成结项',
    })
  }

  // 驳回节点：单独记录被驳回的时间与原因，与单次审核的驳回意见互为补充
  if (p.rejected_at) {
    events.push({
      timestamp: formatDateTime(p.rejected_at),
      type: 'danger',
      title: '项目被驳回',
      content: p.reject_reason ? `原因：${p.reject_reason}` : undefined,
    })
  }

  // 按真实时间升序排列：时间轴从早到晚阅读，符合项目推进顺序
  events.sort((a, b) => {
    const ta = new Date(a.timestamp).getTime()
    const tb = new Date(b.timestamp).getTime()
    return ta - tb
  })

  return events
})

// ==================== 交互 ====================

/**
 * 点击「审核附件」。
 * 当前实现只提示附件 ID，不发起下载：历史附件缺少统一鉴权入口，直接打开会 401。
 * @param item 当前时间轴事件，需包含 attachmentId
 */
function handleAttachmentClick(item: TimelineEvent) {
  if (item.attachmentId) {
    ElMessage.info(`附件ID: ${item.attachmentId}，请联系管理员下载`)
  }
}
</script>
