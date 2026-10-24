<!-- ==== ThemePicker 主题色选择器 ==== -->
<!--
  职责：提供一组预设主题色，点击后写入 appearance store，由 store 统一切换 CSS 变量并持久化。
  复用场景：layout/index.vue 顶栏右侧的调色板图标。
  外部契约：无 props、无 emit；直接读写 useAppearanceStore。
  注意事项：颜色写入 localStorage（appearance_theme_color），刷新后仍生效；
           当前选中项通过 active 类展示描边与对勾，不改变业务逻辑。
  交互细节：
    1. 触发器使用 Brush 图标，与 ThemeToggle、NoticeBell 保持同一视觉规格。
    2. 点击图标打开 popover，面板宽度固定 220px，3 列网格展示 6 个预设色。
    3. 选中后立即生效，无需确认按钮；同一颜色重复点击不会产生副作用。
    4. 颜色切换由 appearance store 的 watch 统一写入 CSS 变量与 localStorage，
       组件本身不直接操作 DOM。
  主题变量：--primary-color 与 --el-color-primary 会同步更新，
            侧边菜单激活色、按钮主色、选中描边均随之变化。
  性能与稳定性：面板内容仅在弹层打开时渲染，颜色列表长度固定为 6，无需虚拟滚动；
                写操作只触发一次 store 更新，避免在点击回调里重复操作 DOM。
  可访问性：触发器是可聚焦的图标元素，悬停提示说明用途；
            选中状态除颜色外还用对勾与描边双重标记，避免仅靠颜色传达信息。
-->
<template>
  <!-- 外层 tooltip 提供悬停说明，内层 popover 承载颜色面板 -->
  <el-tooltip content="主题色" placement="bottom">
    <!-- popover 参数：向下弹出、固定 220px、点击触发；自定义类用于覆盖内边距 -->
    <el-popover
      placement="bottom"
      :width="220"
      trigger="click"
      popper-class="theme-picker-popover"
    >
      <!-- 触发器：调色板图标 -->
      <template #reference>
        <el-icon class="action-item">
          <Brush />
        </el-icon>
      </template>
      <!-- 面板内容：标题 + 3 列颜色网格 -->
      <div class="picker-content">
        <div class="picker-title">选择主题色</div>
        <!-- 预设颜色网格：遍历 store.presetColors，当前色显示对勾 -->
        <div class="color-grid">
          <div
            v-for="color in appearanceStore.presetColors"
            :key="color"
            class="color-item"
            :style="{ background: color }"
            :class="{ active: appearanceStore.themeColor === color }"
            @click="handlePick(color)"
          >
            <!-- 选中态对勾：仅当前主题色显示，起到颜色之外的辅助标识作用 -->
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

// 主题状态来源：预设色板、当前主题色、setThemeColor 均由此提供。
const appearanceStore = useAppearanceStore()

/**
 * 选中某个预设主题色
 * 仅调用 store 的 setThemeColor，变量替换与 localStorage 持久化由 store 内部的 watch 完成。
 */
function handlePick(color: string) {
  appearanceStore.setThemeColor(color)
}
</script>

<style scoped>
/* 顶栏触发器：与主题切换等图标保持统一的尺寸与颜色 */
.action-item {
  font-size: 18px;
  cursor: pointer;
  color: #5a5e66;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* 深色模式下使用更亮的图标颜色，保证对比度 */
:deep(html.dark) .action-item {
  color: #cfd3dc;
}

/* 面板内容内边距：与外层 popover 的 12px 内边距叠加后保持适中留白 */
.picker-content {
  padding: 4px;
}

/* 面板标题：次级文字色，与色块形成层级对比 */
.picker-title {
  font-size: 13px;
  color: var(--text-color-regular, #606266);
  margin-bottom: 12px;
  font-weight: 500;
}

/* 颜色网格：固定 3 列，6 个预设色正好两行 */
.color-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

/* 单个色块：52x52 圆角方块，点击区域充足 */
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

/* 悬停放大并加深阴影，提示色块可点击 */
.color-item:hover {
  transform: scale(1.08);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

/* 选中态：白色内描边 + 主题色外描边，深浅背景下都能看清 */
.color-item.active {
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px var(--primary-color, #409EFF);
}

/* 选中对勾：白色加粗，保证在任意色块上可读 */
.check-icon {
  color: #fff;
  font-size: 22px;
  font-weight: bold;
}
</style>

<style>
/* 非 scoped：需要作用于 popover 挂载到 body 的弹层根节点 */
/* 使用 !important 覆盖 Element Plus 弹层默认内边距，保证 3 列网格四周留白一致 */
.theme-picker-popover {
  padding: 12px !important;
}
</style>
