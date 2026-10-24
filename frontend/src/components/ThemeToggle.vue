<!-- ==== ThemeToggle 明暗主题切换 ==== -->
<!--
  职责：在浅色/深色模式之间一键切换，图标与 tooltip 文案随当前模式变化。
  复用场景：layout/index.vue 顶栏右侧。
  外部契约：无 props、无 emit；直接调用 useAppearanceStore.toggleDark。
  注意事项：切换会修改 html 的 dark 类，并由 store 写入 localStorage（appearance_is_dark）；
            首次渲染时 store 已根据本地存储恢复状态，无需组件额外处理。
  图标语义：月亮表示"可切换到深色"，太阳表示"可切换到浅色"，与提示文案保持一致。
  样式说明：图标颜色在深色模式下自动变亮，保证在深色顶栏上的可见性。
-->
<template>
  <!-- 提示文案取反：当前为深色则提示切到浅色，反之提示切到深色 -->
  <el-tooltip :content="appearanceStore.isDark ? '切换到浅色模式' : '切换到深色模式'" placement="bottom">
    <!-- 点击触发 store 切换；未开启深色显示月亮，已开启显示太阳 -->
    <el-icon class="action-item" @click="appearanceStore.toggleDark()">
      <Moon v-if="!appearanceStore.isDark" />
      <Sunny v-else />
    </el-icon>
  </el-tooltip>
</template>

<script setup lang="ts">
import { Moon, Sunny } from '@element-plus/icons-vue'
import { useAppearanceStore } from '@/store/appearance'

// 主题状态来源：isDark 驱动图标显示，toggleDark 负责切换与持久化。
const appearanceStore = useAppearanceStore()
</script>

<style scoped>
/* 顶栏动作图标：固定 18px，便于与其它图标对齐 */
.action-item {
  font-size: 18px;
  cursor: pointer;
  color: #5a5e66;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* 深色模式下的图标颜色，避免在深色背景上对比度不足 */
:deep(html.dark) .action-item {
  color: #cfd3dc;
}
</style>
