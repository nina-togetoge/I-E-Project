<!--
  项目阶段页面公共壳（StagePageShell）
  面向角色：中期检查、结项验收、项目成果（旧路由）三页的所有访问者。
  核心功能：统一页头（标题 + 状态标签 + 自定义操作 + 项目切换）、阶段步骤条与内容区，
           避免三个后期页面各写一套布局，导致标题、间距、切换器行为不一致。
  调用 API：本组件不直接请求；ProjectSwitcher 内部会拉取项目列表，
           页面数据由使用方的默认插槽内容自行加载。
  关键约束：
    1. project 为空时只保留 loading 容器，不渲染页头与插槽，防止异步加载期出现半截页面；
    2. 状态标签文案与颜色由使用方传入，壳层不解释业务状态码；
    3. header-actions 中自定义操作排在项目切换器之前，保持操作优先、切换其次的视觉顺序。
  特别注意：组件只有插槽没有事件，所有交互（提交、审核、导出）都由页面自身实现。
-->
<template>
  <!-- loading 由使用方传入，覆盖整个页面，避免加载时局部内容先闪现再消失 -->
  <div class="page-container" v-loading="loading">
    <!-- 项目未加载完成时不渲染主体，既避免空标题，也避免步骤条误判状态 -->
    <template v-if="project">
      <!-- 页头：左侧标题与状态/副标题，右侧自定义操作与项目切换 -->
      <div class="page-header">
        <div class="header-row">
          <div>
            <h2 class="page-title">{{ title }}</h2>
            <!-- 副标题区：状态标签与 subtitle 插槽同时存在时并排展示 -->
            <div v-if="statusText || $slots.subtitle" class="page-subtitle">
              <el-tag v-if="statusText" :type="statusType" size="small">{{ statusText }}</el-tag>
              <slot name="subtitle" />
            </div>
          </div>
          <div class="header-actions">
            <!-- 页面自定义操作区，例如返回列表、刷新、导出等 -->
            <slot name="actions" />
            <!-- 项目切换器：suffix 决定可切换项目的状态范围，切换后跳转到对应阶段页 -->
            <ProjectSwitcher :current-id="Number(project.id)" :suffix="current" />
          </div>
        </div>
      </div>

      <!-- 三阶段步骤条：用于展示进度并支持横向跳转 -->
      <ProjectStageSteps :project="project" :current="current" />

      <!-- 页面正文：由使用方提供表单、报告、成果面板等 -->
      <slot />
    </template>
  </div>
</template>

<script setup lang="ts">
import ProjectSwitcher from '@/components/ProjectSwitcher.vue'
import ProjectStageSteps from '@/components/ProjectStageSteps.vue'

// ==================== Props ====================

withDefaults(defineProps<{
  /** 当前项目对象；为空时整个主体不渲染 */
  project: any
  /** 页面标题，例如「中期检查」 */
  title: string
  /** 当前阶段标识，同时用于步骤条高亮与项目切换器的状态过滤 */
  current: 'midterm' | 'achievements' | 'final'
  /** 页头状态标签文案，不传则不显示标签 */
  statusText?: string
  /** 状态标签颜色，默认灰色 info，避免无意义的高亮 */
  statusType?: 'primary' | 'success' | 'info' | 'warning' | 'danger'
  /** 页面级加载态，默认 false */
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
