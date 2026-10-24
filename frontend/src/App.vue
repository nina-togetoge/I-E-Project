<!-- ==== App 应用根组件 ==== -->
<!--
  职责：应用最外层壳，负责全局路由出口、加载骨架屏、错误边界、网络离线提示与深色模式类名。
  渲染顺序：离线提示（固定顶部）→ 路由加载骨架 → ErrorBoundary 包裹的 router-view。
  复用场景：仅 main.ts 挂载一次，不作为业务组件复用。
  注意事项：
    1. 骨架屏由路由 beforeEach/afterEach 控制：切换超过 300ms 才展示，避免短跳转闪烁。
    2. ErrorBoundary 只包裹 router-view，保证业务页面异常不会拖垮整个应用外壳。
    3. 深色模式通过 watch 立即同步 html.dark，与 appearance store 的持久化状态保持一致。
  状态优先级：离线提示 > 骨架屏 > 正常页面；三者互斥展示，避免视觉叠加。
  副作用清单：
    - 全局 router.beforeEach / afterEach（加载态）；
    - window online/offline 事件监听；
    - 动态向 head 注入 manifest、preconnect、dns-prefetch（仅挂载时执行一次）。
-->
<template>
  <!-- 根节点：app-dark 类供局部样式判断深色模式；具体颜色仍以 html.dark 下的变量为准 -->
  <div class="app-wrapper" :class="{ 'app-dark': isDark }">
    <!-- 离线提示：仅浏览器上报 offline 时展示，恢复后自动隐藏 -->
    <div v-if="isOnline === false" class="offline-tip">
      ⚠️ 网络已断开，部分功能不可用
    </div>
    <!-- 路由切换骨架屏：延迟 300ms 出现，加载完成后立即消失 -->
    <PageSkeleton v-if="showLoading" />
    <!-- 正常渲染：错误边界包裹路由出口，捕获页面级运行时错误 -->
    <ErrorBoundary v-else>
      <router-view />
    </ErrorBoundary>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import PageSkeleton from '@/components/PageSkeleton.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { useAppearanceStore } from '@/store/appearance'

// ==================== 全局依赖 ====================
// router 用于注册全局加载态守卫；其自身已在 main.ts 注册，这里只取实例。
const router = useRouter()
// 外观状态：提供 isDark，后续 watch 会把它同步到 documentElement。
const appearanceStore = useAppearanceStore()

// 深色模式：直接映射 store 状态，供根节点类名与 watch 使用。
const isDark = computed(() => appearanceStore.isDark)
// 网络状态：SSR 环境下 navigator 不存在时默认在线，避免误报离线。
const isOnline = ref(typeof navigator !== 'undefined' ? navigator.onLine : true)

// ==================== 路由加载状态 ====================
// loading 表示"路由正在切换"，showLoading 表示"骨架屏实际可见"；
// 两者分离是为了实现 300ms 延迟展示，避免快速切换时骨架屏闪烁。
const loading = ref(false)
const showLoading = ref(false)
let loadingTimer: number | null = null

// ==================== 网络状态监听 ====================
// 浏览器恢复联网：隐藏顶部提示条；业务请求的失败重试由各页面自行决定。
function handleOnline() {
  isOnline.value = true
}
// 浏览器断网：展示顶部提示条；已渲染的页面仍可浏览缓存中的数据。
function handleOffline() {
  isOnline.value = false
}

// 挂载阶段：注册网络事件监听，并补齐 PWA/性能相关的 head 资源
onMounted(() => {
  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)

  // PWA manifest：使浏览器可安装应用并读取图标配置
  const manifestLink = document.createElement('link')
  manifestLink.rel = 'manifest'
  manifestLink.href = '/manifest.json'
  document.head.appendChild(manifestLink)

  // 预连接当前站点源：提前完成 DNS/TCP/TLS，缩短首个静态资源请求耗时
  const preconnectLink = document.createElement('link')
  preconnectLink.rel = 'preconnect'
  preconnectLink.href = '/'
  preconnectLink.crossOrigin = 'anonymous'
  document.head.insertBefore(preconnectLink, document.head.firstChild)

  // 接口域名 DNS 预解析：减少后续 API 请求的解析延迟
  const dnsPrefetchLink = document.createElement('link')
  dnsPrefetchLink.rel = 'dns-prefetch'
  dnsPrefetchLink.href = '/api'
  document.head.insertBefore(dnsPrefetchLink, document.head.firstChild)
})

// 卸载时移除网络监听，防止根组件销毁后仍持有回调引用
onBeforeUnmount(() => {
  window.removeEventListener('online', handleOnline)
  window.removeEventListener('offline', handleOffline)
})

// ==================== 路由加载骨架控制 ====================
// 进入路由：标记加载中；300ms 后仍未完成才真正展示骨架屏，短切换不闪屏。
router.beforeEach(() => {
  loading.value = true
  if (loadingTimer) {
    clearTimeout(loadingTimer)
  }
  loadingTimer = window.setTimeout(() => {
    if (loading.value) {
      showLoading.value = true
    }
  }, 300)
})
// 说明：beforeEach 不清除上一次的 showLoading，若连续快速跳转，
// afterEach 会统一复位，保证不会出现骨架屏残留。

// 离开路由：清理定时器并立即隐藏骨架屏，同时复位加载标记。
router.afterEach(() => {
  loading.value = false
  if (loadingTimer) {
    clearTimeout(loadingTimer)
    loadingTimer = null
  }
  showLoading.value = false
})

// ==================== 深色模式同步 ====================
// 将 store 的 isDark 同步到 html.dark，确保 Element Plus 与自定义主题变量同时生效。
// immediate: true 保证首帧即应用，不会出现先浅色后深色的闪烁。
watch(isDark, (val) => {
  if (val) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}, { immediate: true })
</script>

<style>
/* 应用根容器：撑满视口，背景与文字色跟随主题变量平滑过渡 */
.app-wrapper {
  width: 100%;
  min-height: 100vh;
  background: var(--bg-color, #f0f2f5);
  color: var(--text-color, #303133);
  transition: background 0.3s ease, color 0.3s ease;
}

/* 离线提示条：固定顶部并提高层级，避免被页面内容遮挡 */
.offline-tip {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  background: #fdf6ec;
  color: #e6a23c;
  text-align: center;
  padding: 8px 16px;
  font-size: 14px;
  border-bottom: 1px solid #faecd8;
  box-shadow: 0 2px 8px rgba(230, 162, 60, 0.15);
}

/* 字体声明：优先使用系统已安装的 Helvetica Neue / Arial，避免额外网络请求 */
@font-face {
  font-family: 'Helvetica Neue';
  font-display: swap;
  src: local('Helvetica Neue'), local('Arial');
}
</style>
