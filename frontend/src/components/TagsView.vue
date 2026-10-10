<template>
  <div class="tags-view">
    <div class="tags-wrapper">
      <el-tag
        v-for="view in tagsStore.visitedViews"
        :key="view.path"
        :closable="!view.affix"
        :type="route.path === view.path ? 'primary' : 'info'"
        :effect="route.path === view.path ? 'dark' : 'plain'"
        class="tag-item"
        @click="router.push(view.path)"
        @close="handleClose(view.path)"
      >
        <el-icon v-if="view.icon" class="tag-icon">
          <component :is="view.icon" />
        </el-icon>
        <span>{{ view.title }}</span>
      </el-tag>
    </div>
    <div class="tags-actions">
      <el-dropdown trigger="click" @command="handleCommand">
        <el-button size="small" plain>
          <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="others">关闭其他</el-dropdown-item>
            <el-dropdown-item command="all">关闭全部</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { useTagsStore } from '@/store/tags'

const route = useRoute()
const router = useRouter()
const tagsStore = useTagsStore()

function handleClose(path: string) {
  const isActive = route.path === path
  tagsStore.removeView(path)
  if (isActive && tagsStore.visitedViews.length > 0) {
    const last = tagsStore.visitedViews[tagsStore.visitedViews.length - 1]
    router.push(last.path)
  }
}

function handleCommand(cmd: string) {
  if (cmd === 'others') {
    tagsStore.removeOthers(route.path)
  } else if (cmd === 'all') {
    tagsStore.removeAll()
    if (tagsStore.visitedViews.length > 0) {
      router.push(tagsStore.visitedViews[0].path)
    }
  }
}
</script>

<style scoped>
.tags-view {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--header-color, #fff);
  border-bottom: 1px solid var(--border-color-light, #ebeef5);
  transition: background 0.3s ease, border-color 0.3s ease;
}

.tags-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  overflow-x: auto;
  padding-right: 8px;
  max-height: 40px;
}

.tag-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  flex-shrink: 0;
  margin-right: 0;
}

.tag-item :deep(.el-tag__content) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.tag-icon {
  font-size: 13px;
  line-height: 1;
}

.tags-actions {
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .tags-view {
    padding: 6px 12px;
  }
  .tag-item .el-tag__content span {
    max-width: 60px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
