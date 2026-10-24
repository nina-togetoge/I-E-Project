<!--
  页面名称：项目成果（旧路由 /projects/:id/achievements，保留兼容）
  面向角色：项目负责人、指导教师、学院 / 超管（具体操作权限由 AchievementPanel 判定）
  核心功能：仅作为 StagePageShell + AchievementPanel 的薄壳，
           负责加载项目详情、同步侧边栏阶段，成果的增删改与认定全部由面板完成。
  调用 API：getProjectDetail（本页唯一请求）。
  权限 / 状态约束：
    - 通知与流程步骤条仍会跳转到此地址，因此路由不能删除；
    - 主入口已合并到「结项验收」页的成果登记 Tab，本页只做兼容展示；
    - 成果登记 / 认定 / 删除的角色与状态限制见 AchievementPanel。
  关键交互：项目加载完成后才渲染面板，避免面板内部拿到空 project 做权限判断。
-->
<template>
  <StagePageShell :project="project" title="项目成果" current="achievements" :loading="loading">
    <!-- 面板需要完整的 project 才能判断阶段与角色，故加载完成后再渲染 -->
    <AchievementPanel v-if="project" :project="project" />
  </StagePageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getProjectDetail } from '@/api/project'
import StagePageShell from '@/components/StagePageShell.vue'
import AchievementPanel from '@/components/AchievementPanel.vue'
import { useProcessStore } from '@/store/process'

// ==================== 路由 / Store / 项目标识 ====================
// 旧路由只负责把项目壳数据交给成果面板，store 用于同步侧边栏的阶段状态。
const route = useRoute()
const processStore = useProcessStore()
const pid = computed(() => Number(route.params.id))

/** 项目详情：面板据此判断能否登记、认定或删除成果 */
const project = ref<any>(null)
/** 页面加载态 */
const loading = ref(true)

/**
 * 加载项目详情并同步主侧边栏「过程管理」状态。
 * 失败处理：提示「加载失败」，保持空 project，面板不渲染。
 */
async function loadData() {
  loading.value = true
  try {
    const res = await getProjectDetail(pid.value)
    project.value = res.data
    processStore.setStatus(res.data.status)
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

// 进入即加载；离开时清理侧边栏阶段，避免影响其他项目页面
onMounted(() => loadData())
onBeforeUnmount(() => processStore.reset())
</script>
