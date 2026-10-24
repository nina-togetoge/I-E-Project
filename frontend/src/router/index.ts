/**
 * ==== 路由配置 + 权限守卫 router/index.ts ====
 * 职责：定义全部前端路由、组织布局层级，并通过全局守卫完成登录态校验与角色鉴权。
 * 被谁引用：main.ts 注册为 Vue Router 插件；layout/index.vue 读取 options.routes 生成侧边栏；
 *           App.vue 额外注册了加载骨架相关的 beforeEach/afterEach。
 * 路由分组：
 *   1. publicRoutes：公开页（登录、403、404），无需登录即可访问。
 *   2. layoutRoutes：登录后布局页，统一挂在 path '/' 的布局组件下，子路由渲染进 layout 的 router-view。
 *      子路由再按业务氛围分为：工作台 / 项目管理 / 审核中心 / 专家端 / 系统管理（管理端）/ 资源中心。
 * meta 字段含义：
 *   title     页面标题，同时用于浏览器标题、面包屑与标签页名称。
 *   icon      Element Plus 图标组件名，用于侧边菜单。
 *   roles     允许访问的角色数组（1 学生 / 2 教师 / 3 专家 / 4 管理员）；缺省表示登录后皆可。
 *   group     侧边栏分组 key（workbench/project/review/system/resource），layout 据此归组。
 *   hidden    true 表示不出现在侧边菜单（详情页、创建页、子列表页等）。
 *   affix     可选，标签页固定不可关闭（由 tags store 维护，非本文件配置）。
 *   keepAlive 约定字段：为 true 时页面可被缓存；当前路由表未显式配置，布局也未启用 keep-alive。
 * 鉴权流程（见文件末尾守卫）：
 *   未登录 → 白名单放行，否则跳 /login 并携带 redirect；
 *   已登录但无 userInfo → 先拉取；token 在拉取过程中失效 → 回登录页；
 *   首次登录强制改密 → 除白名单外全部锁定到 /profile?tab=password；
 *   已登录访问 /login → 重定向首页；meta.roles 不匹配 → /403；
 *   动态标题：每次跳转写入 document.title。
 */
import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'

// ==================== 路由定义 ====================

/** 公共路由（无需登录）：登录页与两个错误页，均采用路由级懒加载 */
// 说明：错误页也走懒加载，避免首屏加载与业务无关的组件；登录页单独拆 core chunk 便于复用。
const publicRoutes: RouteRecordRaw[] = [
  // 登录页：全局唯一入口，守卫会向未登录访问的业务页追加 redirect 参数
  {
    path: '/login',
    name: 'Login',
    component: () => import(/* @vite-ignore */ /* webpackChunkName: "core" */ '@/views/Login.vue'),
    meta: { title: '登录' },
  },
  // 403：已登录但角色不满足 meta.roles 时的落地页
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import(/* webpackChunkName: "misc" */ '@/views/error/403.vue'),
    meta: { title: '无权限' },
  },
  // 404：兜底页，由末尾的通配路由重定向进入
  {
    path: '/404',
    name: 'NotFound',
    component: () => import(/* webpackChunkName: "misc" */ '@/views/error/404.vue'),
    meta: { title: '页面不存在' },
  },
]

