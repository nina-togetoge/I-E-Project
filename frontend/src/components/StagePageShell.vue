<!--
  项目阶段页面公共壳
  统一页头（标题 + 状态标签 + 项目切换）、阶段步骤条与页面内容区，
  供中期检查 / 结项验收 / 项目成果（旧路由）复用。
-->
<template>
  <div class="page-container" v-loading="loading">
    <template v-if="project">
      <div class="page-header">
        <div class="header-row">
          <div>
            <h2 class="page-title">{{ title }}</h2>
            <div v-if="statusText || $slots.subtitle" class="page-subtitle">
              <el-tag v-if="statusText" :type="statusType" size="small">{{ statusText }}</el-tag>
              <slot name="subtitle" />
            </div>
          </div>
          <div class="header-actions">
            <slot name="actions" />
            <ProjectSwitcher :current-id="Number(project.id)" :suffix="current" />
          </div>
        </div>
      </div>

      <ProjectStageSteps :project="project" :current="current" />

      <slot />
    </template>
  </div>
</template>

<script setup lang="ts">
import ProjectSwitcher from '@/components/ProjectSwitcher.vue'
import ProjectStageSteps from '@/components/ProjectStageSteps.vue'

withDefaults(defineProps<{
  project: any
  title: string
  current: 'midterm' | 'achievements' | 'final'
  statusText?: string
  statusType?: 'primary' | 'success' | 'info' | 'warning' | 'danger'
  loading?: boolean
}>(), {
  statusText: '',
  statusType: 'info',
  loading: false,
})
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  white-space: nowrap;
}
.page-subtitle {
  color: #909399;
  font-size: 13px;
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
