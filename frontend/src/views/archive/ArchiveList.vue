<!--
  ==== 归档项目库 ====

  页面职责：检索、查看历史已归档项目（结题完成），支持基础筛选与高级筛选
            （类别 / 级别 / 获奖 / 经费区间 / 排序）、筛选结果汇总与展开收起。
  角色与路由：meta.roles 为 [1,2,3,4]，各角色均可访问；
            路由 /admin/archive（name: ProjectArchive）。
  调用接口：GET /api/projects（status=9 表示已结题归档，page_size=200 循环拉取全部页码）
  关键交互：后端单页上限 200，且高级筛选与排序需要在前端完成，因此一次性取回全部
            归档数据后本地筛选、排序、分页；翻页只切换显示切片，不再发起请求；
            执行查询后展示筛选条件汇总，帮助用户确认当前结果口径。
  说明：项目级别 project_level 与比赛级别不同，取值为 1 院级 / 2 校级 / 3 省级 / 4 国家级。
-->
<template>
  <div class="page-container">
    <!-- 区块：基础筛选区（关键词 / 年份，以及高级筛选展开开关） -->
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号/成果" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="年份">
          <el-select v-model="searchForm.year" placeholder="全部" clearable style="width: 100px">
            <el-option v-for="y in years" :key="y" :label="y" :value="y" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset" v-if="showAdvanced">重置</el-button>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" link @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '收起筛选 ▲' : '高级筛选 ▼' }}
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 区块：高级筛选区（类别 / 级别 / 获奖 / 经费区间 / 排序，展开后才显示） -->
      <el-form v-show="showAdvanced" :inline="true" :model="searchForm" style="margin-top: 12px; border-top: 1px solid #ebeef5; padding-top: 12px;">
        <el-form-item label="项目类别">
          <el-select v-model="searchForm.project_type" placeholder="全部类别" clearable style="width: 140px">
            <el-option label="创新训练" :value="1" />
            <el-option label="创业训练" :value="2" />
            <el-option label="创业实践" :value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目级别">
          <el-select v-model="searchForm.project_level" placeholder="全部级别" clearable style="width: 140px">
            <el-option label="院级" :value="1" />
            <el-option label="校级" :value="2" />
            <el-option label="省级" :value="3" />
            <el-option label="国家级" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item label="获奖情况">
          <el-select v-model="searchForm.has_award" placeholder="全部" clearable style="width: 120px">
            <el-option label="获奖" :value="1" />
            <el-option label="未获奖" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item label="经费范围(万)" style="min-width: 260px;">
          <el-slider
            v-model="searchForm.budget_range"
            range
            :min="0"
            :max="10"
            :step="0.5"
            :marks="{ 0: '0', 2: '2', 5: '5', 10: '10' }"
            style="width: 260px; display: inline-block; vertical-align: middle;"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-select v-model="searchForm.sort_by" placeholder="默认排序" clearable style="width: 180px">
            <el-option label="结题时间 ↓ 最新" value="end_date_desc" />
            <el-option label="结题时间 ↑ 最早" value="end_date_asc" />
            <el-option label="经费 ↓ 高到低" value="budget_desc" />
            <el-option label="经费 ↑ 低到高" value="budget_asc" />
            <el-option label="项目级别 ↓ 高到低" value="level_desc" />
            <el-option label="项目级别 ↑ 低到高" value="level_asc" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 区块：筛选结果汇总（仅在执行查询后展示，包含条件与命中条数） -->
    <el-alert
      v-if="searched && filterSummary"
      type="info"
      :closable="false"
      show-icon
      class="summary-alert"
    >
      <span v-html="filterSummary"></span>
    </el-alert>

    <!-- 区块：归档列表（通用分页表格，插槽自定义类别/级别/获奖标签与操作列） -->
    <PaginationTable
      :data="displayData"
      :columns="columns"
      :total="displayTotal"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <template #project_type="{ row }">
        <el-tag size="small">{{ row.project_type_name || projectTypeLabel(row.project_type) }}</el-tag>
      </template>
      <template #project_level="{ row }">
        <el-tag size="small" :type="levelTagType(row.project_level)">{{ row.project_level_name || projectLevelLabel(row.project_level) }}</el-tag>
      </template>
      <template #has_award="{ row }">
        <!-- 获奖判定：成果数 award_count 或兼容字段 has_award 大于 0 即视为获奖 -->
        <el-tag v-if="row.award_count > 0 || row.has_award === 1" type="success" size="small">🏆 获奖</el-tag>
        <el-tag v-else type="info" size="small">未获奖</el-tag>
      </template>
      <!-- 操作列仅提供查看入口，详情由全局 projectDetailStore 统一打开 -->
      <template #actions="{ row }">
        <el-button link type="primary" size="small" @click="projectDetailStore.open(row.id)">查看</el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="file" description="暂无归档项目" />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
