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
            {{ userStore.userInfo?.college_name || '暂无学院' }} ·
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
              <p class="stat-value">{{ card.value }}</p>
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
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import {
  Document, Files, Wallet, TrendCharts, EditPen, Bell, DataAnalysis, Box
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { getStatistics, getTrend } from '@/api/project'
import EChart from '@/components/EChart.vue'

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
      { label: '我的项目', value: '-', icon: Files, color: '#409EFF' },
      { label: '已立项', value: '-', icon: Document, color: '#67C23A' },
      { label: '报销申请', value: '-', icon: Wallet, color: '#E6A23C' },
      { label: '待办事项', value: '-', icon: Bell, color: '#F56C6C' },
    ]
  } else {
    return [
      { label: '待处理', value: '-', icon: Bell, color: '#409EFF' },
      { label: '指导项目', value: '-', icon: Files, color: '#67C23A' },
      { label: '已审核', value: '-', icon: Document, color: '#E6A23C' },
      { label: '本月评审', value: '-', icon: TrendCharts, color: '#F56C6C' },
    ]
  }
})

const quickEntries = computed(() => {
  const entries = [
    { label: '我的项目', path: '/projects', icon: Files, color: '#409EFF' },
    { label: '项目申报', path: '/projects/create', icon: EditPen, color: '#67C23A' },
    { label: '报销申请', path: '/expenses', icon: Wallet, color: '#E6A23C' },
    { label: '归档项目库', path: '/admin/archive', icon: Box, color: '#909399' },
  ]
  if (userStore.isAdmin) {
    entries.push(
      { label: '数据看板', path: '/admin/statistics', icon: DataAnalysis, color: '#F56C6C' },
      { label: '用户管理', path: '/admin/users', icon: 'UserFilled', color: '#9B59B6' },
    )
  }
  return entries
})

// 图表配置
const statusChartOption = ref<any>({})
const trendChartOption = ref<any>({})

async function loadStatistics() {
  if (!userStore.isAdmin) return
  try {
    const [statsRes, trendRes] = await Promise.all([
      getStatistics(),
      getTrend(),
    ])
    stats.value = {
      total_projects: statsRes.data.total_projects || 0,
      approved_projects: statsRes.data.approved_projects || 0,
      finished_projects: statsRes.data.finished_projects || 0,
      total_budget: statsRes.data.total_budget || 0,
      pending_review: statsRes.data.pending_review || 0,
    }

    const trend = (trendRes.data || []) as any[]
    statusChartOption.value = {
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        data: [
          { name: '已立项', value: statsRes.data.approved_projects || 0 },
          { name: '已结题', value: statsRes.data.finished_projects || 0 },
          { name: '待审核', value: statsRes.data.pending_review || 0 },
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
