<!--
  页面名称：数据统计看板（管理员端，深色数据大屏风格）
  面向角色：系统管理员（全校数据）、学院管理员（仅本院数据）
  功能：以 ECharts 多维展示项目申报趋势、学院立项率、学院能力雷达、经费分布、
    类别/状态分布、经费使用率仪表盘、全流程桑基图、学院综合实力热力图；
    支持时间范围 / 学院 / 类别筛选，一键导出 Excel。
  调用 API：
    - GET /api/statistics/overview：KPI、类别分布、状态分布、预算按类别统计
    - GET /api/statistics/trend：按月申报/立项趋势（后端只接收起止年份）
    - GET /api/statistics/college-breakdown：各学院立项率、雷达、热力图数据
    - GET /api/colleges：学院筛选下拉
  权限 / 数据范围：
    - 后端 DataScope 统一过滤数据；学院管理员下拉锁定为本院（不可清空、不可改选），
      并在初始化时强制把 college_id 设为本人学院，防止越权查看他院数据。
  关键交互：
    - 「查询」一次性并行加载三个统计接口，任一失败统一提示
    - 类别饼图、状态饼图支持点击下钻到项目列表，并携带 type/status 查询参数
    - 导出仅包含「统计概览」与「趋势」两个工作表，数据取自当前筛选结果
  空数据处理：
    - 各图表把可能为空的数组映射为 series.data，ECharts 会渲染空坐标系而不是报错；
      雷达图指标上限用 Math.max(10, ...) 兜底，避免全院为零时坐标轴退化为 0 域；
      仪表盘在预算为 0 时使用率固定为 0，不做除零。
-->
<template>
  <div class="big-screen">
    <!--
      顶部栏：标题 + 实时时钟 + 导出
      时钟由 script 里的 setInterval 每秒更新，组件卸载时清理，避免离开页面后定时器泄漏。
      导出按钮不重新请求后端，直接使用当前已加载的 stats / trendData 生成工作簿，
      因此导出内容与屏幕上当前筛选结果一致。
    -->
    <div class="screen-header">
      <div class="screen-title">
        <span class="title-bar"></span>
        <span class="title-text">创新创业项目 · 数据大屏</span>
        <span class="title-sub">Data Overview</span>
      </div>
      <div class="screen-tools">
        <div class="screen-clock">
          <span class="clock-date">{{ nowDate }}</span>
          <span class="clock-time">{{ nowTime }}</span>
        </div>
        <el-button type="primary" :icon="Download" @click="handleExport">导出 Excel</el-button>
      </div>
    </div>

    <!--
      筛选栏
      - 时间范围只取起止年份（后端按立项年份过滤），日期选择器保留到日是为了交互习惯
      - 学院下拉对学院管理员禁用且不可清空：数据范围已由后端锁定，前端同步限制避免误操作
      - 类别按 1 创新训练 / 2 创业训练 / 3 创业实践 传值
      筛选不会自动请求，需点击「查询」触发 loadData，防止拖动日期时连续打接口。
    -->
    <div class="filter-bar">
      <el-form :inline="true" :model="filterForm">
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filterForm.dateRange"
            type="daterange"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            range-separator="至"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 260px"
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
        </el-form-item>
      </el-form>
    </div>

    <!--
      核心指标卡片
      statCards 由 stats 计算得出，图标与渐变色随卡片配置；CountNumber 负责数字滚动动画。
      经费总额用 toLocaleString 展示千分位，避免大数字难以辨认。
    -->
    <div class="kpi-row">
      <div v-for="card in statCards" :key="card.label" class="kpi-card">
        <div class="kpi-icon" :style="{ background: `linear-gradient(135deg, ${card.from}, ${card.to})` }">
          <el-icon :size="26"><component :is="card.icon" /></el-icon>
        </div>
        <div class="kpi-info">
          <p class="kpi-label">{{ card.label }}</p>
          <p class="kpi-value"><CountNumber :value="card.value" /></p>
        </div>
        <span class="kpi-deco"></span>
      </div>
    </div>

    <!--
      图表区第 1 行：年度申报趋势 + 各学院立项率
      趋势图只受起止年份影响（学院/类别筛选不会改变折线），因为后端趋势接口仅接受年份参数；
      学院立项率来自 college-breakdown，受全部筛选条件影响。
    -->
    <el-row :gutter="20">
      <el-col :span="12">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">年度申报趋势</span></div>
          <EChart :option="trendOption" height="300px" />
        </div>
      </el-col>
      <el-col :span="12">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">各学院立项率</span></div>
          <EChart :option="collegeOption" height="300px" />
        </div>
      </el-col>
    </el-row>

    <!--
      图表区第 2 行：学院 5 维能力雷达 + 项目经费使用分布
      雷达只取申报数最多的前 5 个学院，避免图例过多、轴线重叠；
      经费分布按预算科目横向条形展示，金额四舍五入到整数便于阅读。
    -->
    <el-row :gutter="20">
      <el-col :span="12">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">学院 5 维能力雷达图</span></div>
          <EChart :option="radarOption" height="300px" />
        </div>
      </el-col>
      <el-col :span="12">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">项目经费使用分布</span></div>
          <EChart :option="budgetDistOption" height="300px" />
        </div>
      </el-col>
    </el-row>

    <!--
      图表区第 3 行：类别分布 + 经费使用率仪表盘 + 状态分布
      类别/状态饼图开启了 clickable，点击扇区会按名称映射到项目列表的 type/status 查询参数，
      实现从统计到明细的下钻；仪表盘只展示，不参与下钻。
    -->
    <el-row :gutter="20">
      <el-col :span="8">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">项目类别分布</span></div>
          <EChart :option="categoryOption" :clickable="true" @click="handleChartDrill" height="280px" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">经费使用率</span></div>
          <EChart :option="budgetOption" height="280px" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">项目状态分布</span></div>
          <EChart :option="statusOption" :clickable="true" @click="handleChartDrill" height="280px" />
        </div>
      </el-col>
    </el-row>

    <!--
      图表区第 4 行：项目全流程转化漏斗（桑基图）
      以「项目总数」为唯一源节点，各状态为汇节点，用连线宽度表达各状态项目数量占比。
      状态分布为空时只渲染源节点，不产生指向空名称的连线。
    -->
    <el-row :gutter="20">
      <el-col :span="24">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">项目全流程转化漏斗（桑基图）</span></div>
          <EChart :option="sankeyOption" height="420px" />
        </div>
      </el-col>
    </el-row>

    <!--
      图表区第 5 行：学院综合实力热力图
      行为学院、列为 6 个指标（申报/立项/结题/经费/成果/平均评分），
      横纵坐标由 collegeStats 动态生成，学院数为 0 时矩阵为空但不会报错。
    -->
    <el-row :gutter="20">
      <el-col :span="24">
        <div class="panel">
          <div class="panel-head"><span class="panel-title">学院综合实力热力图</span></div>
          <EChart :option="heatmapOption" height="480px" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, computed } from 'vue'
