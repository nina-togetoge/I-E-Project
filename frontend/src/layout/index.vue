<!-- ==== 主布局 Layout ==== -->
<!--
  职责：登录后所有业务页面的统一外壳，负责侧边菜单、顶栏操作区、多标签页与内容区渲染。
  整体结构：
    左：PC 端 el-aside 侧边栏（可折叠 210px / 64px）；移动端改为 el-drawer 抽屉。
    右上：折叠按钮 + 面包屑；右：通知、主题色、明暗切换、盲审（仅专家）、全屏、用户菜单。
    中：TagsView 多标签页导航；下：el-main 承载 router-view，带淡入淡出过渡。
  菜单来源：读取 router.options.routes 中 path 为 '/' 的子路由，按 meta.roles 过滤，
            再按 meta.group 归入 MENU_GROUPS 的五个分组（工作台/项目管理/审核中心/系统管理/资源中心）。
  角色约定：1 学生 / 2 教师 / 3 专家 / 4 管理员；超管 = role 4 且无 college_id，
            学院管理员 = role 4 且有 college_id，菜单与路由均按角色裁剪。
  注意事项：流程阶段菜单由本地 PROCESS_STAGES 生成，与项目状态码联动高亮；
            侧边栏折叠状态与移动端抽屉状态互相驱动，窗口宽度阈值 768px。
  数据流：
    router.options.routes → filteredRoutes（按角色过滤）→ groupedRoutes（去 hidden + 分组）→ 侧边栏
    route.path / route.query.status → activeMenu（普通菜单高亮）
    processStore.projectStatus → processStages（流程阶段高亮）
  边界：布局只决定"展示哪些菜单"，不决定"能否访问"；越权访问一律由 router 守卫拦截。
