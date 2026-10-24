<!--
  ==== 审核工作台 ====
  解决的问题：教师 / 管理员日常审核入口分散，这里把「待审核列表」与「变更申请审批」
    收敛到同一个页面，用 Tab 切换，避免多级菜单来回跳转。
  对应角色与路由：role=2(教师)、role=4(管理员，含超管与学院管理员)，路由 /review，
    子 Tab 分别对应隐藏路由 /review/pending 与 /review/changes。
  依赖 API：本页不直接发请求，由两个子组件分别调用 getReviewList、getChangeList、
    approveChangeRequest、rejectChangeRequest 等接口。
  关键交互流程：菜单进入默认停在「待审核列表」；可通过 URL query.tab=changes 深链到变更审批；
    两个 Tab 均使用 lazy，首次激活时才挂载子组件，减少一次性请求。
-->
<template>
  <div class="review-center">
    <!-- 区块：审核业务分类切换，pending=待审核项目，changes=变更/延期申请审批 -->
    <el-tabs v-model="activeTab" class="review-tabs">
      <!-- 待审核列表：按当前登录角色（教师/学院管理员/超管）自动展示对应阶段的待办项目 -->
      <el-tab-pane label="待审核列表" name="pending" lazy>
        <ReviewPending />
      </el-tab-pane>
      <!-- 变更申请审批：审批负责人提交的变更/延期申请，通过后项目按提交阶段回退重审 -->
      <el-tab-pane label="变更申请审批" name="changes" lazy>
        <ChangeApproval />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
// ==================== 导入 ====================
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import ReviewPending from '@/views/review/ReviewPending.vue'
import ChangeApproval from '@/views/review/ChangeApproval.vue'

// ==================== 路由与 Tab 状态 ====================
/**
 * 当前激活的 Tab：pending=待审核列表（默认），changes=变更申请审批。
 * 初值取 URL query.tab，使得从通知、面包屑或外部链接可以直接定位到指定 Tab。
 */
const route = useRoute()
const activeTab = ref(route.query.tab === 'changes' ? 'changes' : 'pending')

// ==================== 路由联动 ====================
/**
 * 监听 URL 中 tab 参数的变化。
 * 目的：当用户在同一个 /review 路由下由代码改写 query 时，页面 Tab 需要同步切换，
 * 避免出现「地址变了但内容没变」的不一致状态。
 */
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