import * as echarts from 'echarts'
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

// ==================== 深色主题常量 ====================
// 统一色板与文字/轴线颜色，保证多个图表视觉一致；数组按索引取模复用，避免单个图表配色数量不足
const PALETTE = ['#22d3ee', '#3b82f6', '#34d399', '#fbbf24', '#f472b6', '#a78bfa', '#f87171', '#38bdf8', '#4ade80', '#fb923c']
const TEXT_MAIN = '#1e293b'
const TEXT_LABEL = '#64748b'
const AXIS_LINE = 'rgba(100,116,139,0.3)'
const SPLIT_LINE = 'rgba(148,163,184,0.2)'
const TOOLTIP = {
  backgroundColor: 'rgba(30,41,59,0.9)',
  borderColor: 'rgba(59,130,246,0.4)',
  textStyle: { color: '#f1f5f9' },
}

/**
 * 生成 ECharts 线性渐变色
 * @param from 起始颜色
 * @param to 结束颜色
 * @param dir 'v' 垂直（默认），'h' 水平
 * @returns echarts.graphic.LinearGradient 实例
 * 说明：面积图、条形图共用此函数，避免在每个 option 中手写坐标参数。
 */
function linearGradient(from: string, to: string, dir: 'v' | 'h' = 'v') {
  return new echarts.graphic.LinearGradient(0, 0, dir === 'h' ? 1 : 0, dir === 'v' ? 1 : 0, [
    { offset: 0, color: from },
    { offset: 1, color: to },
  ])
}