-->
<template>
  <!-- 最外层容器的水平方向由 Element Plus 自动排布：侧边栏 + 右侧纵向容器 -->
  <el-container class="layout-container">
    <!-- PC 端侧边栏：宽屏下固定展示，宽度随 isCollapse 在 210px 与 64px 间切换 -->
    <el-aside v-if="!isMobile" :width="isCollapse ? '64px' : '210px'" class="sidebar">
      <!-- 品牌区：折叠时仅保留 logo，隐藏文字 -->
      <div class="logo">
        <img src="/images/logo.jpg" class="logo-img" :class="{ collapsed: isCollapse }" alt="logo" />
        <span class="logo-text" :class="{ collapsed: isCollapse }">创新创业平台</span>
      </div>
      <!-- 主菜单：默认激活项由 activeMenu 计算，选中后统一交给 handleMenuSelect -->
      <!-- 背景色与激活色来自主题状态：深色模式切近黑，激活色跟随用户选择的主题色 -->
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        :collapse-transition="true"
        :background-color="sidebarBg"
        text-color="#bfcbd9"
        :active-text-color="appearanceStore.themeColor"
        @select="handleMenuSelect"
      >
        <!-- 按分组渲染一级菜单；分组内无可见路由时该分组已被 groupedRoutes 过滤 -->
        <template v-for="group in groupedRoutes" :key="group.key">
          <el-sub-menu :index="group.key">
            <template #title>
              <el-icon><component :is="group.icon" /></el-icon>
              <span>{{ group.title }}</span>
            </template>
            <!-- 分组下的普通路由菜单项：路径经 resolvePath 补全为绝对路径 -->
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
            <!-- 流程阶段菜单：按 STAGE_GROUP_MAP 归入对应分组，index 以 stage- 前缀区分普通路由 -->
            <el-menu-item
              v-for="item in stagesOfGroup(group.key)"
              :key="item.key"
              :index="'stage-' + item.key"
              class="stage-menu-item"
              :class="{ 'is-active': item.isActive, 'is-done': item.isDone }"
            >
              <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
              <span class="stage-item-inner">{{ item.label }}</span>
            </el-menu-item>
            <!-- 已立项：把执行段的中期检查 / 结项验收收拢为二级菜单，减少一级菜单数量；
                 仅当 execStages 非空时渲染（教师看不到结项验收时可能为空） -->
            <el-sub-menu
              v-if="group.key === 'project' && execStages.length"
              index="stage-group-approved"
            >
              <template #title>
                <el-icon><CircleCheck /></el-icon>
                <span>已立项</span>
              </template>
              <el-menu-item
                v-for="item in execStages"
                :key="item.key"
                :index="'stage-' + item.key"
                class="stage-menu-item"
                :class="{ 'is-active': item.isActive, 'is-done': item.isDone }"
              >
                <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
                <span class="stage-item-inner">{{ item.label }}</span>
              </el-menu-item>
            </el-sub-menu>
          </el-sub-menu>
        </template>
      </el-menu>
    </el-aside>

    <!-- 移动端 Drawer 侧边栏：与 PC 端菜单结构一致，仅容器和折叠行为不同 -->
    <!-- direction="ltr" 从左侧滑出；240px 略宽于 PC 折叠态，保证菜单文字完整 -->
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
        <!-- 移动端品牌区：始终展示完整名称与 logo -->
        <div class="logo">
          <img src="/images/logo.jpg" class="logo-img" alt="logo" />
          <span class="logo-text">创新创业平台</span>
        </div>
        <!-- 移动端菜单：禁用折叠，避免抽屉内出现窄栏 -->
        <el-menu
          :default-active="activeMenu"
          :collapse="false"
          :collapse-transition="false"
          :background-color="sidebarBg"
          text-color="#bfcbd9"
          :active-text-color="appearanceStore.themeColor"
          @select="handleMenuSelect"
        >
          <!-- 分组索引加 m- 前缀，避免与 PC 端同名 index 冲突 -->
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
              <!-- 流程阶段（归入对应分组）：与 PC 端使用相同数据源与 stage- 前缀 -->
              <el-menu-item
                v-for="item in stagesOfGroup(group.key)"
                :key="item.key"
                :index="'stage-' + item.key"
                class="stage-menu-item"
                :class="{ 'is-active': item.isActive, 'is-done': item.isDone }"
              >
                <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
                <span class="stage-item-inner">{{ item.label }}</span>
              </el-menu-item>
              <!-- 已立项：中期检查 / 结项验收 -->
              <el-sub-menu
                v-if="group.key === 'project' && execStages.length"
                index="m-stage-group-approved"
              >
                <template #title>
                  <el-icon><CircleCheck /></el-icon>
                  <span>已立项</span>
                </template>
                <el-menu-item
                  v-for="item in execStages"
                  :key="item.key"
                  :index="'stage-' + item.key"
                  class="stage-menu-item"
                  :class="{ 'is-active': item.isActive, 'is-done': item.isDone }"
                >
                  <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
                  <span class="stage-item-inner">{{ item.label }}</span>
                </el-menu-item>
              </el-sub-menu>
            </el-sub-menu>
          </template>
        </el-menu>
      </div>
    </el-drawer>

    <el-container>
      <!-- 右侧区域：顶栏、标签页、内容区从上到下排列，由 el-container 自动转为纵向布局 -->
      <!-- 顶栏：左侧折叠按钮与面包屑，右侧全局操作与用户菜单 -->
      <el-header class="header">
        <div class="header-left">
          <!-- 折叠按钮：PC 端切换侧边栏宽度，移动端切换抽屉显隐 -->
          <el-icon class="collapse-btn" @click="handleToggleSidebar">
            <Fold v-if="!isMobile && !isCollapse" />
            <Expand v-else />
          </el-icon>
          <!-- 面包屑：由 breadcrumbs 根据当前路径逐段匹配路由 meta.title 生成，仅 PC 端展示 -->
          <el-breadcrumb separator="/" class="breadcrumb" v-if="!isMobile">
            <!-- 最后一项为当前页，不传 to 即不可点击；其余项点击后走普通路由跳转 -->
            <el-breadcrumb-item
              v-for="(item, idx) in breadcrumbs"
              :key="item.path || idx"
              :to="!item.isLast ? item.path : undefined"
            >
              {{ item.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <!-- 右侧操作区：通知、主题、盲审、全屏、用户下拉 -->
        <div class="header-right">
          <!-- 通知铃铛：独立组件，内部自行拉取未读数 -->
          <NoticeBell />
          <!-- 主题色选择与明暗切换：状态由 appearance store 统一维护 -->
          <ThemePicker />
          <ThemeToggle />
          <!-- 盲审模式仅对专家展示：开启后项目敏感信息由页面按 appearanceStore.isBlindMode 隐藏 -->
          <el-tooltip v-if="userStore.isExpert" :content="appearanceStore.isBlindMode ? '关闭盲审模式' : '开启盲审模式'" placement="bottom">
            <el-icon
              class="action-item"
              :class="{ 'blind-active': appearanceStore.isBlindMode }"
              @click="appearanceStore.toggleBlindMode()"
            >
              <component :is="appearanceStore.isBlindMode ? 'View' : 'Hide'" />
            </el-icon>
          </el-tooltip>
          <!-- 全屏切换：移动端隐藏，避免与系统手势冲突 -->
          <el-tooltip content="全屏" placement="bottom" v-if="!isMobile">
            <el-icon class="action-item" @click="toggleFullscreen">
              <FullScreen />
            </el-icon>
          </el-tooltip>
          <!-- 用户菜单：头像 + 姓名 + 角色标签；command 统一交给 handleCommand，避免模板内写分支 -->
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <!-- 头像优先取后端返回地址；无头像时用姓名首字兜底，再退化为 U -->
              <el-avatar :size="32" :src="userStore.userInfo?.avatar || undefined">
                {{ userStore.userInfo?.real_name?.[0] || 'U' }}
              </el-avatar>
              <span class="user-name" v-if="!isMobile">{{ userStore.userInfo?.real_name }}</span>
              <el-tag size="small" type="info" v-if="!isMobile">{{ userStore.roleNameDisplay }}</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <!-- command 值需与 handleCommand 中的分支保持一致 -->
                <el-dropdown-item command="profile" :icon="User">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 多标签页导航：记录访问历史，支持关闭与批量关闭 -->
      <TagsView />

      <!-- 内容区：router-view 渲染当前路由页面，切换时使用淡入淡出过渡 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <!-- mode="out-in"：先淡出旧页面再淡入新页面，避免两个页面重叠导致高度跳动 -->
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
    <!-- 右下角悬浮 AI 助手：全局常驻，不随路由切换卸载 -->
    <AIAssistant />
    <!-- 项目详情弹窗：由全局状态控制显隐，供列表页快速预览项目 -->
    <ProjectDetailDialog />
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
// 图标按用途分组导入：
//   顶栏交互：Fold/Expand/FullScreen/User/SwitchButton/View/Hide
//   菜单分组：Monitor/Folder/Bell/Setting/Box/Trophy
//   流程阶段：EditPen/OfficeBuilding/School/Star/CircleCheck/Calendar/Medal/Checked/CircleCheckFilled
import {
  Fold, Expand, FullScreen, User, SwitchButton, View, Hide,
  Monitor, Folder, Bell, Setting, Box, Trophy,
  EditPen, OfficeBuilding, School, Star, CircleCheck, Calendar, Medal, Checked, CircleCheckFilled
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

// ==================== 依赖与全局状态 ====================
// route/router 驱动菜单高亮、面包屑与跳转；userStore 提供角色与用户信息；
// appearanceStore 提供主题色/明暗/盲审；processStore 提供项目详情页的当前状态与滚动请求。
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appearanceStore = useAppearanceStore()
const processStore = useProcessStore()

// ==================== 项目流程轴定义 ====================
// 项目流程轴（两段式）：
//   审批段：项目申报 → 指导教师确认 → 学院初审 → 校级复审 → 专家评审 →（结论：立项 / 落选）
//   执行段：立项 → 中期检查 → 成果登记 → 结项验收 → 已结题
// 其中「项目立项」是两段的分界结论：审批通过即进入执行段，故归入执行段作为起点。
// 状态码速查（与后端 project.status 一致）：
//   0 草稿 / 1 待学院初审 / 2 学院初审通过（瞬时） / 3 待校级复审 / 4 校级复审通过（瞬时）
//   5 待专家评审 / 6 已立项 / 7 中期检查中 / 8 待结题 / 9 已结题
//   10 已驳回 / 11 已撤销 / 12 待指导教师确认 / 13 待分配评审专家
// 阶段与状态并非一一对应：瞬时状态（2/4）用于衔接前后审批环节，
// 因此 ACTIVE 映射中学院初审会同时接受 1/2，校级复审接受 3/4。
const PROCESS_STAGES = [
  // —— 审批段（进入执行段前）——
  // 申报：学生提交项目，status 0
  { key: 'declare', label: '项目申报', status: 0, segment: 'approval', icon: 'EditPen' },
  // 指导教师确认：status 12，教师确认后才进入学院初审
  { key: 'teacher', label: '指导教师确认', status: 12, segment: 'approval', icon: 'User' },
  // 学院初审：status 1，学院管理员审核
  { key: 'college', label: '学院初审', status: 1, segment: 'approval', icon: 'OfficeBuilding' },
  // 校级复审：status 3，学校管理部门审核
  { key: 'university', label: '校级复审', status: 3, segment: 'approval', icon: 'School' },
  // 专家评审：status 5，分配专家后进入评审
  { key: 'expert', label: '专家评审', status: 5, segment: 'approval', icon: 'Star' },
  // —— 执行段（立项之后）——
  // 项目立项：status 6，同时是执行段起点
  { key: 'approved', label: '项目立项', status: 6, segment: 'exec', icon: 'CircleCheck' },
  // 中期检查：status 7，教师参与审核
  { key: 'midterm', label: '中期检查', status: 7, segment: 'exec', icon: 'Calendar' },
  // 成果登记：立项后即可登记，与中期检查并行，不单独高亮
  { key: 'achievement', label: '成果登记', status: 6, segment: 'exec', icon: 'Medal' },
  // 结项验收：status 8，专家/管理员操作
  { key: 'final', label: '结项验收', status: 8, segment: 'exec', icon: 'Checked' },
  // 已结题：status 9，流程终点
  { key: 'finished', label: '已结题', status: 9, segment: 'exec', icon: 'CircleCheckFilled' },
]

// 阶段按功能归入侧边栏分组：审批段不再作为侧边栏阶段菜单，
// 统一由「审核工作台」（教师/管理员）与「待评审项目」（专家）入口承载，避免同名重复入口；
// 执行段在「项目管理」下以「已立项」父级菜单收拢（中期检查 / 结项验收）。
// project 组放申报入口；exec 组放执行段；review 组当前不直接挂阶段菜单。
const STAGE_GROUP_MAP: Record<string, string[]> = {
  project: ['declare'],
  exec: ['midterm', 'final'],
  review: [],
}

/**
 * 取某分组下的阶段列表
 * 处理内容：按 STAGE_GROUP_MAP 查 key → 关联 PROCESS_STAGES → 按角色过滤 → 合并流程进度。
 * 角色过滤规则：项目申报仅学生可见；结项验收仅非教师可见（专家/管理员）；
 *              执行段其余阶段常驻展示。
 * @param groupKey 侧边栏分组 key（workbench/project/review/system/resource）
 * @returns 带全局序号、isActive/isDone 的阶段数组，可直接用于菜单渲染
 */
function stagesOfGroup(groupKey: string) {
  // 先按分组映射取出阶段 key，再回查完整定义；未配置分组的 key 直接忽略
  const keys = STAGE_GROUP_MAP[groupKey] || []
  return keys
    .map((k) => PROCESS_STAGES.find((s) => s.key === k))
    .filter(Boolean)
    .filter((s) => {
      // 项目申报仅对学生显示（教师/管理员跳转目标与"我的项目"重复）
      if (s!.key === 'declare') return userStore.role === ROLES.STUDENT
      // 结项验收仅由评审专家/超级管理员操作，教师只参与中期检查审核
      if (s!.key === 'final') return !userStore.isTeacher
      // 执行段阶段（项目立项/中期检查/结项验收/已结题）常驻侧边栏展示
      return true
    })
    .map((s) => {
      // idx 为阶段在整个流程轴中的序号（从 1 开始），与是否进入菜单无关
      const idx = PROCESS_STAGES.findIndex((p) => p.key === s!.key)
      // full 为 processStages 计算出的当前进度；非详情页时不存在，按未高亮处理
      const full = processStages.value.find((p) => p.key === s!.key)
      return { ...s!, idx: idx + 1, isActive: full?.isActive || false, isDone: full?.isDone || false }
    })
}

// 「已立项」父级菜单下的子导航：中期检查 / 结项验收（已按角色过滤）
const execStages = computed(() => stagesOfGroup('exec'))

/**
 * 计算当前项目的流程进度（isDone / isActive）
 * 数据来源：processStore.projectStatus，仅项目详情页会写入；为 null 时全部阶段都不高亮。
 * 规则：状态 10/11（已驳回/已撤销）视为流程中断，所有阶段都不标记完成；
 *      其余状态按 DONE / ACTIVE 映射表判断，成果登记为并行节点不参与高亮。
 * 副作用：无，纯计算属性。
 */
const processStages = computed(() => {
  const cur = processStore.projectStatus
  // 非详情页：阶段列表始终显示，但无高亮
  if (cur === null) {
    return PROCESS_STAGES.map((s) => ({ ...s, isActive: false, isDone: false }))
  }
  const isRejected = cur === 10 || cur === 11
  const inFlow = (arr: number[]) => !isRejected && arr.includes(cur)
  // 审批段：指导教师确认(12)→学院初审(1/2)→校级复审(3/4)→专家评审(5)
  // 执行段：立项(6)→中期检查(7)→成果登记→结项验收(8)→已结题(9)
  // 成果登记为执行段的并行节点：立项后即可登记，中期检查通过（待结题8）后方视为完成。
  // DONE 表含义：只要当前状态已越过该阶段，就标记为完成（浅蓝色）。
  const DONE: Record<string, boolean> = {
    declare: true,
    teacher: inFlow([1, 2, 3, 4, 5, 6, 7, 8, 9]),
    college: inFlow([2, 3, 4, 5, 6, 7, 8, 9]),
    university: inFlow([4, 5, 6, 7, 8, 9]),
    expert: inFlow([6, 7, 8, 9]),
    approved: inFlow([6, 7, 8, 9]),
    midterm: inFlow([8, 9]),
    achievement: inFlow([8, 9]),
    final: inFlow([9]),
    finished: inFlow([9]),
  }
  // ACTIVE 表含义：当前正处于该阶段（主题色高亮），只允许一个主阶段同时高亮。
  const ACTIVE: Record<string, boolean> = {
    declare: cur === 0,
    teacher: cur === 12,
    college: cur === 1 || cur === 2,
    university: cur === 3 || cur === 4,
    expert: cur === 5,
    approved: false,
    midterm: cur === 7,
    // 成果登记为执行段并行节点（立项后即可登记），不作为"当前阶段"高亮，
    // 避免与「项目立项」「中期检查」同时亮起造成误导。
    achievement: false,
    final: cur === 8,
    finished: false,
  }
  return PROCESS_STAGES.map((s) => ({
    ...s,
    isDone: !!DONE[s.key],
    isActive: !!ACTIVE[s.key],
  }))
})

/**
 * 阶段 → 对应页面路由（非项目详情上下文点击时使用）
 * 按角色适配：学生申报走创建页；专家评审走待评审；其余审核阶段统一进审核工作台。
 * @param key PROCESS_STAGES 中的阶段 key
 * @returns 目标路由路径（可能携带 status 查询参数）
 */
function stageRoute(key: string): string {
  const role = userStore.role
  switch (key) {
    case 'declare':
      // 学生进申报页，其他角色看项目列表
      return role === 1 ? '/projects/create' : '/projects'
    case 'midterm':
      return '/projects?status=7'
    case 'achievement':
      return '/projects?status=6'
    case 'final':
      return '/projects?status=8'
    case 'teacher':
    case 'college':
    case 'university':
      // 审批段三个阶段共用审核工作台，具体待办列表由页面内 Tab 区分
      return '/review'
    case 'expert':
      // 专家进待评审，其他角色看待审核
      return role === 3 ? '/expert/pending' : '/review'
    default:
      return '/projects'
  }
}

/**
 * 处理流程阶段菜单点击
 * 分两种情况：
 *   1. 当前已在 /projects/:id 上下文：中期检查/成果登记/结项验收直接进入对应子页，
 *      其他阶段回到详情页并请求滚动定位；若处于独立子页需先回详情页，否则滚动请求无人监听。
 *   2. 非项目上下文：按 stageRoute 跳转到功能页面。
 * 副作用：路由跳转；详情页场景会调用 processStore.requestScroll。
 */
function handleStageClick(key: string) {
  // 已在项目上下文页面（详情页 / 中期检查 / 成果登记）
  if (route.path.startsWith('/projects/')) {
    // 动态路由参数 id 为空时无法拼接子页地址，退回该阶段的功能页
    const projectId = route.params.id
    if (!projectId) {
      router.push(stageRoute(key))
      return
    }
    if (key === 'midterm') {
      router.push(`/projects/${projectId}/midterm`)
      return
    }
    if (key === 'achievement') {
      router.push(`/projects/${projectId}/achievements`)
      return
    }
    if (key === 'final') {
      router.push(`/projects/${projectId}/final`)
      return
    }
    // 其余阶段（项目立项/已结题等）只在项目详情页内以区域展示：
    // 当前若处于独立子页（中期检查/成果登记），需先跳回详情页再滚动定位，
    // 否则 requestScroll 无人监听、点击无响应。
    const inSubPage = route.path.endsWith('/midterm') || route.path.endsWith('/achievements')
    if (inSubPage) {
      router.push({ path: `/projects/${projectId}`, query: { scroll: key } })
      return
    }
    // 已在详情页：直接滚动到对应区域
    processStore.requestScroll(key)
    return
  }
  // 非项目上下文：跳转到该阶段对应的功能页面
  router.push(stageRoute(key))
}

// ==================== 响应式布局状态 ====================
// isCollapse：PC 端侧边栏折叠；isMobile：是否窄屏（<768px）；drawerVisible：移动端抽屉显隐。
// 三个状态互相联动：移动端下 isCollapse 与 drawerVisible 互为取反，保证图标语义一致。
const isCollapse = ref(false)
const isMobile = ref(false)
const drawerVisible = ref(false)

/** 根据窗口宽度更新移动端标记；切到移动端时默认折叠 PC 侧边栏状态。 */
/** 只在跨越 768px 阈值时触发副作用，但当前实现每次都赋值，避免漏掉首次初始化。 */
function checkMobile() {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    isCollapse.value = true
  }
}

/**
 * 菜单选中统一入口
 * index 以 stage- 开头时交给阶段导航，否则按路由路径跳转；
 * 移动端选中后自动关闭抽屉，并滚动侧边栏让激活项可见。
 */
function handleMenuSelect(index: string) {
  // 流程阶段：交给统一阶段导航处理（index 形如 'stage-declare'）
  if (index.startsWith('stage-')) {
    // 去掉 stage- 前缀后才是 PROCESS_STAGES 的 key
    handleStageClick(index.slice('stage-'.length))
  } else {
    // 普通菜单项：index 已是 resolvePath 补全后的绝对路径
    router.push(index)
  }
  if (isMobile.value) {
    drawerVisible.value = false
  }
  // 点击菜单项后滚动到激活项
  scrollActiveIntoView()
}

/**
 * 自动滚动侧边栏，让当前激活菜单项可见（PC 端与移动端抽屉均适用）
 * 实现要点：最多轮询 10 次、每次 200ms，等待子菜单展开动画结束；
 *          激活项若在未展开的子菜单内，先触发其标题点击展开，再继续重试；
 *          用 getBoundingClientRect 判断是否超出菜单可视区，超出则平滑滚动到最近位置。
 * 副作用：可能触发子菜单点击展开与 DOM 滚动。
 */
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
        (parentSub.querySelector('.el-sub-menu__title') as HTMLElement | null)?.click()
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

// ==================== 菜单可视性监听 ====================
// 路由变化后重新计算激活项位置
// 只监听 path 而非整个 route 对象：同路径仅 query 变化（如状态筛选切换）时不需要重新滚动，
// 高亮本身由 activeMenu 计算属性响应式更新。
watch(() => route.path, scrollActiveIntoView)

// 项目详情页状态变化时（阶段高亮变化），也滚动到激活阶段
// 仅在项目上下文生效，其他页面没有阶段高亮，无需滚动
watch(() => processStore.projectStatus, () => {
  if (route.path.startsWith('/projects/')) {
    scrollActiveIntoView()
  }
})

// 移动端抽屉打开时，也滚动到激活项
watch(drawerVisible, (val) => {
  if (val) scrollActiveIntoView()
})

// 移动端折叠状态与抽屉显隐互相同步：
// isCollapse=true 时打开抽屉，isCollapse=false 时关闭抽屉。
// 双向 watch 均加 isMobile 判断，避免 PC 端折叠时误触发抽屉状态。
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

// ==================== 窗口尺寸监听 ====================
// 100ms 防抖，避免拖拽窗口时频繁触发移动端判定。
let resizeTimer: number | null = null
function onResize() {
  // 防抖：拖拽窗口时 resize 触发频繁，只在停止 100ms 后重新判断移动端
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(() => {
    checkMobile()
  }, 100)
}

// 挂载时初始化移动端标记并注册 resize 监听
// checkMobile 必须立即执行一次，否则首屏窄屏会先渲染 PC 侧边栏再切换，出现闪动
onMounted(() => {
  checkMobile()
  window.addEventListener('resize', onResize)
})

// 卸载时移除监听并清理未执行的防抖定时器，避免内存泄漏
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (resizeTimer) clearTimeout(resizeTimer)
})
// 当前路由对象的只读引用，供模板或后续计算使用
const currentRoute = computed(() => route)

