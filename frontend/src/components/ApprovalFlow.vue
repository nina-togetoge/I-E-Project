<template>
  <div class="approval-flow">
    <el-alert
      v-if="status === 7"
      type="error"
      show-icon
      title="已驳回"
      class="reject-alert"
    >
      <div v-if="comment" class="reject-comment">驳回原因：{{ comment }}</div>
    </el-alert>

    <el-steps
      :active="displayActiveStep"
      direction="horizontal"
      finish-status="success"
      :process-status="processStatus"
    >
      <el-step title="学生提交" :description="getNodeDesc(0)">
        <template #icon><span class="step-icon">{{ getNodeIcon(0) }}</span></template>
      </el-step>
      <el-step title="导师审批" :description="getNodeDesc(1)">
        <template #icon><span class="step-icon">{{ getNodeIcon(1) }}</span></template>
      </el-step>
      <el-step title="学院审批" :description="getNodeDesc(2)">
        <template #icon><span class="step-icon">{{ getNodeIcon(2) }}</span></template>
      </el-step>
      <el-step title="财务审批" :description="getNodeDesc(3)">
        <template #icon><span class="step-icon">{{ getNodeIcon(3) }}</span></template>
      </el-step>
    </el-steps>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    status: number
    comment?: string
  }>(),
  {
    comment: '',
  }
)

const doneBefore = (idx: number): boolean => {
  const s = props.status
  if (idx === 0) return s >= 1
  if (idx === 1) return s >= 2
  if (idx === 2) return s >= 4
  if (idx === 3) return s >= 6
  return false
}

const isCurrent = (idx: number): boolean => {
  const s = props.status
  if (s === 7) return false
  if (idx === 0) return s === 0
  if (idx === 1) return s === 1
  if (idx === 2) return s === 3
  if (idx === 3) return s === 5
  return false
}

const rejectNodeIdx = computed((): number => {
  const s = props.status
  if (s !== 7) return -1
  const lastDone = [doneBefore(0), doneBefore(1), doneBefore(2), doneBefore(3)].lastIndexOf(true)
  return lastDone >= 0 ? Math.min(lastDone + 1, 3) : 1
})

const displayActiveStep = computed(() => {
  const s = props.status
  if (s === 7) {
    return rejectNodeIdx.value + 1
  }
  if (s >= 6) return 4
  if (s === 5) return 3
  if (s >= 3) return 3
  if (s === 2) return 2
  if (s >= 1) return 2
  return 1
})

const processStatus = computed(() => {
  if (props.status === 7) return 'error'
  return props.status >= 6 ? 'success' : 'process'
})

function getNodeStatus(idx: number): 'done' | 'current' | 'pending' | 'reject' {
  if (props.status === 7) {
    if (idx <= rejectNodeIdx.value) {
      if (idx === rejectNodeIdx.value) return 'reject'
      return 'done'
    }
    return 'pending'
  }
  if (doneBefore(idx)) return 'done'
  if (isCurrent(idx)) return 'current'
  return 'pending'
}

function getNodeDesc(idx: number): string {
  const st = getNodeStatus(idx)
  if (st === 'done') return '通过 ✅'
  if (st === 'reject') return '驳回 ❌'
  if (st === 'current') return '待审 ⏳'
  return '未开始'
}

function getNodeIcon(idx: number): string {
  const st = getNodeStatus(idx)
  if (st === 'done') return '✅'
  if (st === 'reject') return '❌'
  if (st === 'current') return '⏳'
  return String(idx + 1)
}
</script>

<style scoped>
.approval-flow {
  padding: 12px 0;
}
.reject-alert {
  margin-bottom: 20px;
}
.reject-comment {
  margin-top: 6px;
  font-size: 13px;
  color: #606266;
}
.step-icon {
  font-size: 16px;
}
:deep(.el-step__title.is-process) {
  font-weight: 600;
}
</style>
