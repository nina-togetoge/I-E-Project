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
          <el-select
            v-model="filterForm.college_id"
            :placeholder="userStore.isCollegeAdmin ? '本院' : '全部学院'"
            :clearable="!userStore.isCollegeAdmin"
            :disabled="userStore.isCollegeAdmin"
            style="width: 150px"
          >
            <el-option v-for="c in colleges" :key="c.id" :label="c.college_name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="filterForm.project_type" placeholder="全部类别" clearable style="width: 130px">
            <el-option label="创新训练" :value="1" />
            <el-option label="创业训练" :value="2" />
            <el-option label="创业实践" :value="3" />
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
              <p class="stat-value"><CountNumber :value="card.value" /></p>
              <p class="stat-label">{{ card.label }}</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区 第1行：趋势图 + 学院图 -->
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

    <!-- 图表区 新增行：U6雷达图 + U8图表下钻占位 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>学院5维能力雷达图</span></template>
          <EChart :option="radarOption" height="350px" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>项目经费使用分布</span></template>
          <EChart :option="budgetDistOption" height="350px" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区 第3行：类别+预算+状态 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>项目类别分布</span></template>
          <EChart :option="categoryOption" :clickable="true" @click="handleChartDrill" height="300px" />
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
          <EChart :option="statusOption" :clickable="true" @click="handleChartDrill" height="300px" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区 新增行：U5桑基图 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span>项目全流程转化漏斗（桑基图）</span></template>
          <EChart :option="sankeyOption" height="420px" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区 新增行：F17学院综合实力热力图 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card shadow="never">
          <template #header><span>学院综合实力热力图</span></template>
          <EChart :option="heatmapOption" height="480px" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import type { EChartsOption } from 'echarts'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Download, Files, Document, Box, Wallet } from '@element-plus/icons-vue'
import EChart from '@/components/EChart.vue'
import CountNumber from '@/components/CountNumber.vue'
import { getStatistics, getTrend, getCollegeBreakdown } from '@/api/project'
import { getColleges } from '@/api/auth'
import * as XLSX from 'xlsx'
import { saveAs } from 'file-saver'
import { useAppearanceStore } from '@/store/appearance'
import { useUserStore } from '@/store/user'

const router = useRouter()
const appearanceStore = useAppearanceStore()
const userStore = useUserStore()

// ==================== 筛选 ====================
const filterForm = reactive({
  dateRange: [] as string[],
  college_id: undefined as number | undefined,
  project_type: undefined as number | undefined,
})

const colleges = ref<any[]>([])

// ==================== 统计数据 ====================
const stats = ref({
  total_projects: 0,
  pending_review: 0,
  approved_projects: 0,
  finished_projects: 0,
  total_budget: 0,
  total_used: 0,
  approval_rate: 0,
})

// 趋势数据（单独接口）
const trendData = ref<{ period: string; apply_count: number; approved_count: number }[]>([])

// 各学院统计数据（雷达图/热力图/学院立项率）
const collegeStats = ref<any[]>([])

// 后端返回的真实分布数据
const categoryDist = ref<{ name: string; value: number }[]>([])
const statusDist = ref<{ name: string; value: number; status: number }[]>([])
const budgetByCategory = ref<{ name: string; amount: number }[]>([])

const statCards = computed(() => [
  { label: '申报总数', value: stats.value.total_projects, icon: Files, color: '#409EFF' },
  { label: '待审核', value: stats.value.pending_review, icon: Document, color: '#E6A23C' },
  { label: '已立项', value: stats.value.approved_projects, icon: Box, color: '#67C23A' },
  { label: '经费总额(¥)', value: Number(stats.value.total_budget || 0).toLocaleString(), icon: Wallet, color: '#F56C6C' },
])

// ==================== 图表配置 ====================
const trendOption = computed((): EChartsOption => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: (trendData.value || []).map((d) => d.period) },
  yAxis: { type: 'value' },
  series: [
    {
      name: '申报数',
      type: 'line',
      data: (trendData.value || []).map((d) => d.apply_count),
      smooth: true,
      itemStyle: { color: '#409EFF' },
    },
    {
      name: '立项数',
      type: 'line',
      data: (trendData.value || []).map((d) => d.approved_count),
      smooth: true,
      itemStyle: { color: '#67C23A' },
    },
  ],
}))

const collegeOption = computed((): EChartsOption => {
  const colleges = collegeStats.value || []
  return {
    tooltip: { trigger: 'axis', formatter: '{b}: {c}%' },
    xAxis: { type: 'category', data: colleges.map((c) => c.college_name), axisLabel: { rotate: 30, fontSize: 11 } },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [{
      type: 'bar',
      data: colleges.map((c) => Math.round(c.approval_rate || 0)),
      itemStyle: { color: '#67C23A' },
      label: { show: true, position: 'top', formatter: '{c}%' },
    }],
  }
})

