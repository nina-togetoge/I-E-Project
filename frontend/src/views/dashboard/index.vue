<!--
  页面名称：首页 Dashboard（当前位于 views/dashboard/index.vue）
  面向角色：全部已登录角色（学生 / 教师 / 专家 / 管理员），内容按角色差异化
  功能：
    1. 欢迎卡片：头像、问候语、姓名、学院、角色、日期与实时时钟
    2. 角色化统计卡片：管理员看项目/立项/结题/经费；学生看我的项目/报销/待办；
       专家看待处理/评审项目；教师看待处理/指导项目/报销
    3. 快捷入口：按角色过滤可用路由，避免进入无权限页面
    4. 管理员额外展示：项目状态分布饼图、月度申报趋势折线图
  调用 API：
    - GET  /api/statistics/overview：项目统计，后端按当前用户数据权限过滤
    - GET  /api/statistics/trend：月度申报趋势（仅管理员加载图表）
    - POST /api/expenses/list：只取 total 作为报销申请数量（学生 / 教师）
  权限 / 数据范围：
    - 所有统计由后端按角色与学院过滤，前端不额外传学院参数
    - 快捷入口依据路由 meta.roles 与当前角色做前端过滤，防止点击后跳 403
  关键交互：
    - 时钟每秒刷新，组件卸载时清理定时器
    - 统计加载失败时静默降级为 0，不阻塞页面；报销数量仅对学生/教师请求
    - 管理员的状态饼图与趋势图在同一个加载流程里赋值，切换角色登录不会渲染
