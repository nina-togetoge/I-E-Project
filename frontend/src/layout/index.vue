<!--
  主布局框架
  侧边栏 + 顶栏 + 标签页 + 内容区
-->
<template>
  <el-container class="layout-container">
    <!-- PC端侧边栏 -->
    <el-aside v-if="!isMobile" :width="isCollapse ? '64px' : '210px'" class="sidebar">
      <div class="logo">
        <img src="/images/logo.jpg" class="logo-img" :class="{ collapsed: isCollapse }" alt="logo" />
        <span class="logo-text" :class="{ collapsed: isCollapse }">创新创业平台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        :collapse-transition="true"
        :background-color="sidebarBg"
        text-color="#bfcbd9"
        :active-text-color="appearanceStore.themeColor"
        router
      >
        <template v-for="group in groupedRoutes" :key="group.key">
          <el-sub-menu :index="group.key">
            <template #title>
              <el-icon><component :is="group.icon" /></el-icon>
              <span>{{ group.title }}</span>
            </template>
            <el-menu-item
              v-for="route in group.routes"
              :key="route.path"
              :index="resolvePath(route)"
            >
              <el-icon v-if="route.meta?.icon">
                <component :is="route.meta.icon" />
              </el-icon>
              <template #title>{{ route.meta?.title }}</template>
            </el-menu-item>
            <!-- 流程阶段（归入对应分组） -->
            <div
              v-for="item in stagesOfGroup(group.key)"
              :key="item.key"
              class="el-menu-item stage-menu-item"
              :class="{ 'is-active': item.isActive, 'is-done': item.isDone }"
              @click="handleStageClick(item.key)"
            >
              <span>{{ item.label }}</span>
            </div>
          </el-sub-menu>
        </template>
      </el-menu>
    </el-aside>

    <!-- 移动端Drawer侧边栏 -->
    <el-drawer
      v-if="isMobile"
      v-model="drawerVisible"
      direction="ltr"
      size="240px"
      :show-close="false"
      modal-class="mobile-sidebar-drawer"
      class="mobile-drawer"
    >
      <div class="sidebar sidebar-mobile">
        <div class="logo">
          <img src="/images/logo.jpg" class="logo-img" alt="logo" />
          <span class="logo-text">创新创业平台</span>
        </div>
        <el-menu
          :default-active="activeMenu"
          :collapse="false"
          :collapse-transition="false"
          :background-color="sidebarBg"
          text-color="#bfcbd9"
          :active-text-color="appearanceStore.themeColor"
          router
          @select="handleMenuSelect"
        >
          <template v-for="group in groupedRoutes" :key="`m-${group.key}`">
            <el-sub-menu :index="`m-${group.key}`">
              <template #title>
                <el-icon><component :is="group.icon" /></el-icon>
                <span>{{ group.title }}</span>
              </template>
              <el-menu-item
                v-for="route in group.routes"
                :key="route.path"
                :index="resolvePath(route)"
              >
                <el-icon v-if="route.meta?.icon">
                  <component :is="route.meta.icon" />
                </el-icon>
                <template #title>{{ route.meta?.title }}</template>
              </el-menu-item>
              <!-- 流程阶段（归入对应分组） -->
              <div
                v-for="item in stagesOfGroup(group.key)"
                :key="item.key"
                class="el-menu-item stage-menu-item"
                :class="{ 'is-active': item.isActive, 'is-done': item.isDone }"
                @click="handleStageClick(item.key)"
              >
                <span>{{ item.label }}</span>
              </div>
            </el-sub-menu>
          </template>
        </el-menu>
      </div>
    </el-drawer>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="handleToggleSidebar">
            <Fold v-if="!isMobile && !isCollapse" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/" class="breadcrumb" v-if="!isMobile">
            <el-breadcrumb-item
              v-for="(item, idx) in breadcrumbs"
              :key="item.path || idx"
              :to="!item.isLast ? item.path : undefined"
            >
              {{ item.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <NoticeBell />
          <ThemePicker />
          <ThemeToggle />
          <el-tooltip v-if="userStore.isExpert" :content="appearanceStore.isBlindMode ? '关闭盲审模式' : '开启盲审模式'" placement="bottom">
            <el-icon
              class="action-item"
              :class="{ 'blind-active': appearanceStore.isBlindMode }"
              @click="appearanceStore.toggleBlindMode()"
            >
              <component :is="appearanceStore.isBlindMode ? 'View' : 'Hide'" />
            </el-icon>
          </el-tooltip>
          <el-tooltip content="全屏" placement="bottom" v-if="!isMobile">
            <el-icon class="action-item" @click="toggleFullscreen">
              <FullScreen />
            </el-icon>
          </el-tooltip>
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="32" :src="userStore.userInfo?.avatar || undefined">
                {{ userStore.userInfo?.real_name?.[0] || 'U' }}
              </el-avatar>
              <span class="user-name" v-if="!isMobile">{{ userStore.userInfo?.real_name }}</span>
              <el-tag size="small" type="info" v-if="!isMobile">{{ userStore.roleNameDisplay }}</el-tag>
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

      <TagsView />

      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
    <!-- 右下角悬浮 AI 助手 -->
    <AIAssistant />
    <!-- 项目详情弹窗 -->
    <ProjectDetailDialog />
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  Fold, Expand, FullScreen, User, SwitchButton, View, Hide,
  Monitor, Folder, Bell, Setting, Box, Trophy
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { useAppearanceStore } from '@/store/appearance'
import { useProcessStore } from '@/store/process'
import ThemeToggle from '@/components/ThemeToggle.vue'
import ThemePicker from '@/components/ThemePicker.vue'
import TagsView from '@/components/TagsView.vue'
import NoticeBell from '@/components/NoticeBell.vue'
import AIAssistant from '@/components/AIAssistant.vue'
import ProjectDetailDialog from '@/components/ProjectDetailDialog.vue'
import { ROLES } from '@/api/types'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appearanceStore = useAppearanceStore()
const processStore = useProcessStore()

// 项目申报后流程阶段定义
const PROCESS_STAGES = [
  { key: 'declare', label: '项目申报', status: 0 },
  { key: 'teacher', label: '指导教师确认', status: 12 },
  { key: 'college', label: '学院初审', status: 1 },
  { key: 'university', label: '校级复审', status: 3 },
  { key: 'expert', label: '专家评审', status: 5 },
  { key: 'approved', label: '项目立项', status: 6 },
  { key: 'midterm', label: '中期检查', status: 7 },
  { key: 'achievement', label: '成果登记', status: 6 },
  { key: 'final', label: '结项验收', status: 8 },
]

// 阶段按功能归入侧边栏分组
// 冗余清理：中期检查/成果登记/结项验收均跳转 /projects（=我的项目），
//           项目立项跳转 /announcement/approval（=立项结果公示），
//           项目申报仅对学生是唯一入口（/projects/create），其他角色与我的项目重复。
//           因此侧边栏仅保留学生的"项目申报"阶段入口。
const STAGE_GROUP_MAP: Record<string, string[]> = {
  project: ['declare'],
  review: [],
}

// 取某分组下的阶段列表（带序号偏移，保持全局编号连续）
function stagesOfGroup(groupKey: string) {
  const keys = STAGE_GROUP_MAP[groupKey] || []
  return keys
    .map((k) => PROCESS_STAGES.find((s) => s.key === k))
    .filter(Boolean)
    .filter((s) => {
      // 项目申报仅对学生显示（教师/管理员跳转目标与"我的项目"重复）
      if (s!.key === 'declare') return userStore.role === ROLES.STUDENT
      return true
    })
    .map((s) => {
      const idx = PROCESS_STAGES.findIndex((p) => p.key === s!.key)
      const full = processStages.value.find((p) => p.key === s!.key)
      return { ...s!, idx: idx + 1, isActive: full?.isActive || false, isDone: full?.isDone || false }
    })
}

const processStages = computed(() => {
  const cur = processStore.projectStatus
  // 非详情页：阶段列表始终显示，但无高亮
  if (cur === null) {
    return PROCESS_STAGES.map((s) => ({ ...s, isActive: false, isDone: false }))
  }
  const isRejected = cur === 10 || cur === 11
  // 找到当前状态对应的阶段索引
  const curIdx = PROCESS_STAGES.findIndex((s) => {
    if (s.key === 'final') return cur === 8 || cur >= 9
    if (s.key === 'achievement') return cur >= 6
    if (cur === 2) return s.key === 'college'
    if (cur === 4) return s.key === 'university'
    return s.status === cur
  })
  return PROCESS_STAGES.map((s, idx) => {
    // 成果登记：立项后即可登记，标记为已完成
    if (s.key === 'achievement') {
      return { ...s, isActive: false, isDone: !isRejected && cur >= 6 }
    }
    const isDone = !isRejected && curIdx >= 0 && idx < curIdx
    const isActive = !isRejected && idx === curIdx
    return { ...s, isActive, isDone }
  })
})

// 阶段 → 对应页面路由（非详情页点击时跳转，按角色适配）
function stageRoute(key: string): string {
  const role = userStore.role
  switch (key) {
    case 'declare':
      // 学生进申报页，其他角色看项目列表
      return role === 1 ? '/projects/create' : '/projects'
    case 'midterm':
    case 'achievement':
    case 'final':
      return '/projects'
    case 'teacher':
    case 'college':
    case 'university':
      return '/review/pending'
    case 'expert':
      // 专家进待评审，其他角色看待审核
      return role === 3 ? '/expert/pending' : '/review/pending'
    case 'approved':
      return '/announcement/approval'
    default:
      return '/projects'
  }
}

function handleStageClick(key: string) {
  // 已在项目详情页：中期检查/成果登记跳转独立页面，其余滚动到对应区域
  if (route.path.startsWith('/projects/')) {
    const projectId = route.params.id
    if (key === 'midterm') {
      router.push(`/projects/${projectId}/midterm`)
      return
    }
    if (key === 'achievement') {
      router.push(`/projects/${projectId}/achievements`)
      return
    }
    processStore.requestScroll(key)
    return
  }
  // 非详情页：跳转到该阶段对应的功能页面
  router.push(stageRoute(key))
}

const isCollapse = ref(false)
const isMobile = ref(false)
const drawerVisible = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    isCollapse.value = true
  }
}