// ==================== 时钟 ====================
// 顶栏日期/时间；clockTimer 保存 setInterval 句柄，卸载时清理防止定时器泄漏
const nowDate = ref('')
const nowTime = ref('')
let clockTimer: number
/** 刷新顶栏时钟：日期带星期，时间补零到 HH:mm:ss */
function updateClock() {
  const n = new Date()
  const days = ['日', '一', '二', '三', '四', '五', '六']
  nowDate.value = `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')} 星期${days[n.getDay()]}`
  nowTime.value = `${String(n.getHours()).padStart(2, '0')}:${String(n.getMinutes()).padStart(2, '0')}:${String(n.getSeconds()).padStart(2, '0')}`
}
updateClock()
clockTimer = window.setInterval(updateClock, 1000)
onBeforeUnmount(() => clearInterval(clockTimer))

// ==================== 筛选 ====================
// 日期范围以 YYYY-MM-DD 字符串保存，提交时只取年份；college_id/project_type 为空表示不筛选
const filterForm = reactive({
  dateRange: [] as string[],
  college_id: undefined as number | undefined,
  project_type: undefined as number | undefined,
})

// 学院下拉数据；学院管理员虽然只能看本院，仍需该列表回显本院名称
const colleges = ref<any[]>([])

// ==================== 统计数据 ====================
// KPI 概览，字段与 GET /api/statistics/overview 返回结构对齐；初始为 0 便于首屏渲染
const stats = ref({
  total_projects: 0,
  pending_review: 0,
  approved_projects: 0,
  finished_projects: 0,
  total_budget: 0,
  total_used: 0,
  approval_rate: 0,
})

// 按月趋势：period 为「YYYY-MM」，apply_count 申报数，approved_count 立项数
const trendData = ref<{ period: string; apply_count: number; approved_count: number }[]>([])
// 各学院汇总：用于立项率柱图、雷达图、热力图（字段由后端 CollegeStatisticsItem 提供）
const collegeStats = ref<any[]>([])
// 类别分布（饼图）
const categoryDist = ref<{ name: string; value: number }[]>([])
// 状态分布（饼图 + 桑基图）；status 保留数值用于节点配色
const statusDist = ref<{ name: string; value: number; status: number }[]>([])
// 按预算科目的经费使用分布（横向条形图）
const budgetByCategory = ref<{ name: string; amount: number }[]>([])

// KPI 卡片配置：value 直接引用 stats，筛选后随统计接口一起更新
const statCards = computed(() => [
  { label: '申报总数', value: stats.value.total_projects, icon: Files, from: '#3b82f6', to: '#22d3ee' },
  { label: '待审核', value: stats.value.pending_review, icon: Document, from: '#f59e0b', to: '#fbbf24' },
  { label: '已立项', value: stats.value.approved_projects, icon: Box, from: '#22c55e', to: '#4ade80' },
  { label: '经费总额(¥)', value: Number(stats.value.total_budget || 0).toLocaleString(), icon: Wallet, from: '#ef4444', to: '#f472b6' },
])

// ==================== 图表配置 ====================
/**
 * 年度申报趋势折线图
 * 两条线分别使用 data 中的 apply_count / approved_count；数组为空时 data 为 []，
 * ECharts 展示空坐标系，不会因 undefined 报错。
 * 去掉学院/类别维度是接口能力限制，不是漏传：trend 接口只接受 start_year/end_year。
 */
const trendOption = computed((): EChartsOption => ({
  tooltip: { ...TOOLTIP, trigger: 'axis' },
  legend: { top: 0, textStyle: { color: TEXT_LABEL } },
  grid: { left: '3%', right: '4%', bottom: '3%', top: 40, containLabel: true },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: (trendData.value || []).map((d) => d.period),
    axisLabel: { color: TEXT_LABEL },
    axisLine: { lineStyle: { color: AXIS_LINE } },
    axisTick: { show: false },
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: TEXT_LABEL },
    splitLine: { lineStyle: { color: SPLIT_LINE } },
    axisLine: { show: false },
  },
  series: [
    {
      name: '申报数',
      type: 'line',
      data: (trendData.value || []).map((d) => d.apply_count),
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 3, color: '#3b82f6', shadowColor: 'rgba(59,130,246,0.45)', shadowBlur: 6 },
      itemStyle: { color: '#3b82f6', borderColor: '#fff', borderWidth: 1 },
      areaStyle: { color: linearGradient('rgba(59,130,246,0.18)', 'rgba(59,130,246,0)') },
    },
    {
      name: '立项数',
      type: 'line',
      data: (trendData.value || []).map((d) => d.approved_count),
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 3, color: '#22c55e', shadowColor: 'rgba(34,197,94,0.45)', shadowBlur: 6 },
      itemStyle: { color: '#22c55e', borderColor: '#fff', borderWidth: 1 },
      areaStyle: { color: linearGradient('rgba(34,197,94,0.16)', 'rgba(34,197,94,0)') },
    },
  ],
}))