-->
<template>
  <div class="dashboard">
    <!--
      欢迎卡片
      头像优先使用用户头像，缺省时用姓名首字；学院名取 displayCollegeName（无学院时回退学校名）。
      greeting 按当前小时计算，时间与日期由定时器每秒/每分钟更新。
    -->
    <el-card class="welcome-card" shadow="never">
      <div class="welcome-content">
        <el-avatar :size="60" :src="userStore.userInfo?.avatar || undefined">
          {{ userStore.userInfo?.real_name?.[0] || 'U' }}
        </el-avatar>
        <div class="welcome-info">
          <h2>{{ greeting }}，{{ userStore.userInfo?.real_name }}</h2>
          <p>
            {{ userStore.displayCollegeName || '暂无学院' }} ·
            <el-tag size="small">{{ userStore.roleName }}</el-tag>
          </p>
        </div>
        <div class="welcome-time">
          <p>{{ currentDate }}</p>
          <p class="time">{{ currentTime }}</p>
        </div>
      </div>
    </el-card>

    <!--
      角色化统计卡片
      statCards 是 computed：不同角色返回不同的指标名称与图标，但复用同一份 stats。
      数值为 0 时 CountNumber 仍正常展示，避免接口失败造成空白。
    -->
    <el-row :gutter="20" class="stat-row">
      <el-col v-for="card in statCards" :key="card.label" :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" :style="{ background: card.color }">
              <el-icon :size="28"><component :is="card.icon" /></el-icon>
            </div>
            <div class="stat-info">
              <p class="stat-value"><CountNumber :value="card.value" /></p>
              <p class="stat-label">{{ card.label }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!--
      快捷入口
      quickEntries 是 computed，按当前角色生成：只保留该角色有权访问的路径，
      路由守卫会再次校验角色；每个入口 span=4，即一行最多展示 6 个。
    -->
    <el-card shadow="never" class="quick-entry">
      <template #header>
        <span>快捷入口</span>
      </template>
      <el-row :gutter="16">
        <el-col v-for="entry in quickEntries" :key="entry.path" :span="4">
          <div class="entry-item" @click="router.push(entry.path)">
            <el-icon :size="32" :color="entry.color">
              <component :is="entry.icon" />
            </el-icon>
            <p>{{ entry.label }}</p>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!--
      管理员数据概览
      只有管理员渲染：左侧状态饼图使用 stats 中的立项/结题/待审核数量，
      右侧趋势折线使用 getTrend 返回的按月申请数；非管理员不请求趋势接口。
      图表 option 用 shallowRef 保存，整体替换即可触发 EChart 更新，避免深层响应式开销。
    -->
    <el-row v-if="userStore.isAdmin" :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>项目状态分布</span></template>
          <EChart :option="statusChartOption" height="300px" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>月度申报趋势</span></template>
          <EChart :option="trendChartOption" height="300px" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { useRouter } from 'vue-router'
import {
  Document, Files, Wallet, EditPen, Bell, DataAnalysis, Box, UserFilled
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { getStatistics, getTrend } from '@/api/project'
import { post } from '@/utils/request'
import EChart from '@/components/EChart.vue'
import CountNumber from '@/components/CountNumber.vue'

const router = useRouter()
const userStore = useUserStore()

// ==================== 时钟 ====================
// 顶栏时间展示；timer 保存定时器句柄，卸载时清理
const currentTime = ref('')
const currentDate = ref('')
let timer: number

/** 刷新日期与时间：日期带星期，时间补零到 HH:mm:ss */
function updateTime() {
  const now = new Date()
  const days = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  currentDate.value = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ${days[now.getDay()]}`
  currentTime.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
}

timer = window.setInterval(updateTime, 1000)

onBeforeUnmount(() => clearInterval(timer))

// ==================== 问候语 ====================
// 按当前小时分段返回中文问候；不依赖接口，因此登录后立即可用
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '凌晨好'
  if (h < 9) return '早上好'
  if (h < 12) return '上午好'
  if (h < 14) return '中午好'
  if (h < 17) return '下午好'
  if (h < 19) return '傍晚好'
  return '晚上好'
})

// ==================== 统计数据 ====================
// 概览数据：字段与 /api/statistics/overview 对齐；不同角色复用的字段含义由后端按数据范围解释
const stats = ref({
  total_projects: 0,
  approved_projects: 0,
  finished_projects: 0,
  total_budget: 0,
  pending_review: 0,
  expense_count: 0,
})

// 统计卡片按角色分支：管理员看全校汇总；学生/教师看本人/本院项目与报销；
// 专家只看待处理与评审相关数量。最后 else 分支作为教师默认展示。
const statCards = computed(() => {
  if (userStore.isAdmin) {
    return [
      { label: '项目总数', value: stats.value.total_projects, icon: Files, color: '#409EFF' },
      { label: '已立项', value: stats.value.approved_projects, icon: Document, color: '#67C23A' },
      { label: '已结题', value: stats.value.finished_projects, icon: Box, color: '#E6A23C' },
      { label: '经费总额(¥)', value: Number(stats.value.total_budget || 0).toLocaleString(), icon: Wallet, color: '#F56C6C' },
    ]
  } else if (userStore.isStudent) {
    return [
      { label: '我的项目', value: stats.value.total_projects, icon: Files, color: '#409EFF' },
      { label: '已立项', value: stats.value.approved_projects, icon: Document, color: '#67C23A' },
      { label: '报销申请', value: stats.value.expense_count, icon: Wallet, color: '#E6A23C' },
      { label: '待办事项', value: stats.value.pending_review, icon: Bell, color: '#F56C6C' },
    ]
  } else if (userStore.isExpert) {
    return [
      { label: '待处理', value: stats.value.pending_review, icon: Bell, color: '#409EFF' },
      { label: '评审项目', value: stats.value.total_projects, icon: Files, color: '#67C23A' },
      { label: '已立项', value: stats.value.approved_projects, icon: Document, color: '#E6A23C' },
      { label: '已结题', value: stats.value.finished_projects, icon: Box, color: '#F56C6C' },
    ]
  } else {
    return [
      { label: '待处理', value: stats.value.pending_review, icon: Bell, color: '#409EFF' },
      { label: '指导项目', value: stats.value.total_projects, icon: Files, color: '#67C23A' },
      { label: '已立项', value: stats.value.approved_projects, icon: Document, color: '#E6A23C' },
      { label: '报销申请', value: stats.value.expense_count, icon: Wallet, color: '#F56C6C' },
    ]
  }
})

// ==================== 快捷入口 ====================
// 快捷入口按角色过滤：目标路由的 meta.roles 必须包含当前角色，否则会跳 403
// （/projects→[1,2]，/projects/create 仅学生使用，/expenses→[1]，
//   /admin/expenses→[2,4]，/expert/pending→[3]，其余管理页→[4]）
// 「归档项目库」对所有角色开放，因此不需要额外角色判断；管理员再追加看板与用户管理。
const quickEntries = computed(() => {
  const entries: { label: string; path: string; icon: any; color: string }[] = []
  if (userStore.isStudent || userStore.isTeacher) {
    entries.push({ label: '我的项目', path: '/projects', icon: Files, color: '#409EFF' })
  }
  if (userStore.isStudent) {
    entries.push(
      { label: '项目申报', path: '/projects/create', icon: EditPen, color: '#67C23A' },
      { label: '报销申请', path: '/expenses', icon: Wallet, color: '#E6A23C' },
    )
  }
  if (userStore.isExpert) {
    entries.push({ label: '待评审项目', path: '/expert/pending', icon: Document, color: '#409EFF' })
  }
  if (userStore.isTeacher || userStore.isAdmin) {
    entries.push({ label: '经费管理', path: '/admin/expenses', icon: Wallet, color: '#E6A23C' })
  }
  entries.push({ label: '归档项目库', path: '/admin/archive', icon: Box, color: '#909399' })
  if (userStore.isAdmin) {
    entries.push(
      { label: '数据看板', path: '/admin/statistics', icon: DataAnalysis, color: '#F56C6C' },
      { label: '用户管理', path: '/admin/users', icon: UserFilled, color: '#9B59B6' },
    )
  }
  return entries
})

// ==================== 管理员图表配置 ====================
// 用 shallowRef 存 option：ECharts 配置对象层级深，整体替换即可驱动更新，
// 同时避免 Vue 递归代理带来额外开销。
const statusChartOption = shallowRef<echarts.EChartsOption>({} as echarts.EChartsOption)
const trendChartOption = shallowRef<echarts.EChartsOption>({} as echarts.EChartsOption)

/**
 * 加载首页统计与图表
 * 1) 所有角色都请求 overview，后端按数据权限返回各自范围；
 * 2) 学生/教师额外请求报销列表，只取 total 作为报销数量，page_size=1 减少传输；
 * 3) 管理员再请求趋势并生成状态饼图与趋势折线。
 * 失败处理：每个请求独立 try/catch 且静默失败，保持已有值（通常为 0），
 *   首页作为入口页不应因统计接口异常而弹出错误或白屏。
 */
async function loadStatistics() {
  try {
    // 所有角色都加载项目统计（API 内部按数据权限过滤）
    const statsRes = await getStatistics()
    stats.value = {
      total_projects: statsRes.data.total_projects || 0,
      approved_projects: statsRes.data.approved_projects || 0,
      finished_projects: statsRes.data.finished_projects || 0,
      total_budget: statsRes.data.total_budget || 0,
      pending_review: statsRes.data.pending_review || 0,
      expense_count: stats.value.expense_count,
    }
  } catch {}

  // 报销申请数量（学生和教师；专家/管理员无报销业务）
  if (userStore.isStudent || userStore.isTeacher) {
    try {
      const res: any = await post('/api/expenses/list', {}, { params: { page: 1, page_size: 1 } })
      stats.value.expense_count = res?.data?.total || 0
    } catch {}
  }

  // 管理员额外加载趋势图表
  if (userStore.isAdmin) {
    try {
      const trendRes = await getTrend()
      const trend = (trendRes.data || []) as any[]
      statusChartOption.value = {
        tooltip: { trigger: 'item' },
        legend: { bottom: 0 },
        series: [{
          type: 'pie',
          radius: ['40%', '70%'],
          data: [
            { name: '已立项', value: stats.value.approved_projects },
            { name: '已结题', value: stats.value.finished_projects },
            { name: '待审核', value: stats.value.pending_review },
          ],
          itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
        }],
      }
      trendChartOption.value = {
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: trend.map((d: any) => d.period) },
        yAxis: { type: 'value' },
        series: [{
          type: 'line',
          data: trend.map((d: any) => d.apply_count),
          smooth: true,
          areaStyle: { opacity: 0.3 },
          itemStyle: { color: '#409EFF' },
        }],
      }
    } catch {}
  }
}

// ==================== 初始化 ====================
// 先立即刷新一次时钟（定时器首次触发在 1 秒后），再加载统计数据
onMounted(() => {
  updateTime()
  loadStatistics()
})
</script>

<style scoped>
.welcome-card {
  margin-bottom: 20px;
}

.welcome-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.welcome-info {
  flex: 1;
}

.welcome-info h2 {
  font-size: 20px;
  color: #303133;
  margin-bottom: 8px;
}

.welcome-info p {
  font-size: 14px;
  color: #909399;
}

.welcome-time {
  text-align: right;
}

.welcome-time p {
  font-size: 14px;
  color: #606266;
}

.welcome-time .time {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.stat-row {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.entry-item {
  text-align: center;
  cursor: pointer;
  padding: 16px 0;
  border-radius: 8px;
  transition: background 0.3s;
}

.entry-item:hover {
  background: #f5f7fa;
}

.entry-item p {
  font-size: 13px;
  color: #606266;
  margin-top: 8px;
}
</style>
