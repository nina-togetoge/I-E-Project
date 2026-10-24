<!--
  ==== ProjectDetailDialog ====
  职责：项目详情弹窗（自定义窗口样式），以"桌面窗口"形态展示项目详情页，
        支持拖拽移动、右下角拖拽调整大小、最小化、全屏与关闭。
  复用：项目列表、审核工作台、专家评审、成果管理等页面需要"不离开当前列表就查看详情"的场景。
  契约：无 props、无 emit、无插槽；显隐与项目 id 由 Pinia 的 projectDetail store 驱动
        （store.visible / store.projectId / store.close()），因此可在任意页面调用打开。
  注意：1) 窗口打开时内部才会挂载 ProjectDetail，关闭即卸载，避免详情页重复请求；
        2) 拖拽与缩放监听挂在 document 上，卸载时必须清理（见 onBeforeUnmount）；
        3) 拖拽边界：水平至少保留 200px、垂直至少保留 60px 在视口内，防止窗口被拖丢；
        4) 最小化只保留标题栏高度，全屏优先级高于最小化。
-->
<template>
  <transition name="dialog-fade">
    <!-- 区块：遮罩层，点击空白处关闭；点击窗口内部不会冒泡触发关闭 -->
    <div v-if="store.visible" class="pd-mask" @click.self="store.close()">
      <div
        class="pd-window"
        :class="{ 'pd-fullscreen': isFullscreen, 'pd-minimized': isMinimized }"
        :style="windowStyle"
        ref="windowRef"
      >
        <!-- 区块：标题栏，按住可拖拽移动，双击可切换全屏；右侧为窗口控制按钮 -->
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

        <!-- 区块：内容区，仅在 projectId 存在时挂载详情页，实现按需加载 -->
        <div v-show="!isMinimized" class="pd-content" ref="contentRef">
          <ProjectDetail v-if="store.projectId" :project-id="store.projectId" />
        </div>

        <!-- 区块：底部操作栏，最小化时一并隐藏，只保留统一关闭入口 -->
        <div v-show="!isMinimized" class="pd-footer">
          <el-button type="primary" @click="store.close()">关闭</el-button>
        </div>

        <!-- 区块：右下角缩放热区，全屏或最小化时隐藏，避免无意义的拉伸操作 -->
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

// ==================== 依赖与状态 ====================
/**
 * 项目详情弹窗 store：visible 控制显隐、projectId 指定加载哪个项目、close() 统一关闭。
 * 通过 store 而非 props 传递，任何页面都能以编程方式打开详情窗口。
 */
const store = useProjectDetailStore()

/** 窗口根节点引用，预留给需要测量窗口尺寸的扩展逻辑，拖拽不依赖它 */
const windowRef = ref<HTMLElement>()
/** 内容滚动容器引用，当前仅用于绑定 DOM，不参与逻辑计算 */
const contentRef = ref<HTMLElement>()

// ==================== 窗口几何 ====================
/** 窗口宽度（px），缩放时最小 600 */
const width = ref(960)
/** 窗口高度（px），缩放时最小 400 */
const height = ref(680)
/** 窗口左偏移；初始按视口居中，小屏时最少留 20px 边距 */
const left = ref(Math.max(20, (window.innerWidth - 960) / 2))
/** 窗口上偏移；初始按视口居中，小屏时最少留 20px 边距 */
const top = ref(Math.max(20, (window.innerHeight - 680) / 2))

/** 是否全屏：全屏时忽略几何值，窗口铺满视口 */
const isFullscreen = ref(false)
/** 是否最小化：最小化时高度压缩为标题栏高度 */
const isMinimized = ref(false)
/** 进入全屏前的窗口几何快照，退出全屏时还原 */
const prevState = ref({ width: 960, height: 680, left: 0, top: 0 })

/**
 * 根据全屏/最小化状态计算窗口内联样式。
 * 优先级：全屏 > 最小化 > 普通窗口。
 * @returns 绑定到窗口根节点的定位与尺寸样式
 */
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

// ==================== 全屏切换 ====================
/**
 * 切换全屏：进入前记录当前几何，退出时还原；进入全屏会同时取消最小化。
 * 副作用：修改 isFullscreen / isMinimized / width / height / left / top / prevState。
 */
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