function handleMenuSelect() {
  if (isMobile.value) {
    drawerVisible.value = false
  }
  // 点击菜单项后滚动到激活项
  scrollActiveIntoView()
}

// 路由变化后，自动滚动侧边栏让激活菜单项可见（PC 端 + 移动端抽屉）
function scrollActiveIntoView() {
  // 轮询重试：等待子菜单展开动画完成，确保激活项可见
  let attempts = 0
  const tryScroll = () => {
    attempts++
    const menus = document.querySelectorAll('.sidebar .el-menu, .sidebar-mobile .el-menu')
    let allVisible = true
    menus.forEach((menu) => {
      const el = menu as HTMLElement
      const active = el.querySelector('.el-menu-item.is-active, .stage-menu-item.is-active') as HTMLElement | null
      if (!active) { allVisible = false; return }

      // 激活项在折叠的子菜单内 → 先展开
      const parentSub = active.closest('.el-sub-menu:not(.is-opened)') as HTMLElement | null
      if (parentSub) {
        parentSub.querySelector('.el-sub-menu__title')?.click()
        allVisible = false
        return
      }

      // 判断是否在可视区内
      const menuRect = el.getBoundingClientRect()
      const itemRect = active.getBoundingClientRect()
      if (itemRect.top < menuRect.top || itemRect.bottom > menuRect.bottom) {
        // 不在可视区 → 滚动
        active.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
        allVisible = false
      }
    })
    // 未全部可见且重试次数未用完，继续轮询
    if (!allVisible && attempts < 10) {
      setTimeout(tryScroll, 200)
    }
  }
  tryScroll()
}

