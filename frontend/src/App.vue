<template>
  <div class="app-wrapper" :class="{ 'app-dark': isDark }">
    <div v-if="isOnline === false" class="offline-tip">
      ⚠️ 网络已断开，部分功能不可用
    </div>
    <PageSkeleton v-if="showLoading" />
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

const router = useRouter()
const appearanceStore = useAppearanceStore()

const isDark = computed(() => appearanceStore.isDark)
const isOnline = ref(typeof navigator !== 'undefined' ? navigator.onLine : true)

const loading = ref(false)
const showLoading = ref(false)
let loadingTimer: number | null = null

function handleOnline() {
  isOnline.value = true
}
function handleOffline() {
  isOnline.value = false
}

onMounted(() => {
  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)

  const manifestLink = document.createElement('link')
  manifestLink.rel = 'manifest'
  manifestLink.href = '/manifest.json'
  document.head.appendChild(manifestLink)

  const preconnectLink = document.createElement('link')
  preconnectLink.rel = 'preconnect'
  preconnectLink.href = '/'
  preconnectLink.crossOrigin = 'anonymous'
  document.head.insertBefore(preconnectLink, document.head.firstChild)

  const dnsPrefetchLink = document.createElement('link')
  dnsPrefetchLink.rel = 'dns-prefetch'
  dnsPrefetchLink.href = '/api'
  document.head.insertBefore(dnsPrefetchLink, document.head.firstChild)
})

onBeforeUnmount(() => {
  window.removeEventListener('online', handleOnline)
  window.removeEventListener('offline', handleOffline)
})

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

router.afterEach(() => {
  loading.value = false
  if (loadingTimer) {
    clearTimeout(loadingTimer)
    loadingTimer = null
  }
  showLoading.value = false
})

watch(isDark, (val) => {
  if (val) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}, { immediate: true })
</script>

<style>
.app-wrapper {
  width: 100%;
  min-height: 100vh;
  background: var(--bg-color, #f0f2f5);
  color: var(--text-color, #303133);
  transition: background 0.3s ease, color 0.3s ease;
}

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

@font-face {
  font-family: 'Helvetica Neue';
  font-display: swap;
  src: local('Helvetica Neue'), local('Arial');
}
</style>
