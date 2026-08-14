<!--
  主布局框架
  侧边栏 + 顶栏 + 标签页 + 内容区
-->
<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '210px'" class="sidebar">
      <div class="logo">
        <el-icon size="28"><Promotion /></el-icon>
        <span v-if="!isCollapse" class="logo-text">创新创业平台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        :collapse-transition="false"
        background-color="#001529"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
        router
      >
        <template v-for="route in filteredRoutes" :key="route.path">
          <el-menu-item
            v-if="!route.meta?.hidden"
            :index="resolvePath(route)"
          >
            <el-icon v-if="route.meta?.icon">
              <component :is="route.meta.icon" />
            </el-icon>
            <template #title>{{ route.meta?.title }}</template>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶栏 -->
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="isCollapse = !isCollapse">
            <Fold v-if="!isCollapse" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentRoute.meta?.title">
              {{ currentRoute.meta.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tooltip content="全屏" placement="bottom">
            <el-icon class="action-item" @click="toggleFullscreen">
              <FullScreen />
            </el-icon>
          </el-tooltip>
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="32" :src="userStore.userInfo?.avatar || undefined">
                {{ userStore.userInfo?.real_name?.[0] || 'U' }}
              </el-avatar>
              <span class="user-name">{{ userStore.userInfo?.real_name }}</span>
              <el-tag size="small" type="info">{{ userStore.roleName }}</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile" :icon="User">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  Fold, Expand, FullScreen, Promotion, User, SwitchButton
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { ROLES } from '@/api/types'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const isCollapse = ref(false)
const currentRoute = computed(() => route)

/** 当前激活菜单 */
const activeMenu = computed(() => route.path)

/** 根据角色过滤路由 */
const filteredRoutes = computed(() => {
  const children = router.options.routes.find((r) => r.path === '/')?.children || []
  return children.filter((child) => {
    const roles = child.meta?.roles as number[] | undefined
    if (!roles) return true
    return roles.includes(userStore.role)
  })
})

function resolvePath(route: any): string {
  const base = '/'
  const path = route.path.startsWith('/') ? route.path.slice(1) : route.path
  return base + path
}

function handleCommand(command: string) {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      type: 'warning',
    }).then(() => {
      userStore.logout()
      router.push('/login')
    }).catch(() => {})
  }
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
}

.sidebar {
  background-color: #001529;
  transition: width 0.3s;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  border-bottom: 1px solid #002140;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}

.el-menu {
  border-right: none;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.collapse-btn {
  font-size: 20px;
  cursor: pointer;
  color: #5a5e66;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.action-item {
  font-size: 18px;
  cursor: pointer;
  color: #5a5e66;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.user-name {
  font-size: 14px;
  color: #333;
}

.main-content {
  background: #f0f2f5;
  padding: 20px;
  overflow-y: auto;
}

/* 路由切换动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
