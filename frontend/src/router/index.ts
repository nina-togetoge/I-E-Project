/**
 * 路由配置 + 权限守卫
 * 基于角色的动态路由：未登录跳登录页，无权限跳403
 */
import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'

// ==================== 路由定义 ====================

/** 公共路由（无需登录） */
const publicRoutes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import(/* @vite-ignore */ /* webpackChunkName: "core" */ '@/views/Login.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import(/* webpackChunkName: "misc" */ '@/views/error/403.vue'),
    meta: { title: '无权限' },
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import(/* webpackChunkName: "misc" */ '@/views/error/404.vue'),
    meta: { title: '页面不存在' },
  },
]

/** 主布局路由（需登录） */
const layoutRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import(/* webpackChunkName: "core" */ '@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      // ==================== 工作台 ====================
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import(/* @vite-ignore */ /* webpackChunkName: "core" */ '@/views/dashboard/index.vue'),
        meta: { title: '首页', icon: 'HomeFilled', group: 'workbench' },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import(/* @vite-ignore */ /* webpackChunkName: "core" */ '@/views/profile/index.vue'),
        meta: { title: '个人中心', icon: 'User', group: 'workbench' },
      },

      // ==================== 项目管理 ====================
      {
        path: 'projects',
        name: 'MyProjects',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/MyProjects.vue'),
        meta: { title: '我的项目', icon: 'Folder', roles: [1, 2], group: 'project' },
      },
      {
        path: 'projects/create',
        name: 'ProjectCreate',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/ProjectCreate.vue'),
        meta: { title: '项目申报', hidden: true, roles: [1] },
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/ProjectDetail.vue'),
        meta: { title: '项目详情', hidden: true },
      },
      {
        path: 'projects/:id/midterm',
        name: 'ProjectMidterm',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/MidtermCheck.vue'),
        meta: { title: '中期检查', hidden: true },
      },
      {
        path: 'projects/:id/achievements',
        name: 'ProjectAchievements',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/ProjectAchievements.vue'),
        meta: { title: '项目成果', hidden: true },
      },
      {
        path: 'projects/:id/final',
        name: 'ProjectFinal',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/FinalCheck.vue'),
        meta: { title: '结项验收', hidden: true },
      },
      {
        path: 'expenses',
        name: 'MyExpenses',
        component: () => import(/* webpackChunkName: "expense" */ '@/views/expense/MyExpenses.vue'),
        meta: { title: '报销申请', icon: 'Money', roles: [1], group: 'project' },
      },
      {
        path: 'my-certificates',
        name: 'MyCertificates',
        component: () => import(/* webpackChunkName: "certificate" */ '@/views/certificate/MyCertificates.vue'),
        meta: { title: '我的证书', icon: 'Medal', roles: [1], group: 'project' },
      },

      // ==================== 审核中心 ====================
      {
        path: 'review',
        name: 'ReviewCenter',
        component: () => import(/* webpackChunkName: "review" */ '@/views/review/ReviewCenter.vue'),
        meta: { title: '审核工作台', icon: 'Bell', roles: [2, 4], group: 'review' },
      },
      {
        path: 'review/pending',
        name: 'ReviewPending',
        component: () => import(/* webpackChunkName: "review" */ '@/views/review/ReviewPending.vue'),
        meta: { title: '待审核列表', icon: 'Bell', roles: [2, 4], group: 'review', hidden: true },
      },
      {
        path: 'review/changes',
        name: 'ChangeApproval',
        component: () => import(/* webpackChunkName: "review" */ '@/views/review/ChangeApproval.vue'),
        meta: { title: '变更申请审批', icon: 'EditPen', roles: [2, 4], group: 'review', hidden: true },
      },

      // ==================== 专家端 ====================
      {
        path: 'expert/pending',
        name: 'ExpertPending',
        component: () => import(/* webpackChunkName: "expert" */ '@/views/expert/ExpertPending.vue'),
        meta: { title: '待评审项目', icon: 'Document', roles: [3], group: 'review' },
      },

      // ==================== 系统管理 ====================
      {
        path: 'admin/users',
        name: 'UserManage',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/UserManage.vue'),
        meta: { title: '用户管理', icon: 'UserFilled', roles: [4], group: 'system' },
      },
      {
        path: 'admin/projects',
        name: 'AdminProjects',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/AdminProjects.vue'),
        meta: { title: '项目管理', icon: 'Files', roles: [4], group: 'system' },
      },
      {
        path: 'admin/expenses',
        name: 'AdminExpenses',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/AdminExpenses.vue'),
        meta: { title: '经费管理', icon: 'Wallet', roles: [2, 4], group: 'system' },
      },
      {
        path: 'admin/statistics',
        name: 'Statistics',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/Statistics.vue'),
        meta: { title: '数据看板', icon: 'DataAnalysis', roles: [4], group: 'system' },
      },
      {
        path: 'admin/logs',
        name: 'OperationLogs',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/OperationLogs.vue'),
        meta: { title: '操作日志', icon: 'List', roles: [4], group: 'system' },
      },
      {
        path: 'admin/colleges',
        name: 'CollegeManage',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/CollegeManage.vue'),
        meta: { title: '学院管理', icon: 'OfficeBuilding', roles: [4], group: 'system' },
      },

      // ==================== 资源中心 ====================
      {
        path: 'competitions',
        name: 'CompetitionList',
        component: () => import(/* webpackChunkName: "competition" */ '@/views/competition/CompetitionList.vue'),
        meta: { title: '创新创业大赛', icon: 'Trophy', roles: [1, 2, 3, 4], group: 'resource' },
      },
      {
        path: 'admin/competitions',
        name: 'CompetitionManage',
        component: () => import(/* webpackChunkName: "competition" */ '@/views/competition/CompetitionManage.vue'),
        meta: { title: '大赛管理', icon: 'Trophy', roles: [4], group: 'system' },
      },
      {
        path: 'admin/announcements',
        name: 'AnnouncementManage',
        component: () => import(/* webpackChunkName: "misc" */ '@/views/announcement/AnnouncementManage.vue'),
        meta: { title: '公告管理', icon: 'Bell', roles: [4], group: 'system' },
      },
      {
        path: 'announcement/approval',
        name: 'ApprovalAnnouncement',
        component: () => import(/* webpackChunkName: "misc" */ '@/views/announcement/ApprovalList.vue'),
        meta: { title: '立项结果公示', icon: 'Bell', roles: [1, 2, 3, 4], group: 'resource' },
      },
      {
        path: 'admin/archive',
        name: 'ProjectArchive',
        component: () => import(/* webpackChunkName: "misc" */ '@/views/archive/ArchiveList.vue'),
        meta: { title: '归档项目库', icon: 'Box', roles: [1, 2, 3, 4], group: 'resource' },
      },
    ],
  },
]

