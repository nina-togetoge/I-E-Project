<!--
  项目后期流程步骤条（ProjectStageSteps）
  面向角色：项目负责人、指导教师、学院/校级管理员、评审专家（三个后期页面共用）。
  核心功能：以「中期检查 → 成果登记 → 结项验收」三步展示项目后期进度，
           并允许直接点击步骤切换页面，省去返回列表再进入的成本。
  调用 API：无。页面切换仅通过 vue-router push，数据由目标页面自行加载。
  关键状态约束：
    - status >= 9（已结题）时三步全部标记完成；
    - status === 8（待结项）时第三步为当前步骤；
    - 其他状态（草稿、审核中、中期进行中）都停在第一步，
      因为后期流程尚未真正开始，提前点亮后续步骤会误导用户。
  特别注意：project 为空时不渲染，避免父组件异步加载期间出现空步骤条；
           点击当前页对应的步骤不会重复跳转，防止路由冗余导航报错。
-->
<template>
  <!-- 仅当项目已加载时展示，步骤条在加载态隐藏，减少布局跳动 -->
  <div v-if="project" class="stage-steps">
    <!-- active 表示当前进行到的步骤索引；finish-status=success 让已完成步骤显示对勾 -->
    <el-steps :active="activeStep" align-center finish-status="success">
      <!-- 每个步骤可点击跳转；当前页用「当前页面」替代说明文案，明确位置 -->
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

// ==================== Props ====================

const props = defineProps<{
  /** 项目对象，至少需要 id 与 status；缺失时不渲染 */
  project: any
  /** 当前所在页面的步骤标识，用于高亮「当前页面」 */
  current: 'midterm' | 'achievements' | 'final'
}>()

const router = useRouter()

// ==================== 步骤配置 ====================

/** 三步固定顺序：顺序即业务推进顺序，不可随意调整 */
const steps = [
  { key: 'midterm' as const, title: '中期检查', desc: '填写并审核中期报告' },
  { key: 'achievements' as const, title: '成果登记', desc: '登记论文专利等成果' },
  { key: 'final' as const, title: '结项验收', desc: '提交结项报告并验收' },
]

// ==================== 进度计算 ====================

/** 依据项目状态推导已完成步骤数：6/7 中期进行中，8 待结项，9 已结题 */
const activeStep = computed(() => {
  const status = Number(props.project?.status ?? 0)
  if (status >= 9) return steps.length
  if (status === 8) return 2
  return 0
})

// ==================== 页面切换 ====================

/**
 * 跳转到指定后期页面。
 * 失败处理：无项目 id 或点击当前页时直接返回，避免无效路由跳转。
 * 副作用：触发 router.push，页面切换后由目标页重新拉取项目详情。
 * @param key 目标步骤标识
 */
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