watch(() => route.path, scrollActiveIntoView)

// 项目详情页状态变化时（阶段高亮变化），也滚动到激活阶段
watch(() => processStore.projectStatus, () => {
  if (route.path.startsWith('/projects/')) {
    scrollActiveIntoView()
  }
})

// 移动端抽屉打开时，也滚动到激活项
watch(drawerVisible, (val) => {
  if (val) scrollActiveIntoView()
})

watch(isCollapse, (val) => {
  if (isMobile.value) {
    drawerVisible.value = !val
  }
})

watch(drawerVisible, (val) => {
  if (isMobile.value) {
    isCollapse.value = !val
  }
})

let resizeTimer: number | null = null
function onResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(() => {
    checkMobile()
  }, 100)
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (resizeTimer) clearTimeout(resizeTimer)
})
const currentRoute = computed(() => route)

const sidebarBg = computed(() =>
  appearanceStore.isDark ? '#0a0a0a' : '#001529'
)

const activeMenu = computed(() => route.path)

const filteredRoutes = computed(() => {
  const children = router.options.routes.find((r) => r.path === '/')?.children || []
  return children.filter((child) => {
    const roles = child.meta?.roles as number[] | undefined
    if (!roles) return true
    return roles.includes(userStore.role)
  })
})

// 侧边栏分组配置（顺序即显示顺序）
const MENU_GROUPS = [
  { key: 'workbench', title: '工作台', icon: Monitor },
  { key: 'project', title: '项目管理', icon: Folder },
  { key: 'review', title: '审核中心', icon: Bell },
  { key: 'system', title: '系统管理', icon: Setting },
  { key: 'resource', title: '资源中心', icon: Box },
]

