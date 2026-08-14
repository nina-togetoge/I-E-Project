<!--
  状态标签组件
  根据项目状态码显示对应的 Tag
-->
<template>
  <el-tag :type="tagType" :effect="effect">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    status: number
    effect?: 'light' | 'dark' | 'plain'
  }>(),
  { effect: 'light' }
)

const STATUS_MAP: Record<number, { label: string; type: string }> = {
  0: { label: '草稿', type: 'info' },
  10: { label: '待审核', type: 'warning' },
  20: { label: '学院初审中', type: 'warning' },
  30: { label: '校级复审中', type: 'warning' },
  40: { label: '专家评审中', type: 'warning' },
  50: { label: '已立项', type: 'success' },
  60: { label: '已驳回', type: 'danger' },
  70: { label: '进行中', type: 'primary' },
  80: { label: '中期检查', type: 'warning' },
  90: { label: '已归档', type: 'success' },
}

const label = computed(() => STATUS_MAP[props.status]?.label || '未知')
const tagType = computed(() => STATUS_MAP[props.status]?.type || 'info')
</script>
