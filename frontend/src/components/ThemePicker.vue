<template>
  <el-tooltip content="主题色" placement="bottom">
    <el-popover
      placement="bottom"
      :width="220"
      trigger="click"
      popper-class="theme-picker-popover"
    >
      <template #reference>
        <el-icon class="action-item">
          <Brush />
        </el-icon>
      </template>
      <div class="picker-content">
        <div class="picker-title">选择主题色</div>
        <div class="color-grid">
          <div
            v-for="color in appearanceStore.presetColors"
            :key="color"
            class="color-item"
            :style="{ background: color }"
            :class="{ active: appearanceStore.themeColor === color }"
            @click="handlePick(color)"
          >
            <el-icon v-if="appearanceStore.themeColor === color" class="check-icon">
              <Check />
            </el-icon>
          </div>
        </div>
      </div>
    </el-popover>
  </el-tooltip>
</template>

<script setup lang="ts">
import { Brush, Check } from '@element-plus/icons-vue'
import { useAppearanceStore } from '@/store/appearance'

const appearanceStore = useAppearanceStore()

function handlePick(color: string) {
  appearanceStore.setThemeColor(color)
}
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

.picker-content {
  padding: 4px;
}

.picker-title {
  font-size: 13px;
  color: var(--text-color-regular, #606266);
  margin-bottom: 12px;
  font-weight: 500;
}

.color-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.color-item {
  width: 52px;
  height: 52px;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
  position: relative;
}

.color-item:hover {
  transform: scale(1.08);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.color-item.active {
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px var(--primary-color, #409EFF);
}

.check-icon {
  color: #fff;
  font-size: 22px;
  font-weight: bold;
}
</style>

<style>
.theme-picker-popover {
  padding: 12px !important;
}
</style>