// ==================== 导入区 ====================
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList } from '@/api/project'
import { formatDateTime } from '@/utils/format'
import { useProjectDetailStore } from '@/store/projectDetail'

// ==================== 依赖与路由 ====================
// router 当前未直接使用（项目详情统一通过 projectDetailStore 打开），保留以便后续扩展跳转
const router = useRouter()
// 全局项目详情抽屉：open(id) 负责按 id 加载并展示归档项目详情
const projectDetailStore = useProjectDetailStore()

// ==================== 状态与查询条件 ====================
// 高级筛选面板是否展开；默认收起，保持首屏简洁
const showAdvanced = ref(false)
// 是否已执行过查询：为 true 才启用前端筛选、排序与筛选汇总；重置后回到 false
const searched = ref(false)

// 筛选条件集合（reactive 便于直接绑定表单）：
// keyword 关键词、year 年份、project_type 类别、project_level 级别、
// has_award 是否获奖（1 获奖 / 0 未获奖）、budget_range 经费区间（单位万元）、sort_by 排序键
const searchForm = reactive({
  keyword: '',
  year: undefined as number | undefined,
  project_type: undefined as number | undefined,
  project_level: undefined as number | undefined,
  has_award: undefined as number | undefined,
  budget_range: [0, 10] as [number, number],
  sort_by: undefined as string | undefined,
})

// ==================== 数据与分页状态 ====================
// 一次拉取的全部归档项目（后端 status=9），作为前端筛选与排序的数据源
const rawData = ref<any[]>([])
// 归档项目总数，取自实际拉取条数，因为后续分页完全在前端完成
const total = ref(0)
// 列表加载态：控制通用表格 v-loading
const loading = ref(false)
// 当前页码（本地分页）
const page = ref(1)
// 每页条数（本地分页），由 PaginationTable 翻页事件更新
const pageSize = ref(10)

// ==================== 年份选项（计算属性） ====================
// 页面生命周期内固定不变的当前年份，作为候选年份的基准
const currentYear = new Date().getFullYear()
/**
 * 年份下拉候选：当前年份向前 5 年。
 * 依赖模块级 currentYear（打开页面后不变），首次求值后由 computed 缓存，
 * 避免每次渲染都重新构造数组。
 */
const years = computed(() => Array.from({ length: 5 }, (_, i) => currentYear - i))