/**
 * 各学院立项率柱状图
 * 立项率固定 0~100 的纵轴上限，避免各院都接近 100% 时差异被视觉放大；
 * 数值四舍五入取整，标签直接显示百分比。
 */
const collegeOption = computed((): EChartsOption => {
  const colleges = collegeStats.value || []
  return {
    tooltip: { ...TOOLTIP, trigger: 'axis', formatter: '{b}: {c}%' },
    grid: { left: '3%', right: '4%', bottom: '3%', top: 20, containLabel: true },
    xAxis: {
      type: 'category',
      data: colleges.map((c) => c.college_name),
      axisLabel: { color: TEXT_LABEL, rotate: 30, fontSize: 11 },
      axisLine: { lineStyle: { color: AXIS_LINE } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: { color: TEXT_LABEL, formatter: '{value}%' },
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    series: [{
      type: 'bar',
      data: colleges.map((c) => Math.round(c.approval_rate || 0)),
      barMaxWidth: 36,
      itemStyle: {
        color: linearGradient('rgba(34,211,238,0.95)', 'rgba(59,130,246,0.15)'),
        borderRadius: [4, 4, 0, 0],
        shadowColor: 'rgba(34,211,238,0.4)',
        shadowBlur: 8,
      },
      label: { show: true, position: 'top', formatter: '{c}%', color: TEXT_MAIN },
    }],
  }
})

// ==================== 学院 5 维能力雷达图 ====================
/**
 * 雷达图只展示申报数最多的前 5 个学院：
 * 1) 图例和面积叠加过多会互相遮挡；
 * 2) 各维度 max 至少取 10（立项率固定 100），保证数据全为 0 时仍有可读刻度。
 * 颜色优先使用系统主题色，再按固定色板补充，保证切换主题后首条数据跟随主题。
 */
const radarOption = computed((): EChartsOption => {
  const themeColor = appearanceStore.themeColor
  const colors = [themeColor, '#67C23A', '#E6A23C', '#F56C6C', '#909399']
  const topColleges = [...(collegeStats.value || [])]
    .sort((a, b) => b.total_projects - a.total_projects)
    .slice(0, 5)
  return {
    tooltip: { ...TOOLTIP },
    legend: { bottom: 0, textStyle: { color: TEXT_LABEL } },
    radar: {
      radius: '62%',
      splitNumber: 4,
      indicator: [
        { name: '申报数量', max: Math.max(10, ...topColleges.map((c) => c.total_projects || 0)) },
        { name: '立项率(%)', max: 100 },
        { name: '结题数', max: Math.max(1, ...topColleges.map((c) => c.finished_projects || 0)) },
        { name: '经费(万)', max: Math.max(10, ...topColleges.map((c) => Number(c.total_budget || 0) / 10000)) },
        { name: '成果数', max: Math.max(1, ...topColleges.map((c) => c.achievements || 0)) },
      ],
      axisName: { color: TEXT_LABEL },
      axisLine: { lineStyle: { color: AXIS_LINE } },
      splitLine: { lineStyle: { color: AXIS_LINE } },
      splitArea: { areaStyle: { color: ['rgba(59,130,246,0.03)', 'rgba(59,130,246,0.09)'] } },
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
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.18 },
      })),
    }],
  }
})

/**
 * 项目经费使用分布（按预算科目）
 * 横向条形图便于科目名称完整显示；金额取整并右对齐标签。
 * 科目为空时 categories 为 []，图表只显示空坐标系。
 */
