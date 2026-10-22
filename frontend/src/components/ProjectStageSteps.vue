<!--
  项目后期流程步骤条（中期检查 → 成果登记 → 结项验收）
  三页共用：按项目状态标记当前进度，点击可直接切换页面
-->
<template>
  <div v-if="project" class="stage-steps">
    <el-steps :active="activeStep" align-center finish-status="success">
      <el-step
        v-for="s in steps"
        :key="s.key"
        :title="s.title"
        :description="s.key === current ? '当前页面' : s.desc"
        class="stage-step"
        @click="go(s.key)"
      />
    </el-steps>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps<{
  project: any
  current: 'midterm' | 'achievements' | 'final'
}>()

const router = useRouter()

const steps = [
  { key: 'midterm' as const, title: '中期检查', desc: '填写并审核中期报告' },
  { key: 'achievements' as const, title: '成果登记', desc: '登记论文专利等成果' },
  { key: 'final' as const, title: '结项验收', desc: '提交结项报告并验收' },
]

/** 依据项目状态推导已完成步骤数：6/7 中期进行中，8 待结项，9 已结题 */
const activeStep = computed(() => {
  const status = Number(props.project?.status ?? 0)
  if (status >= 9) return steps.length
  if (status === 8) return 2
  return 0
})

function go(key: 'midterm' | 'achievements' | 'final') {
  if (!props.project?.id || key === props.current) return
  router.push(`/projects/${props.project.id}/${key}`)
}
</script>

<style scoped>
.stage-steps {
  margin-bottom: 20px;
}
.stage-step {
  cursor: pointer;
}
.stage-step :deep(.el-step__title),
.stage-step :deep(.el-step__description) {
  transition: color 0.2s;
}
.stage-step:hover :deep(.el-step__title) {
  color: var(--el-color-primary);
}
</style>
