<template>
  <el-tag :type="tagType" size="small">{{ statusText }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: number
  /** 可选：覆盖状态文案（如状态 10 区分「已驳回（可修改重提）」与「已落选」） */
  label?: string
  /** 可选：覆盖标签颜色 */
  overrideType?: string
}>()

const statusMap: Record<number, { text: string; type: string }> = {
  0: { text: '草稿', type: 'info' },
  12: { text: '待指导教师确认', type: 'warning' },
  1: { text: '待学院初审', type: 'warning' },
  2: { text: '学院初审通过', type: 'success' },
  3: { text: '待校级复审', type: 'warning' },
  4: { text: '校级复审通过', type: 'success' },
  5: { text: '待专家评审', type: 'warning' },
  13: { text: '待分配评审专家', type: 'warning' },
  6: { text: '已立项', type: 'primary' },
  7: { text: '中期检查中', type: 'warning' },
  8: { text: '待结题', type: 'warning' },
  9: { text: '已结题', type: 'success' },
  10: { text: '已驳回', type: 'danger' },
  11: { text: '已撤销', type: 'info' },
}

const statusText = computed(() => props.label || statusMap[props.status]?.text || `未知(${props.status})`)
const tagType = computed(() => props.overrideType || statusMap[props.status]?.type || 'info')
</script>