// ==================== 表格列配置 ====================
// 列定义交给 PaginationTable 渲染；slot 列由下方同名插槽自定义标签，
// formatter 列负责金额与时间格式化（预算保留两位小数，created_at 作为结题时间展示）
const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'project_type', label: '类别', slot: 'project_type', width: 100 },
  { prop: 'project_level', label: '级别', slot: 'project_level', width: 90 },
  { prop: 'leader_name', label: '负责人', width: 100 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'college_name', label: '学院', width: 120 },
  { prop: 'budget_amount', label: '预算(¥)', width: 110, formatter: (v: number) => Number(v || 0).toFixed(2) },
  { prop: 'has_award', label: '获奖', slot: 'has_award', width: 90 },
  { prop: 'created_at', label: '结题时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

// ==================== 枚举展示辅助函数 ====================
/** 项目类别：1 创新训练 / 2 创业训练 / 3 创业实践；未知值返回 '-' */
function projectTypeLabel(t: number): string {
  return { 1: '创新训练', 2: '创业训练', 3: '创业实践' }[t] || '-'
}

/** 项目级别：1 院级 / 2 校级 / 3 省级 / 4 国家级；未知值返回 '-' */
function projectLevelLabel(l: number): string {
  return { 1: '院级', 2: '校级', 3: '省级', 4: '国家级' }[l] || '-'
}

/** 项目级别转 el-tag 颜色：院级灰、校级默认、省级绿、国家级红，用于快速区分层级 */
function levelTagType(l: number): string {
  return { 1: 'info', 2: '', 3: 'success', 4: 'danger' }[l] || 'info'
}

/**
 * 推断项目所属年份：依次尝试 created_at、submit_time、end_date。
 * @param d 项目行数据
 * @returns 四位年份；三个字段都无法解析时返回 0，从而不会被年份筛选命中
 */
function projectYearOf(d: any): number {
  const s = d.created_at || d.submit_time || d.end_date || ''
  if (!s) return 0
  const m = String(s).match(/(\d{4})/)
  return m ? Number(m[1]) : 0
}

/**
 * 前端筛选：类别、级别、年份、是否获奖、经费区间。
 * @param items 全量归档项目
 * @returns 满足全部已选条件的项目数组；未选择的条件自动跳过
 */
function frontendFilter(items: any[]): any[] {
  return items.filter((item) => {
    if (searchForm.project_type != null && Number(item.project_type) !== Number(searchForm.project_type)) return false
    if (searchForm.project_level != null && Number(item.project_level) !== Number(searchForm.project_level)) return false
    if (searchForm.year != null && projectYearOf(item) !== searchForm.year) return false
    if (searchForm.has_award != null) {
      const awarded = (item.award_count ?? item.has_award ?? 0) >= 1
      if (searchForm.has_award === 1 && !awarded) return false
      if (searchForm.has_award === 0 && awarded) return false
    }
    // 预算以元存储，滑块单位为万元，先换算再比较区间
    const budgetWan = Number(item.budget_amount || 0) / 10000
    if (searchForm.budget_range && Array.isArray(searchForm.budget_range) && searchForm.budget_range.length === 2) {
      const [lo, hi] = searchForm.budget_range
      if (budgetWan < lo || budgetWan > hi) return false
    }
    return true
  })
}

/**
 * 前端排序。
 * @param items 已筛选的项目数组
 * @returns 排序后的新数组；sort_by 为空时原样返回
 * 支持结题时间、经费、项目级别三类字段的正反序，内部先复制数组避免污染原始数据。
 */
function frontendSort(items: any[]): any[] {
  const key = searchForm.sort_by
  if (!key) return items
  const arr = [...items]
  const cmpDate = (a: any, b: any, desc: boolean) => {
    const da = new Date(a.created_at || a.end_date || 0).getTime()
    const db = new Date(b.created_at || b.end_date || 0).getTime()
    return desc ? db - da : da - db
  }
  const cmpNum = (va: number, vb: number, desc: boolean) => (desc ? vb - va : va - vb)
  switch (key) {
    case 'end_date_desc':
      arr.sort((a, b) => cmpDate(a, b, true))
      break
    case 'end_date_asc':
      arr.sort((a, b) => cmpDate(a, b, false))
      break
    case 'budget_desc':
      arr.sort((a, b) => cmpNum(Number(a.budget_amount || 0), Number(b.budget_amount || 0), true))
      break
    case 'budget_asc':
      arr.sort((a, b) => cmpNum(Number(a.budget_amount || 0), Number(b.budget_amount || 0), false))
      break
    case 'level_desc':
      arr.sort((a, b) => cmpNum(Number(a.project_level || 0), Number(b.project_level || 0), true))
      break
    case 'level_asc':
      arr.sort((a, b) => cmpNum(Number(a.project_level || 0), Number(b.project_level || 0), false))
      break
  }
  return arr
}

// ==================== 派生数据（前端筛选 / 排序 / 分页 / 汇总） ====================
/**
 * 过滤后的归档数据。
 * 依赖：rawData（全量归档）与 searchForm 的类别、级别、年份、获奖、经费条件。
 * 输出：先筛选再排序的项目数组，供 displayData 与 filterSummary 复用。
 * 缓存原因：模板中 displayData、filterSummary 都会读取它，computed 避免重复过滤。
 */
const filteredData = computed(() => {
  let list = frontendFilter(rawData.value)
  list = frontendSort(list)
  return list
})

/**
 * 表格显示的总条数。
 * 未查询时取后端返回的 total；已查询时取前端过滤后的条数，
 * 保证分页组件页数与实际展示结果一致。
 */
const displayTotal = computed(() => {
  if (searched.value) return filteredData.value.length
  return total.value
})

/**
 * 当前页数据切片。
 * 未查询时直接展示后端原始数据；已查询时从 filteredData 按页码切片，
 * 实现「一次拉全量、前端本地分页」，翻页不需要再次请求。
 */
const displayData = computed(() => {
  const source = searched.value ? filteredData.value : rawData.value
  const start = (page.value - 1) * pageSize.value
  return source.slice(start, start + pageSize.value)
})

/**
 * 筛选条件汇总文案。
 * 依赖 searched 与 searchForm 各字段，输出 el-alert 中展示的 HTML 片段。
 * 缓存原因：条件未变化时复用同一字符串，避免每次渲染重复拼接。
 */
const filterSummary = computed(() => {
  if (!searched.value) return ''
  const parts: string[] = []
  if (searchForm.keyword) parts.push(`关键词=<b>${searchForm.keyword}</b>`)
  if (searchForm.year != null) parts.push(`年份=${searchForm.year}`)
  if (searchForm.project_type != null) parts.push(`类别=${projectTypeLabel(searchForm.project_type)}`)
  if (searchForm.project_level != null) parts.push(`级别=${projectLevelLabel(searchForm.project_level)}`)
  if (searchForm.has_award != null) parts.push(`获奖=${searchForm.has_award === 1 ? '已获奖' : '未获奖'}`)
  if (searchForm.budget_range && (searchForm.budget_range[0] > 0 || searchForm.budget_range[1] < 10)) {
    parts.push(`经费=¥${searchForm.budget_range[0]}万 ~ ¥${searchForm.budget_range[1]}万`)
  }
  const count = filteredData.value.length
  if (parts.length === 0) return `已查询全部归档项目，共 ${count} 项`
  return `已筛选：${parts.join('，')}，共 ${count} 项`
})

// ==================== 数据加载与筛选事件 ====================
/**
 * 加载全部归档项目。
 * 后端单页上限 200，故用 page_size=200 循环翻页，直到取满 total 或返回不足一页；
 * 一次取回后由前端完成筛选、排序与分页。
 * 副作用：写入 loading、rawData、total。
 */
async function loadData() {
  loading.value = true
  try {
    // status=9 表示已结题归档；后端单页上限 200，且筛选/排序在前端完成，故循环拉取全部页码
    const params: any = { page_size: 200, status: 9, keyword: searchForm.keyword }
    if (searchForm.project_type != null) params.project_type = searchForm.project_type
    if (searchForm.project_level != null) params.project_level = searchForm.project_level
    if (searchForm.year != null) params.year = searchForm.year
    const all: any[] = []
    for (let p = 1; p <= 50; p++) {
      const res = await getProjectList({ ...params, page: p })
      const items: any[] = res.data.items || []
      all.push(...items)
      const totalCount = Number(res.data.total || 0)
      if (all.length >= totalCount || items.length < params.page_size) break
    }
    rawData.value = all
    // 一次取回后在前端本地分页，故总数以实际取回的条数为准
    total.value = all.length
  } finally {
    loading.value = false
  }
}

/**
 * 执行查询：回到第 1 页、标记已查询（启用前端筛选与汇总），再重新拉取全量数据。
 */
function handleSearch() {
  page.value = 1
  searched.value = true
  loadData()
}

/**
 * 重置全部筛选条件与排序，退出已查询状态并重新加载全部归档数据。
 */
function handleReset() {
  searchForm.keyword = ''
  searchForm.year = undefined
  searchForm.project_type = undefined
  searchForm.project_level = undefined
  searchForm.has_award = undefined
  searchForm.budget_range = [0, 10]
  searchForm.sort_by = undefined
  page.value = 1
  searched.value = false
  loadData()
}

/**
 * 本地翻页：数据已全部在内存，仅更新页码与每页条数，不触发请求。
 * @param p 新页码
 * @param ps 新每页条数
 */
function handlePageChange(p: number, ps: number) {
  // 数据已在本地，翻页仅切换显示切片，无需重新请求
  page.value = p
  pageSize.value = ps
}

// ==================== 生命周期 ====================
// 首次进入即拉取全量归档数据，之后筛选、排序、翻页均在前端完成
onMounted(() => loadData())
</script>

<style scoped>
.search-card {
  margin-bottom: 16px;
}

.summary-alert {
  margin-bottom: 16px;
}
</style>