// 按 group 分组过滤后的路由（隐藏路由排除）
const groupedRoutes = computed(() => {
  const visible = filteredRoutes.value.filter((r) => !r.meta?.hidden)
  return MENU_GROUPS
    .map((g) => ({
      ...g,
      routes: visible.filter((r) => (r.meta?.group as string) === g.key),
    }))
    .filter((g) => g.routes.length > 0)
})

const breadcrumbs = computed(() => {
  const result: { path: string; title: string; isLast: boolean }[] = []
  result.push({ path: '/', title: '首页', isLast: false })

  const allRoutes = router.getRoutes()
  const segments = route.path.split('/').filter(Boolean)
  let builtPath = ''
  const matchedList: { path: string; title: string }[] = []

  for (const seg of segments) {
    builtPath += '/' + seg
    const found = allRoutes.find((r) => r.path === builtPath && r.meta?.title)
    if (found && found.meta?.title) {
      matchedList.push({ path: builtPath, title: String(found.meta.title) })
    }
  }

  if (matchedList.length === 0 && route.meta?.title) {
    matchedList.push({ path: route.path, title: String(route.meta.title) })
  }

  for (let i = 0; i < matchedList.length; i++) {
    const isLast = i === matchedList.length - 1
    const item = matchedList[i]
    result.push({
      path: isLast ? '' : item.path,
      title: item.title,
      isLast,
    })
  }

  if (result.length > 0) {
    result[result.length - 1].isLast = true
    result[result.length - 1].path = ''
  }

  return result
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
    }).then(async () => {
      // 必须 await logout 完成，确保 token/localStorage 已清空，
      // 否则路由守卫会因检测到旧 token 而重定向到强制改密页
      await userStore.logout()
      router.replace('/login')
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

function handleToggleSidebar() {
  if (isMobile.value) {
    drawerVisible.value = !drawerVisible.value
  } else {
    isCollapse.value = !isCollapse.value
  }
}
</script>

<style scoped>
.stage-menu-item {
  color: #bfcbd9;
}
.stage-menu-item:hover {
  background-color: rgba(255, 255, 255, 0.08);
}
.stage-menu-item.is-active {
  color: var(--el-color-primary);
  font-weight: 600;
}
.stage-menu-item.is-done {
  color: #a0cfff;
}
.layout-container {
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  background-color: var(--sidebar-color, #001529);
  transition: width 0.3s ease, background-color 0.3s ease;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-mobile {
  height: 100%;
}

.logo {
  height: 60px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  border-bottom: 1px solid #002140;
  padding: 0 8px;
}

.logo-img {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  transition: width 0.3s ease, height 0.3s ease;
}

.logo-img.collapsed {
  width: 40px;
  height: 40px;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  transition: opacity 0.3s ease;
  opacity: 1;
}

.logo-text.collapsed {
  display: none;
}

.el-menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--header-color, #fff);
  border-bottom: 1px solid var(--header-border-color, #e6e6e6);
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  transition: background 0.3s ease, border-color 0.3s ease;
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

:deep(html.dark) .collapse-btn {
  color: #cfd3dc;
}

.breadcrumb {
  font-size: 14px;
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
  transition: color 0.2s;
}
.action-item.blind-active {
  color: var(--el-color-warning);
}

:deep(html.dark) .action-item {
  color: #cfd3dc;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.user-name {
  font-size: 14px;
  color: var(--text-color, #333);
}

.main-content {
  background: var(--bg-color, #f0f2f5);
  padding: 20px;
  overflow-y: auto;
  overflow-x: hidden;
  transition: background 0.3s ease;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

:deep(.mobile-drawer .el-drawer__body) {
  padding: 0;
}

@media (max-width: 768px) {
  .header {
    padding: 0 12px !important;
  }
  .header-left {
    gap: 8px;
  }
  .header-right {
    gap: 12px;
  }
  .main-content {
    padding: 12px;
  }
}
</style>
