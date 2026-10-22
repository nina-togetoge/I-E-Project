<!--
  审核工作台（教师 / 管理员端）
  将「待审核列表」「变更申请审批」合并为同一页面，用 Tab 分类切换
-->
<template>
  <div class="review-center">
    <el-tabs v-model="activeTab" class="review-tabs">
      <el-tab-pane label="待审核列表" name="pending" lazy>
        <ReviewPending />
      </el-tab-pane>
      <el-tab-pane label="变更申请审批" name="changes" lazy>
        <ChangeApproval />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import ReviewPending from '@/views/review/ReviewPending.vue'
import ChangeApproval from '@/views/review/ChangeApproval.vue'

const route = useRoute()
const activeTab = ref(route.query.tab === 'changes' ? 'changes' : 'pending')

watch(
  () => route.query.tab,
  (tab) => {
    activeTab.value = tab === 'changes' ? 'changes' : 'pending'
  },
)
</script>

<style scoped>
.review-center {
  min-height: 100%;
}
/* 嵌入的子页面自带 page-container 内边距，这里去掉一层，避免 Tab 内容区过度留白 */
.review-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.review-tabs :deep(.el-tabs__content) {
  padding: 16px 0;
}
.review-tabs :deep(.page-container) {
  padding: 0;
}
</style>