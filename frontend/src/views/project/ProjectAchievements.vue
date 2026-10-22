<!--
  项目成果（旧路由 /projects/:id/achievements 保留）
  通知与步骤条仍会跳转到此地址，页面仅为 StagePageShell + AchievementPanel 的薄壳；
  主入口已合并到「结项验收」页的成果登记 Tab。
-->
<template>
  <StagePageShell :project="project" title="项目成果" current="achievements" :loading="loading">
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

const route = useRoute()
const processStore = useProcessStore()
const pid = computed(() => Number(route.params.id))

const project = ref<any>(null)
const loading = ref(true)

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

onMounted(() => loadData())
onBeforeUnmount(() => processStore.reset())
</script>