/** 主布局路由（需登录）：所有业务页面都是该布局的子路由，访问 '/' 默认进首页 */
// 布局路由本身没有 meta.title，因此不会出现在面包屑与侧边菜单中；标题取具体子路由。
const layoutRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    // 布局组件懒加载：首屏先加载布局壳，子页面再按各自 chunk 加载
    component: () => import(/* webpackChunkName: "core" */ '@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      // ==================== 工作台 ====================
      // 首页：登录后默认落地页，所有角色可见
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import(/* @vite-ignore */ /* webpackChunkName: "core" */ '@/views/dashboard/index.vue'),
        meta: { title: '首页', icon: 'HomeFilled', group: 'workbench' },
      },
      // 个人中心：资料维护与修改密码（首次登录强制改密也落在此页 password Tab）
      {
        path: 'profile',
        name: 'Profile',
        component: () => import(/* @vite-ignore */ /* webpackChunkName: "core" */ '@/views/profile/index.vue'),
        meta: { title: '个人中心', icon: 'User', group: 'workbench' },
      },

      // ==================== 项目管理 ====================
      // 我的项目：学生与教师可见，支持按项目状态筛选（0~13，见业务状态定义）
      {
        path: 'projects',
        name: 'MyProjects',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/MyProjects.vue'),
        meta: { title: '我的项目', icon: 'Folder', roles: [1, 2], group: 'project' },
      },
      // 项目申报：仅学生可进入，hidden 表示不在菜单中单独展示
      {
        path: 'projects/create',
        name: 'ProjectCreate',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/ProjectCreate.vue'),
        meta: { title: '项目申报', hidden: true, roles: [1] },
      },
      // 项目详情：动态参数 :id，所有角色均可查看（具体可见字段由后端与盲审模式控制）
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/ProjectDetail.vue'),
        meta: { title: '项目详情', hidden: true },
      },
      // 中期检查：项目状态 7（中期检查中）时进入，hidden 但保留面包屑标题
      {
        path: 'projects/:id/midterm',
        name: 'ProjectMidterm',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/MidtermCheck.vue'),
        meta: { title: '中期检查', hidden: true },
      },
      // 项目成果：执行段并行节点，立项后即可登记成果
      {
        path: 'projects/:id/achievements',
        name: 'ProjectAchievements',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/ProjectAchievements.vue'),
        meta: { title: '项目成果', hidden: true },
      },
      // 结项验收：项目状态 8（待结题）时进入，由专家/管理员操作
      {
        path: 'projects/:id/final',
        name: 'ProjectFinal',
        component: () => import(/* webpackChunkName: "project" */ '@/views/project/FinalCheck.vue'),
        meta: { title: '结项验收', hidden: true },
      },
      // 报销申请：学生发起经费报销，归入项目管理分组
      {
        path: 'expenses',
        name: 'MyExpenses',
        component: () => import(/* webpackChunkName: "expense" */ '@/views/expense/MyExpenses.vue'),
        meta: { title: '报销申请', icon: 'Money', roles: [1], group: 'project' },
      },
      // 我的证书：学生查看已结题项目的证书
      {
        path: 'my-certificates',
        name: 'MyCertificates',
        component: () => import(/* webpackChunkName: "certificate" */ '@/views/certificate/MyCertificates.vue'),
        meta: { title: '我的证书', icon: 'Medal', roles: [1], group: 'project' },
      },

      // ==================== 审核中心 ====================
      // 审核工作台：教师（2）与管理员（4）共用，承载学院初审/校级复审等审批入口
      {
        path: 'review',
        name: 'ReviewCenter',
        component: () => import(/* webpackChunkName: "review" */ '@/views/review/ReviewCenter.vue'),
        meta: { title: '审核工作台', icon: 'Bell', roles: [2, 4], group: 'review' },
      },
      // 待审核列表：从工作台进入的二级页，hidden 避免菜单重复
      {
        path: 'review/pending',
        name: 'ReviewPending',
        component: () => import(/* webpackChunkName: "review" */ '@/views/review/ReviewPending.vue'),
        meta: { title: '待审核列表', icon: 'Bell', roles: [2, 4], group: 'review', hidden: true },
      },
      // 变更申请审批：项目内容/成员/预算变更的审批入口
      {
        path: 'review/changes',
        name: 'ChangeApproval',
        component: () => import(/* webpackChunkName: "review" */ '@/views/review/ChangeApproval.vue'),
        meta: { title: '变更申请审批', icon: 'EditPen', roles: [2, 4], group: 'review', hidden: true },
      },

      // ==================== 专家端 ====================
      // 待评审项目：仅专家（3）可见，归属审核中心分组
      {
        path: 'expert/pending',
        name: 'ExpertPending',
        component: () => import(/* webpackChunkName: "expert" */ '@/views/expert/ExpertPending.vue'),
        meta: { title: '待评审项目', icon: 'Document', roles: [3], group: 'review' },
      },

      // ==================== 系统管理（管理端） ====================
      // 说明：roles: [4] 同时覆盖超管与学院管理员；具体数据范围由后端按 college_id 隔离。
      // 用户管理：账号启停、角色与学院调整
      {
        path: 'admin/users',
        name: 'UserManage',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/UserManage.vue'),
        meta: { title: '用户管理', icon: 'UserFilled', roles: [4], group: 'system' },
      },
      // 全量项目管理：管理员维护项目状态、分配评审专家等
      {
        path: 'admin/projects',
        name: 'AdminProjects',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/AdminProjects.vue'),
        meta: { title: '项目管理', icon: 'Files', roles: [4], group: 'system' },
      },
      // 经费管理：教师也可查看/审批，故 roles 为 [2, 4]
      {
        path: 'admin/expenses',
        name: 'AdminExpenses',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/AdminExpenses.vue'),
        meta: { title: '经费管理', icon: 'Wallet', roles: [2, 4], group: 'system' },
      },
      // 数据看板：仅管理员，展示项目/经费/评审等汇总统计
      {
        path: 'admin/statistics',
        name: 'Statistics',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/Statistics.vue'),
        meta: { title: '数据看板', icon: 'DataAnalysis', roles: [4], group: 'system' },
      },
      // 操作日志：审计用，仅管理员可见
      {
        path: 'admin/logs',
        name: 'OperationLogs',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/OperationLogs.vue'),
        meta: { title: '操作日志', icon: 'List', roles: [4], group: 'system' },
      },
      // 学院管理：维护学院基础数据，通常由超管操作
      {
        path: 'admin/colleges',
        name: 'CollegeManage',
        component: () => import(/* webpackChunkName: "admin" */ '@/views/admin/CollegeManage.vue'),
        meta: { title: '学院管理', icon: 'OfficeBuilding', roles: [4], group: 'system' },
      },

      // ==================== 资源中心 ====================
      // 创新创业大赛：所有角色可浏览赛事信息
      {
        path: 'competitions',
        name: 'CompetitionList',
        component: () => import(/* webpackChunkName: "competition" */ '@/views/competition/CompetitionList.vue'),
        meta: { title: '创新创业大赛', icon: 'Trophy', roles: [1, 2, 3, 4], group: 'resource' },
      },
      // 大赛管理：管理员维护赛事，归入系统管理分组
      {
        path: 'admin/competitions',
        name: 'CompetitionManage',
        component: () => import(/* webpackChunkName: "competition" */ '@/views/competition/CompetitionManage.vue'),
        meta: { title: '大赛管理', icon: 'Trophy', roles: [4], group: 'system' },
      },
      // 公告管理：管理员发布/编辑系统公告
      {
        path: 'admin/announcements',
        name: 'AnnouncementManage',
        component: () => import(/* webpackChunkName: "misc" */ '@/views/announcement/AnnouncementManage.vue'),
        meta: { title: '公告管理', icon: 'Bell', roles: [4], group: 'system' },
      },
      // 立项结果公示：所有角色可查看已立项/落选公示
      {
        path: 'announcement/approval',
        name: 'ApprovalAnnouncement',
        component: () => import(/* webpackChunkName: "misc" */ '@/views/announcement/ApprovalList.vue'),
        meta: { title: '立项结果公示', icon: 'Bell', roles: [1, 2, 3, 4], group: 'resource' },
      },
      // 归档项目库：已结题项目的只读档案，所有角色可检索
      {
        path: 'admin/archive',
        name: 'ProjectArchive',
        component: () => import(/* webpackChunkName: "misc" */ '@/views/archive/ArchiveList.vue'),
        meta: { title: '归档项目库', icon: 'Box', roles: [1, 2, 3, 4], group: 'resource' },
      },
    ],
  },
]

