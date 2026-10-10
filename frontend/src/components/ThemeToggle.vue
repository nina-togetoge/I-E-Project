<template>
  <el-tooltip :content="appearanceStore.isDark ? '切换到浅色模式' : '切换到深色模式'" placement="bottom">
    <el-icon class="action-item" @click="appearanceStore.toggleDark()">
      <Moon v-if="!appearanceStore.isDark" />
      <Sunny v-else />
    </el-icon>
  </el-tooltip>
</template>

<script setup lang="ts">
import { Moon, Sunny } from '@element-plus/icons-vue'
import { useAppearanceStore } from '@/store/appearance'

const appearanceStore = useAppearanceStore()
</script>

<style scoped>
.action-item {
  font-size: 18px;
  cursor: pointer;
  color: #5a5e66;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

:deep(html.dark) .action-item {
  color: #cfd3dc;
}
</style>