// U6 学院5维能力雷达图（真实数据：取项目数前5的学院）
const radarOption = computed((): EChartsOption => {
  const themeColor = appearanceStore.themeColor
  const colors = [themeColor, '#67C23A', '#E6A23C', '#F56C6C', '#909399']
  const topColleges = [...(collegeStats.value || [])]
    .sort((a, b) => b.total_projects - a.total_projects)
    .slice(0, 5)
  return {
    tooltip: {},
    legend: {
      data: topColleges.map((c) => c.college_name),
      bottom: 0,
    },
    radar: {
      indicator: [
        { name: '申报数量', max: Math.max(10, ...topColleges.map((c) => c.total_projects || 0)) },
        { name: '立项率(%)', max: 100 },
        { name: '结题数', max: Math.max(1, ...topColleges.map((c) => c.finished_projects || 0)) },
        { name: '经费(万)', max: Math.max(10, ...topColleges.map((c) => Number(c.total_budget || 0) / 10000)) },
        { name: '成果数', max: Math.max(1, ...topColleges.map((c) => c.achievements || 0)) },
      ],
      splitArea: {
        areaStyle: {
          color: ['rgba(64,158,255,0.02)', 'rgba(64,158,255,0.05)'],
        },
      },
    },
    series: [{
      type: 'radar',
      data: topColleges.map((c, i) => ({
        value: [
          c.total_projects || 0,
          c.approval_rate || 0,
          c.finished_projects || 0,
          Math.round(Number(c.total_budget || 0) / 10000 * 100) / 100,
          c.achievements || 0,
        ],
        name: c.college_name,
        itemStyle: { color: colors[i % colors.length] },
        areaStyle: { opacity: 0.2 },
      })),
    }],
  }
})

// 经费使用分布图（真实数据：按预算科目汇总已使用金额）
const budgetDistOption = computed((): EChartsOption => {
  const items = budgetByCategory.value || []
  const colors = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399', '#722ED1']
  const periods = (trendData.value || []).map((d) => d.period)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: items.map((i) => i.name), bottom: 0 },
    xAxis: { type: 'category', data: periods.length ? periods : ['累计'] },
    yAxis: { type: 'value', name: '金额(元)' },
    series: items.map((item, idx) => ({
      name: item.name,
      type: 'bar',
      stack: 'total',
      data: periods.length
        ? periods.map(() => 0)
        : [Math.round(item.amount || 0)],
      itemStyle: { color: colors[idx % colors.length] },
    })),
  }
})

const categoryOption = computed((): EChartsOption => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie',
    radius: ['40%', '70%'],
    data: (categoryDist.value || []).map((c) => ({ name: c.name, value: c.value })),
    itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
    label: { formatter: '{b}: {d}%' },
  }],
}))

const budgetOption = computed((): EChartsOption => ({
  series: [{
    type: 'gauge',
    progress: { show: true, width: 18 },
    axisLine: { lineStyle: { width: 18 } },
    detail: { formatter: '{value}%', fontSize: 24, offsetCenter: [0, '70%'] },
    data: [{ value: Math.round(stats.value.approval_rate || 0), name: '立项率' }],
  }],
}))

const statusOption = computed((): EChartsOption => ({
  tooltip: { trigger: 'item' },
  legend: { type: 'scroll', bottom: 0 },
  series: [{
    type: 'pie',
    radius: '60%',
    data: (statusDist.value || []).map((s) => ({ name: s.name, value: s.value })),
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
  }],
}))

// U5 桑基图（真实数据：按项目状态分布构建流转）
const sankeyOption = computed((): EChartsOption => {
  const primary = appearanceStore.themeColor
  const statusData = statusDist.value || []
  const total = statusData.reduce((sum, s) => sum + (s.value || 0), 0) || 1

  const statusColorMap: Record<number, string> = {
    0: '#909399', 12: '#E6A23C', 1: '#F56C6C', 2: '#409EFF',
    3: '#E6A23C', 4: '#409EFF', 5: '#9B59B6', 6: '#67C23A',
    7: '#409EFF', 8: '#E6A23C', 9: '#52C41A', 10: '#F56C6C', 11: '#909399',
  }

  const nodes = [
    { name: '项目总数', itemStyle: { color: primary } },
    ...statusData.map((s) => ({
      name: s.name,
      itemStyle: { color: statusColorMap[s.status] || '#909399' },
    })),
  ]

  const links = statusData.map((s) => ({
    source: '项目总数',
    target: s.name,
    value: s.value || 0,
  }))

  return {
    tooltip: { trigger: 'item', triggerOn: 'mousemove' },
    series: [{
      type: 'sankey',
      emphasis: { focus: 'adjacency' },
      nodeAlign: 'left',
      data: nodes,
      links: links,
      lineStyle: { color: 'gradient' as any, curveness: 0.5, opacity: 0.6 },
      label: { color: 'inherit' },
    }],
  }
})

