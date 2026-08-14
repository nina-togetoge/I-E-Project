<template>
  <el-tag :type="tagType" size="small">{{ statusText }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: number
}>()

const statusMap: Record<number, { text: string; type: string }> = {
  0: { text: '草稿', type: 'info' },
  1: { text: '待学院初审', type: 'warning' },
  2: { text: '学院初审通过', type: 'success' },
  3: { text: '待校级复审', type: 'warning' },
  4: { text: '校级复审通过', type: 'success' },
  5: { text: '待专家评审', type: 'warning' },
  6: { text: '已立项', type: 'primary' },
  7: { text: '中期检查中', type: 'warning' },
  8: { text: '待结题', type: 'warning' },
  9: { text: '已结题', type: 'success' },
  10: { text: '已驳回', type: 'danger' },
  11: { text: '已撤销', type: 'info' },
}

const statusText = computed(() => statusMap[props.status]?.text || `未知(${props.status})`)
const tagType = computed(() => statusMap[props.status]?.type || 'info')
</script>