// ==================== 主题与菜单高亮 ====================
// 深色模式使用近黑背景，浅色模式沿用经典深蓝侧边栏。
const sidebarBg = computed(() =>
  appearanceStore.isDark ? '#0a0a0a' : '#001529'
)

// 侧边栏高亮：普通菜单项按路由路径高亮；
// 当「我的项目」列表带阶段状态筛选（/projects?status=X）时，高亮对应的流程阶段项，避免与「我的项目」重复高亮
const activeMenu = computed(() => {
  if (route.path === '/projects') {
    // 状态筛选项与流程阶段菜单的映射：6 已立项→成果登记，7 中期检查中→中期检查，8 待结题→结项验收
    // 未列出的状态（如 1/3/5 审批中）仍高亮「我的项目」自身，不强行映射到审批阶段
    const statusMap: Record<string, string> = {
      '6': 'stage-achievement',
      '7': 'stage-midterm',
      '8': 'stage-final',
    }
    const q = route.query.status
    if (typeof q === 'string' && statusMap[q]) {
      return statusMap[q]
    }
  }
  // 「项目申报」高亮对应的流程阶段项（新建/编辑均走该路由）
  if (route.path === '/projects/create') {
    return 'stage-declare'
  }
  return route.path
})

/**
 * 按当前角色过滤布局子路由
 * 无 meta.roles 视为公开菜单项（登录后可见）；有 roles 则要求当前 role 命中。
 * 注意：此处只控制菜单展示，真正的访问鉴权仍在 router 守卫中执行。
 */