// F17 学院综合实力热力图（真实数据）
const heatmapOption = computed((): EChartsOption => {
  const colleges = (collegeStats.value || []).map((c) => c.college_name)
  const dimensions = ['申报数', '立项数', '结题数', '经费(万)', '成果数', '平均评分']
  const data: any[] = []
  ;(collegeStats.value || []).forEach((c, yIdx) => {
    const row = [
      c.total_projects || 0,
      c.approved_projects || 0,
      c.finished_projects || 0,
      Math.round(Number(c.total_budget || 0) / 10000 * 100) / 100,
      c.achievements || 0,
      Math.round(c.avg_score || 0),
    ]
    dimensions.forEach((_, xIdx) => {
      data.push([xIdx, yIdx, row[xIdx]])
    })
  })
  // 计算各维度最大值用于归一化显示（热力图颜色）
  const dimMax = dimensions.map((_, xIdx) =>
    Math.max(1, ...(collegeStats.value || []).map((c) => {
      const vals = [c.total_projects, c.approved_projects, c.finished_projects,
        Math.round(Number(c.total_budget || 0) / 10000), c.achievements, Math.round(c.avg_score || 0)]
      return vals[xIdx] || 0
    }))
  )
  return {
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const yIdx = params.value[1]
        const xIdx = params.value[0]
        return `${colleges[yIdx]}<br/>${dimensions[xIdx]}: ${params.value[2]}`
      }
    },
    grid: {
      left: '18%',
      right: '10%',
      top: '8%',
      bottom: '15%'
    },
    xAxis: {
      type: 'category',
      data: dimensions,
      splitArea: { show: true },
      axisLabel: { interval: 0, rotate: 0 }
    },
    yAxis: {
      type: 'category',
      data: colleges,
      splitArea: { show: true }
    },
    visualMap: {
      min: 0,
      max: 100,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '0%',
      inRange: {
        color: ['#e0f3ff', '#91ccf5', '#409EFF', '#1d6dd8', '#c23531']
      }
    },
    series: [{
      name: '综合实力',
      type: 'heatmap',
      data: data,
      label: {
        show: true,
        color: '#000',
        fontSize: 12
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      }
    }]
  }
})

// ==================== U8 图表下钻 ====================
function handleChartDrill(params: any) {
  const name = params?.name
  if (!name) return
  const seriesType = params?.seriesType
  if (seriesType === 'pie') {
    if (name === '创新训练' || name === '创业训练' || name === '创业实践') {
      const typeMap: Record<string, number> = { '创新训练': 1, '创业训练': 2, '创业实践': 3 }
      router.push({ path: '/admin/projects', query: { type: String(typeMap[name]) } })
      return
    }
    if (name === '已立项' || name === '已结题' || name === '待审核') {
      const statusMap: Record<string, number> = { '待审核': 1, '已立项': 6, '已结题': 9 }
      router.push({ path: '/admin/projects', query: { status: String(statusMap[name]) } })
      return
    }
  }
}

// ==================== 数据加载 ====================
async function loadData() {
  const params: any = {}
  if (filterForm.dateRange.length === 2) {
    params.start_year = new Date(filterForm.dateRange[0]).getFullYear()
    params.end_year = new Date(filterForm.dateRange[1]).getFullYear()
  }
  if (filterForm.college_id) params.college_id = filterForm.college_id
  if (filterForm.project_type) params.project_type = filterForm.project_type

  try {
    const [statsRes, trendRes, collegeRes] = await Promise.all([
      getStatistics(params),
      getTrend(),
      getCollegeBreakdown(),
    ])
    stats.value = statsRes.data
    trendData.value = (trendRes.data || []) as any[]
    collegeStats.value = (collegeRes.data || []) as any[]
    // 真实分布数据
    categoryDist.value = statsRes.data.category_dist || []
    statusDist.value = statsRes.data.status_dist || []
    budgetByCategory.value = statsRes.data.budget_by_category || []
  } catch {
    ElMessage.error('数据加载失败')
  }
}

// ==================== 导出 ====================
async function handleExport() {
  try {
    const wb = XLSX.utils.book_new()

    const overviewData = [
      ['指标', '数值'],
      ['申报总数', stats.value.total_projects],
      ['待审核', stats.value.pending_review],
      ['已立项', stats.value.approved_projects],
      ['已结题', stats.value.finished_projects],
      ['经费总额', stats.value.total_budget],
      ['已使用经费', stats.value.total_used],
      ['立项率', `${stats.value.approval_rate}%`],
    ]
    const ws1 = XLSX.utils.aoa_to_sheet(overviewData)
    XLSX.utils.book_append_sheet(wb, ws1, '统计概览')

    const trendExportData: any[][] = [['时间', '申报数', '立项数']]
    ;(trendData.value || []).forEach((d) => trendExportData.push([d.period, d.apply_count, d.approved_count]))
    const ws2 = XLSX.utils.aoa_to_sheet(trendExportData)
    XLSX.utils.book_append_sheet(wb, ws2, '趋势')

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
  if (userStore.isCollegeAdmin) {
    filterForm.college_id = userStore.collegeId ?? undefined
  }
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