// ==================== 路由表组装 ====================
// 公开页 + 布局页合并；末尾通配路由兜底到 404，避免未知地址白屏。
// 通配路由必须放在最后：Vue Router 按注册顺序匹配，提前注册会吞掉所有业务路径。
// 布局页的 redirect 指向 /dashboard，因此访问 '/' 或登录成功后默认进入首页。
const routes: RouteRecordRaw[] = [
  ...publicRoutes,
  ...layoutRoutes,
  { path: '/:pathMatch(.*)*', redirect: '/404' },
]

// 使用 HTML5 History 模式（地址栏无 #）；部署时服务端需将未知路径回退到 index.html。
// 该模式依赖同源部署与网关 rewrite，静态服务器直接刷新子路由会 404。
// 未配置 scrollBehavior：滚动位置由各页面自行管理，避免与项目详情页的区域滚动定位冲突。
const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ==================== 路由守卫 ====================
// 白名单：未登录也可访问的路径；强制改密流程中同样放行这些页面。
// 白名单只做精确匹配，不支持通配，新增公开页时必须同步加入此数组。
const whiteList = ['/login', '/403', '/404']

/**
 * 全局前置守卫：登录态恢复 + 强制改密 + 角色鉴权 + 动态标题
 * 执行顺序（重要）：
 *   1. 先写 document.title（任何分支都能得到正确标题）；
 *   2. accessToken 存在 → 无 userInfo 则拉取；拉取中 token 失效 → 回登录页；
 *   3. force_change_pwd === 1 → 锁定到 /profile?tab=password&forceReset=1；
 *   4. 已登录访问 /login → 回首页；
 *   5. meta.roles 存在且不包含当前 role → /403；
 *   6. 否则放行。
 * 未登录分支：白名单直接放行，其余带 redirect 跳登录页，登录成功后可回到原地址。
 * 副作用：可能发起用户信息请求、清除失效 token、修改浏览器标题与路由跳转。
 */