const filteredRoutes = computed(() => {
  // 读取静态路由表而非当前匹配链：详情页、创建页等动态路由不会因此进入菜单
  const children = router.options.routes.find((r) => r.path === '/')?.children || []
  return children.filter((child) => {
    // 有 meta.roles 时必须命中当前角色；无 roles 视为登录后通用菜单
    const roles = child.meta?.roles as number[] | undefined
    if (!roles) return true
    return roles.includes(userStore.role)
  })
})

// 侧边栏分组配置（顺序即显示顺序）：路由通过 meta.group 归属到对应分组
const MENU_GROUPS = [
  // 工作台：首页、个人中心
  { key: 'workbench', title: '工作台', icon: Monitor },
  // 项目管理：我的项目、报销、证书，以及申报/中期/结项等流程阶段
  { key: 'project', title: '项目管理', icon: Folder },
  // 审核中心：审核工作台（教师/管理员）与待评审项目（专家）
  { key: 'review', title: '审核中心', icon: Bell },
  // 系统管理：用户、全量项目、经费、统计、日志、学院、大赛、公告等管理端页面
  { key: 'system', title: '系统管理', icon: Setting },
  // 资源中心：大赛浏览、立项公示、归档项目库
  { key: 'resource', title: '资源中心', icon: Box },
]

