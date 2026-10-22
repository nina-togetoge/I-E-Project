<!--
  首页 Dashboard
  根据角色显示差异化内容
-->
<template>
  <div class="dashboard">
    <!-- 欢迎卡片 -->
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

    <!-- 统计卡片 -->
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

    <!-- 快捷入口 -->
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

    <!-- 管理员数据概览 -->
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

const currentTime = ref('')
const currentDate = ref('')
let timer: number

function updateTime() {
  const now = new Date()
  const days = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  currentDate.value = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ${days[now.getDay()]}`
  currentTime.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
}

timer = window.setInterval(updateTime, 1000)

onBeforeUnmount(() => clearInterval(timer))

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

// 统计数据
const stats = ref({
  total_projects: 0,
  approved_projects: 0,
  finished_projects: 0,
  total_budget: 0,
  pending_review: 0,
  expense_count: 0,
})

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

// 快捷入口按角色过滤：目标路由的 meta.roles 必须包含当前角色，否则会跳 403
// （/projects→[1,2]，/projects/create 仅学生使用，/expenses→[1]，
//   /admin/expenses→[2,4]，/expert/pending→[3]，其余管理页→[4]）
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

// 图表配置
const statusChartOption = shallowRef<echarts.EChartsOption>({} as echarts.EChartsOption)
const trendChartOption = shallowRef<echarts.EChartsOption>({} as echarts.EChartsOption)

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
