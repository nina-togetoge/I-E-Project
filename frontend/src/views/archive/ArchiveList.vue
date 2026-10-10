<!--
  归档项目库
  历史项目检索、详情查看、成果预览
  F22 新增：高级搜索（类别/级别/获奖/经费/排序）+ 筛选汇总 + 展开收起
-->
<template>
  <div class="page-container">
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
            <el-option label="省部级" :value="3" />
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

    <el-alert
      v-if="searched && filterSummary"
      type="info"
      :closable="false"
      show-icon
      class="summary-alert"
    >
      <span v-html="filterSummary"></span>
    </el-alert>

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
        <el-tag v-if="row.award_count > 0 || row.has_award === 1" type="success" size="small">🏆 获奖</el-tag>
        <el-tag v-else type="info" size="small">未获奖</el-tag>
      </template>
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
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList } from '@/api/project'
import { formatDateTime } from '@/utils/format'
import { useProjectDetailStore } from '@/store/projectDetail'

const router = useRouter()
const projectDetailStore = useProjectDetailStore()

const showAdvanced = ref(false)
const searched = ref(false)

const searchForm = reactive({
  keyword: '',
  year: undefined as number | undefined,
  project_type: undefined as number | undefined,
  project_level: undefined as number | undefined,
  has_award: undefined as number | undefined,
  budget_range: [0, 10] as [number, number],
  sort_by: undefined as string | undefined,
})

const rawData = ref<any[]>([])
const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const currentYear = new Date().getFullYear()
const years = computed(() => Array.from({ length: 5 }, (_, i) => currentYear - i))

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

function projectTypeLabel(t: number): string {
  return { 1: '创新训练', 2: '创业训练', 3: '创业实践' }[t] || '-'
}

function projectLevelLabel(l: number): string {
  return { 1: '院级', 2: '校级', 3: '省部级' }[l] || '-'
}

function levelTagType(l: number): string {
  return { 1: 'info', 2: '', 3: 'success' }[l] || 'info'
}

function projectYearOf(d: any): number {
  const s = d.created_at || d.submit_time || d.end_date || ''
  if (!s) return 0
  const m = String(s).match(/(\d{4})/)
  return m ? Number(m[1]) : 0
}

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
    const budgetWan = Number(item.budget_amount || 0) / 10000
    if (searchForm.budget_range && Array.isArray(searchForm.budget_range) && searchForm.budget_range.length === 2) {
      const [lo, hi] = searchForm.budget_range
      if (budgetWan < lo || budgetWan > hi) return false
    }
    return true
  })
}

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

const filteredData = computed(() => {
  let list = frontendFilter(rawData.value)
  list = frontendSort(list)
  return list
})

const displayTotal = computed(() => {
  if (searched.value) return filteredData.value.length
  return total.value
})

const displayData = computed(() => {
  if (!searched.value) return tableData.value
  const start = (page.value - 1) * pageSize.value
  return filteredData.value.slice(start, start + pageSize.value)
})

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

async function loadData() {
  loading.value = true
  try {
    const params: any = { page: 1, page_size: 500, status: 9, keyword: searchForm.keyword }
    if (searchForm.project_type != null) params.project_type = searchForm.project_type
    if (searchForm.project_level != null) params.project_level = searchForm.project_level
    if (searchForm.year != null) params.year = searchForm.year
    const res = await getProjectList(params)
    const items: any[] = res.data.items || []
    rawData.value = items
    tableData.value = items.slice(0, pageSize.value)
    total.value = res.data.total || items.length
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  searched.value = true
  loadData()
}

function handleReset() {
  searchForm.keyword = ''
  searchForm.year = undefined
  searchForm.project_type = undefined
  searchForm.project_level = undefined
  searchForm.has_award = undefined
  searchForm.budget_range = [0, 10]
  searchForm.sort_by = undefined
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  if (!searched.value) {
    loadData()
  }
}

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
