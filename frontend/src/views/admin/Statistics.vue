<!--
  数据统计看板（管理员端）
  ECharts 多维度图表：申报趋势折线图、学院立项率柱状图、类别饼图、经费仪表盘
  支持时间/学院/类别筛选，一键导出Excel
-->
<template>
  <div class="page-container">
    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filterForm">
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filterForm.dateRange"
            type="daterange"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item label="学院">
          <el-select v-model="filterForm.college_id" placeholder="全部学院" clearable style="width: 150px">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="filterForm.category" placeholder="全部类别" clearable style="width: 130px">
            <el-option label="创新训练" :value="1" />
            <el-option label="创业训练" :value="2" />
            <el-option label="创业实践" :value="3" />
            <el-option label="创新竞赛" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="loadData">查询</el-button>
          <el-button :icon="Download" @click="handleExport">导出 Excel</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 核心指标卡片 -->
    <el-row :gutter="20" class="stat-row">
      <el-col :span="6" v-for="card in statCards" :key="card.label">
        <el-card shadow="hover">
          <div class="stat-card">
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

    <!-- 图表区 -->
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>年度申报趋势</span></template>
          <EChart :option="trendOption" height="350px" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>各学院立项率</span></template>
          <EChart :option="collegeOption" height="350px" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>项目类别分布</span></template>
          <EChart :option="categoryOption" height="300px" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>经费使用率</span></template>
          <EChart :option="budgetOption" height="300px" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>项目状态分布</span></template>
          <EChart :option="statusOption" height="300px" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Download, Files, Document, Box, Wallet } from '@element-plus/icons-vue'
import EChart from '@/components/EChart.vue'
import { getStatistics, exportProjects } from '@/api/project'
import { getColleges } from '@/api/auth'
import * as XLSX from 'xlsx'
import { saveAs } from 'file-saver'

// ==================== 筛选 ====================
const filterForm = reactive({
  dateRange: [] as string[],
  college_id: undefined as number | undefined,
  category: undefined as number | undefined,
})

const colleges = ref<any[]>([])

// ==================== 统计数据 ====================
const stats = ref({
  total_projects: 0,
  approved_projects: 0,
  archived_projects: 0,
  total_budget: 0,
  approval_rate: 0,
  by_category: [] as { name: string; value: number }[],
  by_college: [] as { name: string; value: number }[],
  by_status: [] as { name: string; value: number }[],
  trend_by_month: [] as { month: string; count: number }[],
})

const statCards = computed(() => [
  { label: '申报总数', value: stats.value.total_projects, icon: Files, color: '#409EFF' },
  { label: '立项数', value: stats.value.approved_projects, icon: Document, color: '#67C23A' },
  { label: '结题数', value: stats.value.archived_projects, icon: Box, color: '#E6A23C' },
  { label: '经费总额(¥)', value: stats.value.total_budget.toLocaleString(), icon: Wallet, color: '#F56C6C' },
])

// ==================== 图表配置 ====================
const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: stats.value.trend_by_month.map((d) => d.month) },
  yAxis: { type: 'value' },
  series: [{
    name: '申报数量',
    type: 'line',
    data: stats.value.trend_by_month.map((d) => d.count),
    smooth: true,
    areaStyle: { opacity: 0.3 },
    itemStyle: { color: '#409EFF' },
  }],
}))

const collegeOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: stats.value.by_college.map((d) => d.name), axisLabel: { rotate: 30 } },
  yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
  series: [{
    type: 'bar',
    data: stats.value.by_college.map((d) => d.value),
    itemStyle: { color: '#67C23A' },
    label: { show: true, position: 'top', formatter: '{c}%' },
  }],
}))

const categoryOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie',
    radius: ['40%', '70%'],
    data: stats.value.by_category,
    itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
    label: { formatter: '{b}: {d}%' },
  }],
}))

const budgetOption = computed(() => ({
  series: [{
    type: 'gauge',
    progress: { show: true, width: 18 },
    axisLine: { lineStyle: { width: 18 } },
    detail: { formatter: '{value}%', fontSize: 24, offsetCenter: [0, '70%'] },
    data: [{ value: Math.round(stats.value.approval_rate), name: '立项率' }],
  }],
}))

const statusOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { type: 'scroll', bottom: 0 },
  series: [{
    type: 'pie',
    radius: '60%',
    data: stats.value.by_status,
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
  }],
}))

// ==================== 数据加载 ====================
async function loadData() {
  const params: any = {}
  if (filterForm.dateRange.length === 2) {
    params.start_date = filterForm.dateRange[0]
    params.end_date = filterForm.dateRange[1]
  }
  if (filterForm.college_id) params.college_id = filterForm.college_id
  if (filterForm.category) params.category = filterForm.category

  try {
    const res = await getStatistics(params)
    stats.value = res.data
  } catch {
    ElMessage.error('数据加载失败')
  }
}

// ==================== 导出 ====================
async function handleExport() {
  try {
    // 生成 Excel
    const wb = XLSX.utils.book_new()
    
    // 统计概览
    const overviewData = [
      ['指标', '数值'],
      ['申报总数', stats.value.total_projects],
      ['立项数', stats.value.approved_projects],
      ['结题数', stats.value.archived_projects],
      ['经费总额', stats.value.total_budget],
      ['立项率', `${stats.value.approval_rate}%`],
    ]
    const ws1 = XLSX.utils.aoa_to_sheet(overviewData)
    XLSX.utils.book_append_sheet(wb, ws1, '统计概览')

    // 学院分布
    const collegeData = [['学院', '立项率(%)']]
    stats.value.by_college.forEach((d) => collegeData.push([d.name, d.value]))
    const ws2 = XLSX.utils.aoa_to_sheet(collegeData)
    XLSX.utils.book_append_sheet(wb, ws2, '学院分布')

    // 类别分布
    const categoryData = [['类别', '数量']]
    stats.value.by_category.forEach((d) => categoryData.push([d.name, d.value]))
    const ws3 = XLSX.utils.aoa_to_sheet(categoryData)
    XLSX.utils.book_append_sheet(wb, ws3, '类别分布')

    // 趋势
    const trendData = [['月份', '申报数量']]
    stats.value.trend_by_month.forEach((d) => trendData.push([d.month, d.count]))
    const ws4 = XLSX.utils.aoa_to_sheet(trendData)
    XLSX.utils.book_append_sheet(wb, ws4, '月度趋势')

    const buf = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    saveAs(new Blob([buf]), '统计报表.xlsx')
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

// ==================== 初始化 ====================
onMounted(async () => {
  const res = await getColleges()
  colleges.value = res.data || []
  loadData()
})
</script>

<style scoped>
.filter-card { margin-bottom: 16px; }
.stat-row { margin-bottom: 20px; }
.stat-card { display: flex; align-items: center; gap: 16px; }
.stat-icon { width: 56px; height: 56px; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #fff; }
.stat-value { font-size: 24px; font-weight: 600; color: #303133; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
</style>