const routes: RouteRecordRaw[] = [
  ...publicRoutes,
  ...layoutRoutes,
  { path: '/:pathMatch(.*)*', redirect: '/404' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ==================== 路由守卫 ====================
const whiteList = ['/login', '/403', '/404']

router.beforeEach(async (to, _from, next) => {
  // 设置页面标题
  document.title = `${to.meta.title || '首页'} - 校园创新创业项目管理平台`

  const userStore = useUserStore()

  if (userStore.accessToken) {
    // 已登录，如果还没有 userInfo 则获取
    if (!userStore.userInfo) {
      await userStore.fetchUserInfo()
    }

    // fetchUserInfo 期间 token 可能因过期被清除（refresh token 也失效）
    // 此时应跳转到登录页，避免白屏
    if (!userStore.accessToken) {
      next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
      return
    }

    // [P0-2] 首次登录强制改密：仅允许访问 /profile?tab=password，其余路由全部拦截
    if (userStore.userInfo?.force_change_pwd === 1) {
      if (to.path === '/profile') {
        // 强制跳转到改密 Tab，并携带 forceReset 标记锁死切换
        if (to.query.tab !== 'password') {
          next({ path: '/profile', query: { tab: 'password', forceReset: '1' } })
          return
        }
      } else if (!whiteList.includes(to.path)) {
        next({ path: '/profile', query: { tab: 'password', forceReset: '1' } })
        return
      }
    }

    // 已登录访问登录页，重定向首页
    if (to.path === '/login') {
      next('/')
      return
    }

    // 角色权限校验
    const requiredRoles = to.meta.roles as number[] | undefined
    if (requiredRoles && !requiredRoles.includes(userStore.role)) {
      next('/403')
      return
    }

    next()
  } else {
    // 未登录
    if (whiteList.includes(to.path)) {
      next()
    } else {
      next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
    }
  }
})

import { useTagsStore } from '@/store/tags'

router.afterEach((to) => {
  if (to.path === '/login' || to.path === '/403' || to.path === '/404') return
  try {
    const tagsStore = useTagsStore()
    tagsStore.addView(to)
  } catch {}
})

router.isReady().then(() => {
  const prefetch = () => {
    try {
      import(/* @vite-ignore */ /* webpackPrefetch: true */ '@/views/dashboard/index.vue')
      import(/* webpackPrefetch: true */ '@/views/project/MyProjects.vue')
      import(/* webpackPrefetch: true */ '@/views/profile/index.vue')
    } catch {}
  }
  if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
    (window as any).requestIdleCallback(prefetch, { timeout: 3000 })
  } else {
    setTimeout(prefetch, 1000)
  }
})

export default router