const budgetDistOption = computed((): EChartsOption => {
  const items = budgetByCategory.value || []
  const colors = PALETTE
  return {
    tooltip: { ...TOOLTIP, trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '8%', bottom: '3%', top: 10, containLabel: true },
    xAxis: { type: 'value', axisLabel: { color: TEXT_LABEL }, splitLine: { lineStyle: { color: SPLIT_LINE } } },
    yAxis: {
      type: 'category',
      data: items.map((i) => i.name),
      axisLabel: { color: TEXT_MAIN },
      axisLine: { lineStyle: { color: AXIS_LINE } },
      axisTick: { show: false },
    },
    series: [{
      type: 'bar',
      barWidth: 16,
      data: items.map((i, idx) => ({
        value: Math.round(i.amount || 0),
        itemStyle: {
          color: linearGradient(colors[idx % colors.length], 'rgba(59,130,246,0.08)', 'h'),
          borderRadius: [0, 4, 4, 0],
        },
      })),
      label: { show: true, position: 'right', color: TEXT_MAIN },
    }],
  }
})

/**
 * 项目类别分布环形图
 * 扇区名称即类别中文名，供 handleChartDrill 映射成 project_type 参数下钻。
 */
const categoryOption = computed((): EChartsOption => ({
  tooltip: { ...TOOLTIP, trigger: 'item' },
  legend: { bottom: 0, textStyle: { color: TEXT_LABEL } },
  color: PALETTE,
  series: [{
    type: 'pie',
    radius: ['45%', '72%'],
    center: ['50%', '46%'],
    itemStyle: { borderRadius: 6, borderColor: '#ffffff', borderWidth: 2 },
    label: { color: TEXT_MAIN, formatter: '{b}\n{d}%' },
    labelLine: { lineStyle: { color: 'rgba(159,185,217,0.4)' } },
    data: (categoryDist.value || []).map((c) => ({ name: c.name, value: c.value })),
  }],
}))

/**
 * 经费使用率 = 已使用经费 / 经费总额（原实现误用了立项率）
 * total_budget 为 0 时直接返回 0，避免除零得到 NaN/Infinity 导致仪表盘指针异常；
 * 结果取整用于百分比展示，不做上限截断（超出预算按实际比例显示以暴露问题）。
 */
const budgetUsageRate = computed(() => {
  const total = Number(stats.value.total_budget || 0)
  if (total <= 0) return 0
  return Math.round((Number(stats.value.total_used || 0) / total) * 100)
})

/**
 * 经费使用率仪表盘
 * 0~100 固定量程，数据只有 budgetUsageRate 一个值；空/零预算时显示 0%。
 */
const budgetOption = computed((): EChartsOption => ({
  series: [{
    type: 'gauge',
    startAngle: 210,
    endAngle: -30,
    min: 0,
    max: 100,
    radius: '100%',
    axisLine: { lineStyle: { width: 14, color: [[1, 'rgba(59,130,246,0.15)']] } },
    progress: { show: true, width: 14, itemStyle: { color: linearGradient('#22d3ee', '#3b82f6', 'h'), shadowColor: 'rgba(34,211,238,0.5)', shadowBlur: 10 } },
    axisTick: { show: false },
    splitLine: { length: 10, lineStyle: { width: 2, color: 'rgba(159,185,217,0.25)' } },
    axisLabel: { distance: 22, color: TEXT_LABEL, fontSize: 10 },
    pointer: { itemStyle: { color: '#22d3ee' } },
    anchor: { show: true, itemStyle: { color: '#22d3ee' } },
    detail: { valueAnimation: true, formatter: '{value}%', color: TEXT_MAIN, fontSize: 28, offsetCenter: [0, '70%'] },
    title: { show: false },
    data: [{ value: budgetUsageRate.value }],
  }],
}))

/**
 * 项目状态分布环形图
 * 图例使用 scroll 类型，防止状态较多时溢出面板；名称用于下钻映射。
 */
const statusOption = computed((): EChartsOption => ({
  tooltip: { ...TOOLTIP, trigger: 'item' },
  legend: { type: 'scroll', bottom: 0, textStyle: { color: TEXT_LABEL } },
  color: PALETTE,
  series: [{
    type: 'pie',
    radius: ['40%', '68%'],
    center: ['50%', '46%'],
    itemStyle: { borderRadius: 6, borderColor: '#ffffff', borderWidth: 2 },
    label: { color: TEXT_MAIN, formatter: '{b}\n{d}%' },
    labelLine: { lineStyle: { color: 'rgba(159,185,217,0.4)' } },
    data: (statusDist.value || []).map((s) => ({ name: s.name, value: s.value })),
  }],
}))