/**
 * 按 group 分组过滤后的菜单路由
 * 规则：先排除 meta.hidden（详情页、创建页等不进入菜单），再按 meta.group 归组；
 *      空分组直接剔除，避免侧边栏出现无子项的空目录。
 */
const groupedRoutes = computed(() => {
  // 先剔除 hidden 路由，再按 group 归组；MENU_GROUPS 的数组顺序即侧边栏显示顺序
  const visible = filteredRoutes.value.filter((r) => !r.meta?.hidden)
  return MENU_GROUPS
    .map((g) => ({
      ...g,
      routes: visible.filter((r) => (r.meta?.group as string) === g.key),
    }))
    .filter((g) => g.routes.length > 0)
})

/**
 * 面包屑生成
 * 来源：router.getRoutes() 中带 meta.title 的路由 + 当前路径逐段匹配；
 *      首项固定为"首页"，匹配不到时退回当前路由 meta.title；
 *      最后一项不可点击（path 置空），其余项可跳转。
 * 注意：动态参数路径（如 projects/:id）不一定能逐段匹配，故保留兜底分支。
 */
const breadcrumbs = computed(() => {
  const result: { path: string; title: string; isLast: boolean }[] = []
  result.push({ path: '/', title: '首页', isLast: false })

  // 已注册路由表：用于把当前路径逐段还原成带标题的层级
  // getRoutes() 返回扁平化结果，因此直接用绝对 path 精确匹配即可
  const allRoutes = router.getRoutes()
  // 过滤空段，避免根路径产生空字符串
  const segments = route.path.split('/').filter(Boolean)
  // 逐段累加的路径，例如 /projects/1 → /projects → /projects/1
  let builtPath = ''
  // 匹配到的层级列表，最终再补首页与 isLast 标记
  const matchedList: { path: string; title: string }[] = []

  for (const seg of segments) {
    builtPath += '/' + seg
    const found = allRoutes.find((r) => r.path === builtPath && r.meta?.title)
    if (found && found.meta?.title) {
      matchedList.push({ path: builtPath, title: String(found.meta.title) })
    }
  }

  // 动态参数路径可能无法逐段命中，兜底使用当前路由自身的标题
  if (matchedList.length === 0 && route.meta?.title) {
    matchedList.push({ path: route.path, title: String(route.meta.title) })
  }

  // 逐项转换为面包屑项；只有最后一项不可点击
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

// 将子路由的相对 path 补全为以 / 开头的绝对路径，供 el-menu index 与 router.push 使用
// 当前路由表只有一层子路由，无需递归处理多级嵌套
function resolvePath(route: any): string {
  const base = '/'
  const path = route.path.startsWith('/') ? route.path.slice(1) : route.path
  return base + path
}

/**
 * 用户下拉菜单命令处理
 * profile：跳转个人中心；logout：二次确认后先等待 logout 清理登录态，再 replace 到登录页。
 * 注意：必须 await logout，否则守卫可能因旧 token 尚存而重定向到强制改密页。
 * 副作用：清空 token/localStorage 并触发路由跳转。
 */
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

// 浏览器全屏切换：未全屏时请求进入，已全屏时退出
// 浏览器可能因用户手势限制或权限策略拒绝请求，此时静默保持原状态，不阻断其他操作
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

/**
 * 侧边栏折叠按钮
 * PC 端切换 isCollapse；移动端切换抽屉显隐（同时通过 watch 同步 isCollapse）。
 */
function handleToggleSidebar() {
  if (isMobile.value) {
    drawerVisible.value = !drawerVisible.value
  } else {
    isCollapse.value = !isCollapse.value
  }
}
</script>

<style scoped>
/*
  样式组织：
    1. 颜色一律走 CSS 变量（--sidebar-color / --header-color / --bg-color / --el-color-primary），
       由 appearance store 在根节点切换，布局样式不直接判断主题，减少重复逻辑。
    2. 尺寸约定：品牌区与顶栏均 60px；PC 侧边栏 210px、折叠 64px；移动端抽屉 240px。
    3. 作用域：scoped 仅作用于本组件；需要穿透 Element Plus 内部结构时使用 :deep()。
    4. 断点统一 768px，与脚本中 checkMobile 的阈值保持一致，避免样式与逻辑不同步。
*/
/* 流程阶段菜单项：默认与普通菜单同色 */
.stage-menu-item {
  color: #bfcbd9;
}
/* 悬停时给一层轻微高亮 */
.stage-menu-item:hover {
  background-color: rgba(255, 255, 255, 0.08);
}
/* 当前阶段：使用主题色并加粗 */
/* 仅一个阶段应为 is-active；若出现多个，说明状态映射有重叠，需要回查 ACTIVE 表 */
.stage-menu-item.is-active {
  color: var(--el-color-primary);
  font-weight: 600;
}
/* 已完成阶段：浅蓝色弱化展示，区别于当前阶段 */
.stage-menu-item.is-done {
  color: #a0cfff;
}
/* 布局根容器：锁定一屏高度，内容区内部滚动 */
/* 100vh 而非 100%：保证在任意父级高度下都能撑满视口，避免内容区高度塌陷 */
.layout-container {
  height: 100vh;
  overflow: hidden;
}

/* 侧边栏：纵向 flex，宽度与背景色变化带过渡；内容超出时内部滚动 */
/* overflow hidden 防止折叠动画过程中出现横向滚动条 */
.sidebar {
  background-color: var(--sidebar-color, #001529);
  transition: width 0.3s ease, background-color 0.3s ease;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 移动端抽屉内的侧边栏占满抽屉高度 */
.sidebar-mobile {
  height: 100%;
}

/* 品牌区：固定 60px 高，与顶栏高度对齐；折叠时只保留 logo */
/* border-bottom 与侧边栏背景形成轻微分层，避免 logo 区与菜单区混在一起 */
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

/* logo：圆角方形，折叠时尺寸略放大以填满窄栏 */
.logo-img {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  transition: width 0.3s ease, height 0.3s ease;
}

/* 折叠态 logo：40px，接近窄栏宽度 */
/* 折叠后侧边栏仅 64px，logo 适当放大可避免视觉上过于空旷 */
.logo-img.collapsed {
  width: 40px;
  height: 40px;
}

/* 平台名称：单行不换行，折叠时隐藏 */
.logo-text {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  transition: opacity 0.3s ease;
  opacity: 1;
}

/* 折叠态隐藏文字，仅保留 logo */
.logo-text.collapsed {
  display: none;
}

/* 菜单滚动容器：去掉 Element 默认右边框，纵向可滚动、横向隐藏 */
/* flex:1 让菜单吃掉品牌区之外的剩余高度，菜单项过多时只滚动菜单本身 */
.el-menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

/* 顶栏：左右两端对齐，背景与边框随主题切换 */
/* 高度由 el-header 默认的 60px 决定，与品牌区高度对齐，形成一条水平分界线 */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--header-color, #fff);
  border-bottom: 1px solid var(--header-border-color, #e6e6e6);
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  transition: background 0.3s ease, border-color 0.3s ease;
}

/* 左侧：折叠按钮 + 面包屑，横向排列 */
/* 面包屑在移动端被模板隐藏，此处间距只影响 PC 端 */
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 折叠按钮：20px 图标，扩大点击热区由父级布局保证 */
.collapse-btn {
  font-size: 20px;
  cursor: pointer;
  color: #5a5e66;
}

/* 深色模式下提高折叠按钮亮度 */
/* 与动作图标使用同一提亮色，保证顶栏所有图标在深色背景下视觉一致 */
:deep(html.dark) .collapse-btn {
  color: #cfd3dc;
}

/* 面包屑字体：略小于正文，避免抢视觉焦点 */
/* 面包屑由 Element Plus 自带分隔符，颜色继承全局文字色，无需额外覆盖 */
.breadcrumb {
  font-size: 14px;
}

/* 右侧操作区：图标之间 20px 间距，保持呼吸感 */
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

/* 通用动作图标：18px，颜色与折叠按钮一致 */
/* 统一尺寸避免顶栏图标大小不一；transition 只作用于颜色，悬停不产生位移 */
.action-item {
  font-size: 18px;
  cursor: pointer;
  color: #5a5e66;
  transition: color 0.2s;
}
/* 盲审开启时用警告色标记，提醒当前处于信息隐藏状态 */
.action-item.blind-active {
  color: var(--el-color-warning);
}

/* 深色模式下动作图标提亮 */
:deep(html.dark) .action-item {
  color: #cfd3dc;
}

/* 用户信息区：头像、姓名、角色标签横向排列，整体可点击 */
/* 移动端只保留头像，姓名与角色标签由模板中的 v-if 隐藏，此处不重复处理 */
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

/* 用户名：14px，使用主题文字色 */
/* 姓名过长时不换行，靠顶栏整体空间与移动端隐藏来规避溢出 */
.user-name {
  font-size: 14px;
  color: var(--text-color, #333);
}

/* 内容区：独立纵向滚动，横向隐藏，背景随主题切换 */
/* 与侧边栏配合形成"外层不滚动、内层各自滚动"的双滚动结构 */
.main-content {
  background: var(--bg-color, #f0f2f5);
  padding: 20px;
  overflow-y: auto;
  overflow-x: hidden;
  transition: background 0.3s ease;
}

/* 路由切换过渡：0.2s 淡入淡出，减少页面跳变感 */
/* 只过渡 opacity，避免触发布局重排；进出时长与内容区刷新节奏保持轻量 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
/* 过渡起始/结束：完全透明 */
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 移动端抽屉：去掉默认内边距，让菜单贴边铺满 */
/* :deep 穿透抽屉内部 body 节点，否则 scoped 样式无法命中 teleport 到 body 的弹层 */
/* modal-class 控制遮罩层样式，class 控制抽屉面板本身，二者不要混用 */
:deep(.mobile-drawer .el-drawer__body) {
  padding: 0;
}

/* 移动端适配：收紧顶栏与内容区间距，提升小屏可用宽度 */
/* 仅调整间距与内边距，不改布局结构与断点，保持与 JS 的 768px 判定一致 */
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
