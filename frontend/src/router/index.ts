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
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/error/403.vue'),
    meta: { title: '无权限' },
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '页面不存在' },
  },
]

/** 主布局路由（需登录） */
const layoutRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      // ==================== 通用页面 ====================
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '首页', icon: 'HomeFilled' },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/index.vue'),
        meta: { title: '个人中心', icon: 'User' },
      },

      // ==================== 学生端 ====================
      {
        path: 'projects',
        name: 'MyProjects',
        component: () => import('@/views/project/MyProjects.vue'),
        meta: { title: '我的项目', icon: 'Folder', roles: [1, 2, 4] },
      },
      {
        path: 'projects/create',
        name: 'ProjectCreate',
        component: () => import('@/views/project/ProjectCreate.vue'),
        meta: { title: '项目申报', icon: 'EditPen', roles: [1] },
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/project/ProjectDetail.vue'),
        meta: { title: '项目详情', hidden: true },
      },
      {
        path: 'expenses',
        name: 'MyExpenses',
        component: () => import('@/views/expense/MyExpenses.vue'),
        meta: { title: '报销申请', icon: 'Money', roles: [1] },
      },

      // ==================== 教师端 ====================
      {
        path: 'review/pending',
        name: 'ReviewPending',
        component: () => import('@/views/review/ReviewPending.vue'),
        meta: { title: '待审核列表', icon: 'Bell', roles: [2, 4] },
      },
      {
        path: 'review/:id',
        name: 'ReviewDetail',
        component: () => import('@/views/review/ReviewDetail.vue'),
        meta: { title: '审核详情', hidden: true, roles: [2, 3, 4] },
      },

      // ==================== 专家端 ====================
      {
        path: 'expert/pending',
        name: 'ExpertPending',
        component: () => import('@/views/expert/ExpertPending.vue'),
        meta: { title: '待评审项目', icon: 'Document', roles: [3] },
      },

      // ==================== 管理员端 ====================
      {
        path: 'admin/users',
        name: 'UserManage',
        component: () => import('@/views/admin/UserManage.vue'),
        meta: { title: '用户管理', icon: 'UserFilled', roles: [4] },
      },
      {
        path: 'admin/projects',
        name: 'AdminProjects',
        component: () => import('@/views/admin/AdminProjects.vue'),
        meta: { title: '项目管理', icon: 'Files', roles: [4] },
      },
      {
        path: 'admin/expenses',
        name: 'AdminExpenses',
        component: () => import('@/views/admin/AdminExpenses.vue'),
        meta: { title: '经费管理', icon: 'Wallet', roles: [4] },
      },
      {
        path: 'admin/statistics',
        name: 'Statistics',
        component: () => import('@/views/admin/Statistics.vue'),
        meta: { title: '数据看板', icon: 'DataAnalysis', roles: [4] },
      },
      {
        path: 'admin/logs',
        name: 'OperationLogs',
        component: () => import('@/views/admin/OperationLogs.vue'),
        meta: { title: '操作日志', icon: 'List', roles: [4] },
      },
      {
        path: 'admin/archive',
        name: 'ProjectArchive',
        component: () => import('@/views/archive/ArchiveList.vue'),
        meta: { title: '归档项目库', icon: 'Box', roles: [1, 2, 3, 4] },
      },
      {
        path: 'admin/search',
        name: 'FullSearch',
        component: () => import('@/views/search/FullSearch.vue'),
        meta: { title: '全文检索', icon: 'Search', roles: [1, 2, 3, 4] },
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

export default router