// ==================== 桑基图 ====================
/**
 * 项目全流程转化桑基图
 * 节点 = 项目总数 + 各状态；连线表示「总数 → 状态」的数量。
 * statusColorMap 覆盖后端可能返回的状态码，未命中时回退灰色，避免节点无颜色。
 * 状态列表为空时 nodes 只有根节点、links 为空，图表不报错。
 */
const sankeyOption = computed((): EChartsOption => {
  const primary = appearanceStore.themeColor
  const statusData = statusDist.value || []
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
    tooltip: { ...TOOLTIP, trigger: 'item', triggerOn: 'mousemove' },
    series: [{
      type: 'sankey',
      emphasis: { focus: 'adjacency' },
      nodeAlign: 'left',
      data: nodes,
      links: links,
      lineStyle: { color: 'gradient' as any, curveness: 0.5, opacity: 0.5 },
      label: { color: TEXT_MAIN },
    }],
  }
})

// ==================== 学院综合实力热力图 ====================
/**
 * 学院综合实力热力图
 * 将每个学院的一行指标展开成 [xIndex, yIndex, value] 三元组：
 * x 为指标维度索引，y 为学院索引，value 为原始数值；visualMap 0~100 控制全局色阶。
 * 经费按「万元」换算并保留两位小数；平均评分四舍五入，避免小数让格子标签过长。
 * collegeStats 为空时 data 为空数组，坐标轴亦为空，不会出现越界访问。
 */
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
  return {
    tooltip: {
      ...TOOLTIP,
      position: 'top',
      formatter: (params: any) => `${colleges[params.value[1]]}<br/>${dimensions[params.value[0]]}: ${params.value[2]}`,
    },
    grid: { left: '18%', right: '8%', top: '8%', bottom: '16%' },
    xAxis: {
      type: 'category',
      data: dimensions,
      axisLabel: { color: TEXT_MAIN },
      axisLine: { lineStyle: { color: AXIS_LINE } },
    },
    yAxis: {
      type: 'category',
      data: colleges,
      axisLabel: { color: TEXT_MAIN },
      axisLine: { lineStyle: { color: AXIS_LINE } },
    },
    visualMap: {
      min: 0,
      max: 100,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      textStyle: { color: TEXT_LABEL },
      inRange: { color: ['#0b2a5b', '#13408f', '#1f6feb', '#22c55e', '#f59e0b', '#ef4444'] },
    },
    series: [{
      name: '综合实力',
      type: 'heatmap',
      data: data,
      label: { show: true, color: '#fff', fontSize: 12 },
      itemStyle: { borderColor: 'rgba(255,255,255,0.9)', borderWidth: 2 },
      emphasis: { itemStyle: { shadowBlur: 12, shadowColor: 'rgba(34,211,238,0.6)' } },
    }],
  }
})

// ==================== 图表下钻 ====================
/**
 * 饼图点击下钻到项目列表
 * @param params ECharts 点击事件参数，取 name 与 seriesType
 * 只处理 pie 且名称在已知映射内的情况：类别 → project_type，状态 → status。
 * 名称不在映射中（如后端新增状态）直接忽略，避免跳转到无效筛选。
 * 副作用：router.push 到 /admin/projects 并携带查询参数，由列表页初始化时读取。
 */
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
/**
 * 按当前筛选加载全部统计数据
 * 参数构造：
 *   - 日期范围只有选满 2 个端点时才取年份，避免半截区间产生无效参数；
 *   - 学院/类别为空则不传，交由后端按数据范围返回全部。
 * 请求策略：三个接口并行发出，减少首屏等待；趋势接口单独构造 trendParams，
 *   只保留年份，因为其签名不接受学院/类别。
 * 副作用：覆盖 stats、trendData、collegeStats 与三个分布数组。
 * 失败处理：任一接口失败会进入 catch，提示「数据加载失败」；
 *   此时保留上一次成功的数据，不清空页面，便于用户重试。
 */
