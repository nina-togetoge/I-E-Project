<!--
  ==== ApprovalFlow ====
  职责：项目审批链路可视化。用 el-steps 展示「学生提交 → 导师审批 → 学院审批 → 财务审批」
        四个节点，并根据项目状态码推导每个节点的完成 / 进行中 / 未开始 / 驳回状态。
  复用：项目详情、审核工作台、评审材料等需要展示审批进度的位置。
  契约：props：status（项目状态码，必填）、comment（驳回原因，可选，默认空串）；
        无 emit、无插槽。
  注意：1) 节点与状态码的映射集中在 doneBefore / isCurrent，本视图将 0 视为学生填写中、
           1 视为导师审批中、3 视为学院审批中、5 视为财务审批中，>=6 视为全链路完成；
        2) 状态 7 表示已驳回，会在顶部额外渲染错误提示，并反推驳回发生的节点；
        3) 瞬时状态 2 / 4 按"已推进"处理，不在步骤条上单独展示；
        4) 本组件的状态口径与 StatusTag 不同，改动状态流转时需一并核对两处。
-->
<template>
  <div class="approval-flow">
    <!-- 区块：驳回提示，仅在 status=7 时出现；有驳回意见时一并展示，帮助申报人定位问题 -->
    <el-alert
      v-if="status === 7"
      type="error"
      show-icon
      title="已驳回"
      class="reject-alert"
    >
      <div v-if="comment" class="reject-comment">驳回原因：{{ comment }}</div>
    </el-alert>

    <!-- 区块：审批步骤条，四节点横向排列；active/process-status 由状态码计算，图标与描述逐节点推导 -->
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

// ==================== props ====================
/** 审批链路入参。组件只读取状态码，不主动拉取项目数据。 */
const props = withDefaults(
  defineProps<{
    /** 项目状态码；7 表示已驳回，>=6 表示已进入立项及之后阶段 */
    status: number
    /** 驳回原因，仅 status=7 时有意义，用于在提示条中展示 */
    comment?: string
  }>(),
  {
    comment: '',
  }
)

// ==================== 节点判定 ====================
/**
 * 判断第 idx 个节点是否已完成（已走过该环节）。
 * @param idx 节点序号：0 学生提交 / 1 导师审批 / 2 学院审批 / 3 财务审批
 * @returns 已完成返回 true
 * 映射依据：状态 1 表示学生已提交；2 表示导师已通过；4 表示学院已通过；6 表示财务/立项完成。
 */
const doneBefore = (idx: number): boolean => {
  const s = props.status
  if (idx === 0) return s >= 1
  if (idx === 1) return s >= 2
  if (idx === 2) return s >= 4
  if (idx === 3) return s >= 6
  return false
}

/**
 * 判断第 idx 个节点是否为当前进行中的环节。
 * @param idx 节点序号
 * @returns 进行中返回 true；已驳回（7）时任何节点都不算进行中
 * 映射依据：0 学生填写中、1 导师审批中、3 学院审批中、5 财务审批中。
 */
const isCurrent = (idx: number): boolean => {
  const s = props.status
  if (s === 7) return false
  if (idx === 0) return s === 0
  if (idx === 1) return s === 1
  if (idx === 2) return s === 3
  if (idx === 3) return s === 5
  return false
}

/**
 * 反推驳回发生的节点：取"最后一个已完成节点"的下一节点。
 * @returns 0-3 的节点序号；非驳回状态返回 -1；无任何已完成节点时兜底为 1（导师审批）
 */
const rejectNodeIdx = computed((): number => {
  const s = props.status
  if (s !== 7) return -1
  const lastDone = [doneBefore(0), doneBefore(1), doneBefore(2), doneBefore(3)].lastIndexOf(true)
  return lastDone >= 0 ? Math.min(lastDone + 1, 3) : 1
})

/**
 * el-steps 的 active 值（从 1 开始，表示已完成/进行到的步骤数）。
 * 驳回时指向出问题的节点，已立项及之后直接满格 4，其余按状态逐级推进。
 */
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

/**
 * 当前步骤的视觉状态：驳回显示 error（红色），立项后显示 success（绿色），其余 process（主色）。
 * @returns el-steps 的 process-status 取值
 */
const processStatus = computed(() => {
  if (props.status === 7) return 'error'
  return props.status >= 6 ? 'success' : 'process'
})

/**
 * 汇总单个节点的最终状态。
 * @param idx 节点序号 0-3
 * @returns done 已完成 / current 进行中 / pending 未开始 / reject 被驳回
 * 说明：驳回态优先判断，驳回节点之前的节点仍算完成，之后的节点算未开始。
 */
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

/**
 * 生成节点副标题文案。
 * @param idx 节点序号
 * @returns 通过 / 驳回 / 待审 / 未开始
 */
function getNodeDesc(idx: number): string {
  const st = getNodeStatus(idx)
  if (st === 'done') return '通过 ✅'
  if (st === 'reject') return '驳回 ❌'
  if (st === 'current') return '待审 ⏳'
  return '未开始'
}

/**
 * 生成节点图标：完成/驳回/进行中分别用符号表示，未开始则显示序号。
 * @param idx 节点序号
 * @returns 供模板插槽渲染的文本图标
 */
function getNodeIcon(idx: number): string {
  const st = getNodeStatus(idx)
  if (st === 'done') return '✅'
  if (st === 'reject') return '❌'
  if (st === 'current') return '⏳'
  return String(idx + 1)
}
</script>

<style scoped>
/* 容器：上下留白，和详情页其他信息块保持节奏一致 */
.approval-flow {
  padding: 12px 0;
}
/* 驳回提示条：与步骤条拉开距离，避免两种状态视觉上互相干扰 */
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
