<!--
  项目详情弹窗（自定义窗口样式）
  支持：拖拽移动、拖拽调整大小、最小化、全屏、关闭
-->
<template>
  <transition name="dialog-fade">
    <div v-if="store.visible" class="pd-mask" @click.self="store.close()">
      <div
        class="pd-window"
        :class="{ 'pd-fullscreen': isFullscreen, 'pd-minimized': isMinimized }"
        :style="windowStyle"
        ref="windowRef"
      >
        <!-- 标题栏 -->
        <div class="pd-titlebar" @mousedown="startDrag" @dblclick="toggleFullscreen">
          <div class="pd-title">
            <el-icon><Document /></el-icon>
            <span>项目详情</span>
          </div>
          <div class="pd-controls">
            <el-icon class="pd-ctrl pd-minimize" @click.stop="toggleMinimize" :title="isMinimized ? '还原' : '最小化'">
              <Minus v-if="!isMinimized" />
              <CopyDocument v-else />
            </el-icon>
            <el-icon class="pd-ctrl pd-fullscreen" @click.stop="toggleFullscreen" :title="isFullscreen ? '退出全屏' : '全屏'">
              <FullScreen v-if="!isFullscreen" />
              <Aim v-else />
            </el-icon>
            <el-icon class="pd-ctrl pd-close" @click.stop="store.close()" title="关闭">
              <Close />
            </el-icon>
          </div>
        </div>

        <!-- 内容区 -->
        <div v-show="!isMinimized" class="pd-content" ref="contentRef">
          <ProjectDetail v-if="store.projectId" :project-id="store.projectId" />
        </div>

        <!-- 底部操作栏 -->
        <div v-show="!isMinimized" class="pd-footer">
          <el-button type="primary" @click="store.close()">关闭</el-button>
        </div>

        <!-- 右下角拖拽调整大小手柄 -->
        <div v-show="!isFullscreen && !isMinimized" class="pd-resize-handle" @mousedown.stop="startResize"></div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { Document, Close, FullScreen, Aim, Minus, CopyDocument } from '@element-plus/icons-vue'
import ProjectDetail from '@/views/project/ProjectDetail.vue'
import { useProjectDetailStore } from '@/store/projectDetail'

const store = useProjectDetailStore()

const windowRef = ref<HTMLElement>()
const contentRef = ref<HTMLElement>()

const width = ref(960)
const height = ref(680)
const left = ref(Math.max(20, (window.innerWidth - 960) / 2))
const top = ref(Math.max(20, (window.innerHeight - 680) / 2))

const isFullscreen = ref(false)
const isMinimized = ref(false)
const prevState = ref({ width: 960, height: 680, left: 0, top: 0 })

const windowStyle = computed(() => {
  if (isFullscreen.value) {
    return { left: '0px', top: '0px', width: '100vw', height: '100vh', borderRadius: '0' }
  }
  if (isMinimized.value) {
    return { left: `${left.value}px`, top: `${top.value}px`, width: `${width.value}px`, height: '42px' }
  }
  return {
    left: `${left.value}px`,
    top: `${top.value}px`,
    width: `${width.value}px`,
    height: `${height.value}px`,
  }
})

/* ---------- 全屏切换 ---------- */
function toggleFullscreen() {
  if (isFullscreen.value) {
    isFullscreen.value = false
    width.value = prevState.value.width
    height.value = prevState.value.height
    left.value = prevState.value.left
    top.value = prevState.value.top
  } else {
    prevState.value = { width: width.value, height: height.value, left: left.value, top: top.value }
    isFullscreen.value = true
    isMinimized.value = false
  }
}

/* ---------- 最小化切换 ---------- */
function toggleMinimize() {
  isMinimized.value = !isMinimized.value
  if (isMinimized.value) {
    isFullscreen.value = false
  }
}

/* ---------- 拖拽移动 ---------- */
let dragStart = { x: 0, y: 0, left: 0, top: 0 }
let dragging = false

function startDrag(e: MouseEvent) {
  dragging = true
  dragStart = { x: e.clientX, y: e.clientY, left: left.value, top: top.value }
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
}
function onDrag(e: MouseEvent) {
  if (!dragging) return
  left.value = Math.max(0, Math.min(window.innerWidth - 200, dragStart.left + e.clientX - dragStart.x))
  top.value = Math.max(0, Math.min(window.innerHeight - 60, dragStart.top + e.clientY - dragStart.y))
}
function stopDrag() {
  dragging = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

/* ---------- 拖拽调整大小 ---------- */
let resizeStart = { x: 0, y: 0, w: 0, h: 0 }
let resizing = false

function startResize(e: MouseEvent) {
  resizing = true
  resizeStart = { x: e.clientX, y: e.clientY, w: width.value, h: height.value }
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
}
function onResize(e: MouseEvent) {
  if (!resizing) return
  width.value = Math.max(600, Math.min(window.innerWidth - left.value, resizeStart.w + e.clientX - resizeStart.x))
  height.value = Math.max(400, Math.min(window.innerHeight - top.value, resizeStart.h + e.clientY - resizeStart.y))
}
function stopResize() {
  resizing = false
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
})
</script>

<style scoped>
.pd-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 3000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
}

.pd-window {
  position: absolute;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 600px;
  min-height: 400px;
}
.pd-window.pd-minimized {
  min-height: 42px;
  border-radius: 8px;
}
.pd-window.pd-fullscreen {
  border-radius: 0;
}

/* 标题栏 */
.pd-titlebar {
  height: 42px;
  background: #409eff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px 0 16px;
  cursor: move;
  user-select: none;
  flex-shrink: 0;
}
.pd-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}
.pd-title .el-icon {
  font-size: 16px;
}
.pd-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}
.pd-ctrl {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  cursor: pointer;
  opacity: 0.85;
  font-size: 16px;
  transition: all 0.15s;
}
.pd-ctrl:hover {
  background: rgba(255, 255, 255, 0.2);
  opacity: 1;
}
.pd-close:hover {
  background: #f56c6c !important;
}

/* 内容区 */
.pd-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background: #f5f7fa;
}
.pd-content::-webkit-scrollbar {
  width: 8px;
}
.pd-content::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 4px;
}
.pd-content::-webkit-scrollbar-track {
  background: #f5f7fa;
}

/* 底部操作栏 */
.pd-footer {
  flex-shrink: 0;
  padding: 12px 20px;
  background: #fff;
  border-top: 1px solid #ebeef5;
  text-align: right;
}

/* 拖拽调整大小手柄 */
.pd-resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 50%, #c0c4cc 50%, #c0c4cc 60%, transparent 60%, transparent 70%, #c0c4cc 70%, #c0c4cc 80%, transparent 80%);
  z-index: 10;
}

/* 动画 */
.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}
.dialog-fade-enter-active .pd-window,
.dialog-fade-leave-active .pd-window {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}
.dialog-fade-enter-from .pd-window,
.dialog-fade-leave-to .pd-window {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}
</style>