async function loadData() {
  const params: any = {}
  if (filterForm.dateRange.length === 2) {
    params.start_year = new Date(filterForm.dateRange[0]).getFullYear()
    params.end_year = new Date(filterForm.dateRange[1]).getFullYear()
  }
  if (filterForm.college_id) params.college_id = filterForm.college_id
  if (filterForm.project_type) params.project_type = filterForm.project_type

  try {
    const trendParams: any = {}
    if (params.start_year) trendParams.start_year = params.start_year
    if (params.end_year) trendParams.end_year = params.end_year
    const [statsRes, trendRes, collegeRes] = await Promise.all([
      getStatistics(params),
      getTrend(trendParams),
      getCollegeBreakdown(params),
    ])
    stats.value = statsRes.data
    trendData.value = (trendRes.data || []) as any[]
    collegeStats.value = (collegeRes.data || []) as any[]
    categoryDist.value = statsRes.data.category_dist || []
    statusDist.value = statsRes.data.status_dist || []
    budgetByCategory.value = statsRes.data.budget_by_category || []
  } catch {
    ElMessage.error('数据加载失败')
  }
}

// ==================== 导出 ====================
/**
 * 导出当前统计结果为 Excel
 * 使用已加载的 stats / trendData 在浏览器端用 XLSX 生成两个工作表：
 *   「统计概览」KPI 与经费、立项率；「趋势」按月申报/立项数。
 * 文件通过 file-saver 下载为「统计报表.xlsx」。
 * 失败处理：生成或下载异常统一提示「导出失败」，不阻塞页面。
 */
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
// 先取学院下拉，再按角色锁定学院范围，最后加载统计。
// 学院管理员强制写入本人 collegeId，使前端筛选与后端 DataScope 保持一致。
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
.big-screen {
  position: relative;
  min-height: calc(100vh - 120px);
  padding: 24px 24px 32px;
  border-radius: 14px;
  background:
    radial-gradient(circle at 85% 10%, rgba(59, 130, 246, 0.10), transparent 45%),
    radial-gradient(circle at 10% 92%, rgba(34, 211, 238, 0.10), transparent 40%),
    linear-gradient(160deg, #eef4ff 0%, #e7f0ff 45%, #ecf3ff 100%);
  box-shadow: 0 0 0 1px rgba(120, 170, 255, 0.20), 0 20px 50px rgba(15, 40, 90, 0.10);
  overflow: hidden;
}

/* 顶部 */
.screen-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.screen-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.title-bar {
  width: 6px;
  height: 28px;
  border-radius: 3px;
  background: linear-gradient(180deg, #22d3ee, #3b82f6);
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.8);
}
.title-text {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 2px;
  background: linear-gradient(90deg, #22d3ee, #3b82f6, #22d3ee);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.title-sub {
  font-size: 12px;
  letter-spacing: 3px;
  color: #64748b;
  text-transform: uppercase;
}
.screen-tools {
  display: flex;
  align-items: center;
  gap: 20px;
}
.screen-clock {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.clock-time {
  font-size: 26px;
  font-weight: 700;
  color: #0ea5e9;
  letter-spacing: 1px;
  text-shadow: 0 0 12px rgba(14, 165, 233, 0.4);
  font-variant-numeric: tabular-nums;
}
.clock-date {
  font-size: 12px;
  color: #64748b;
}

/* 筛选栏 */
.filter-bar {
  padding: 14px 18px 2px;
  margin-bottom: 20px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(120, 170, 255, 0.28);
  backdrop-filter: blur(6px);
}

/* KPI 卡片 */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 20px;
}
.kpi-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.80);
  border: 1px solid rgba(120, 170, 255, 0.28);
  overflow: hidden;
  transition: transform 0.25s, box-shadow 0.25s;
}
.kpi-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(34, 211, 238, 0.18);
}
.kpi-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
  box-shadow: 0 6px 16px rgba(15, 40, 90, 0.15);
}
.kpi-info {
  min-width: 0;
}
.kpi-label {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 6px;
}
.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: 0.5px;
  font-variant-numeric: tabular-nums;
}
.kpi-deco {
  position: absolute;
  right: -30px;
  bottom: -30px;
  width: 90px;
  height: 90px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(34, 211, 238, 0.12), transparent 70%);
  pointer-events: none;
}

/* 图表面板 */
.el-row {
  margin-bottom: 20px;
}
.panel {
  position: relative;
  padding: 14px 16px 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(120, 170, 255, 0.28);
  box-shadow: 0 4px 16px rgba(15, 40, 90, 0.06);
}
.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.panel-title {
  position: relative;
  padding-left: 12px;
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}
.panel-title::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: linear-gradient(180deg, #22d3ee, #3b82f6);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.8);
}

/* 筛选栏文字（浅色主题） */
.big-screen :deep(.el-form-item__label) { color: #475569; }
</style>