router.beforeEach(async (to, _from, next) => {
  // 动态标题：优先使用路由 meta.title，缺省为"首页"
  document.title = `${to.meta.title || '首页'} - 校园创新创业项目管理平台`

  // 在守卫内部获取 store：确保 Pinia 已由 main.ts 安装，避免模块加载期读取未初始化实例
  const userStore = useUserStore()

  if (userStore.accessToken) {
    // 已登录，如果还没有 userInfo 则获取（刷新页面后 store 为空的恢复逻辑）
    // 注意：token 本身不等于有效会话，仍需后端校验；这里只处理"是否尝试恢复"
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
    // forceReset=1 供个人中心锁死 Tab 切换，改密成功前不能离开该 Tab。
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

    // 已登录访问登录页，重定向首页（避免重复登录）
    if (to.path === '/login') {
      next('/')
      return
    }

    // 角色权限校验：meta.roles 未配置表示登录后皆可访问
    // 这里只做前端可见性拦截，接口仍需后端再次校验，防止绕过前端直接调用
    const requiredRoles = to.meta.roles as number[] | undefined
    if (requiredRoles && !requiredRoles.includes(userStore.role)) {
      next('/403')
      return
    }

    // 全部校验通过
    // 注意：此处必须显式调用 next()，否则导航会挂起，页面停留在原路由
    next()
  } else {
    // 未登录：白名单放行，其余记录完整路径后跳登录页
    if (whiteList.includes(to.path)) {
      next()
    } else {
      next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
    }
  }
})

import { useTagsStore } from '@/store/tags'

// ==================== 后置守卫：标签页记录 ====================
// 登录/错误页不进入多标签；store 未就绪时静默忽略，避免影响导航完成。
// 放在 afterEach 而非组件内：保证无论从哪个页面跳转都能统一记账，组件无需感知标签逻辑。
router.afterEach((to) => {
  if (to.path === '/login' || to.path === '/403' || to.path === '/404') return
  try {
    const tagsStore = useTagsStore()
    tagsStore.addView(to)
  } catch {}
})

// ==================== 首屏空闲预取 ====================
// 应用就绪后，在浏览器空闲时预取首页、项目列表、个人中心三个高频页面，
// 缩短用户首次点击对应菜单时的等待；requestIdleCallback 不可用时退化为 1s 定时。
// isReady 保证首屏路由已解析完成，避免预取与首屏加载争抢带宽与主线程。
// 预取仅下载 chunk、不执行页面逻辑，因此不会触发接口请求或副作用。
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