// ==================== 最小化切换 ====================
/**
 * 切换最小化：只保留标题栏，内容区与底部栏由 v-show 隐藏；
 * 最小化会退出全屏，避免全屏与最小化状态互相冲突。
 * 副作用：修改 isMinimized / isFullscreen。
 */
function toggleMinimize() {
  isMinimized.value = !isMinimized.value
  if (isMinimized.value) {
    isFullscreen.value = false
  }
}

// ==================== 拖拽移动 ====================
/** 本次拖拽的起点：鼠标坐标 + 当时窗口位置，用差值计算新位置避免累计误差 */
let dragStart = { x: 0, y: 0, left: 0, top: 0 }
/** 是否处于拖拽中，防止松手后的 mousemove 继续移动窗口 */
let dragging = false

/**
 * 标题栏按下：记录起点并注册 document 级移动/抬起监听。
 * @param e 鼠标按下事件
 * 副作用：修改拖拽标记，向 document 注册 onDrag / stopDrag。
 * 说明：监听挂在 document 而非标题栏，鼠标快速移出窗口时仍能跟随。
 */
function startDrag(e: MouseEvent) {
  dragging = true
  dragStart = { x: e.clientX, y: e.clientY, left: left.value, top: top.value }
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
}
/**
 * 拖拽移动：按鼠标位移更新窗口 left/top。
 * @param e 鼠标移动事件
 * 副作用：更新 left / top。
 * 边界：水平至少保留 200px、垂直至少保留 60px 在视口内，防止窗口被拖出屏幕无法找回。
 */
function onDrag(e: MouseEvent) {
  if (!dragging) return
  left.value = Math.max(0, Math.min(window.innerWidth - 200, dragStart.left + e.clientX - dragStart.x))
  top.value = Math.max(0, Math.min(window.innerHeight - 60, dragStart.top + e.clientY - dragStart.y))
}
/**
 * 结束拖拽：清除标记并注销 document 监听。
 * 副作用：修改 dragging，移除 onDrag / stopDrag。
 */
function stopDrag() {
  dragging = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

// ==================== 拖拽调整大小 ====================
/** 本次缩放的起点：鼠标坐标 + 当时窗口宽高 */
let resizeStart = { x: 0, y: 0, w: 0, h: 0 }
/** 是否处于缩放中 */
let resizing = false

/**
 * 右下角手柄按下：记录起点并注册 document 级监听。
 * @param e 鼠标按下事件
 * 副作用：修改缩放标记，向 document 注册 onResize / stopResize。
 */
function startResize(e: MouseEvent) {
  resizing = true
  resizeStart = { x: e.clientX, y: e.clientY, w: width.value, h: height.value }
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
}
/**
 * 缩放中：按鼠标位移计算新宽高并夹取边界。
 * @param e 鼠标移动事件
 * 副作用：更新 width / height。
 * 边界：最小 600x400；最大不超过视口中剩余空间（减去窗口左上偏移）。
 */
function onResize(e: MouseEvent) {
  if (!resizing) return
  width.value = Math.max(600, Math.min(window.innerWidth - left.value, resizeStart.w + e.clientX - resizeStart.x))
  height.value = Math.max(400, Math.min(window.innerHeight - top.value, resizeStart.h + e.clientY - resizeStart.y))
}
/**
 * 结束缩放：清除标记并注销 document 监听。
 * 副作用：修改 resizing，移除 onResize / stopResize。
 */
function stopResize() {
  resizing = false
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
}

// ==================== 生命周期 ====================
/**
 * 卸载时兜底清理四个 document 监听。
 * 正常流程中 mouseup 已清理，此处覆盖"拖拽过程中窗口被强制关闭/路由跳转"的异常场景，
 * 避免监听残留造成内存泄漏与卸载后操作已销毁的响应式状态。
 */
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

/* 标题栏：整条可拖拽，禁止文字选中避免拖动时误选标题 */
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

/* 缩放热区：右下角 16px 斜纹角标，光标提示可对角线拖拽 */
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
