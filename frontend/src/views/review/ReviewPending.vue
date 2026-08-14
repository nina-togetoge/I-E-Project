<!--
  待审核列表页（教师/管理员端）
  展示待审核项目，进入审核详情
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable />
        </el-form-item>
        <el-form-item label="审核阶段">
          <el-select v-model="searchForm.stage" placeholder="全部阶段" clearable style="width: 130px">
            <el-option label="学院初审" :value="1" />
            <el-option label="校级复审" :value="2" />
            <el-option label="专家评审" :value="3" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <template #stage="{ row }">
        <el-tag :type="stageTagType(row.review_stage)">{{ row.review_stage_name }}</el-tag>
      </template>
      <template #status="{ row }">
        <el-tag :type="row.review_result === 1 ? 'success' : 'danger'">
          {{ row.review_result_name || (row.review_result === 1 ? '通过' : '驳回') }}
        </el-tag>
      </template>
      <template #actions="{ row }">
        <el-button
          link
          type="primary"
          size="small"
          @click="router.push(`/review/${row.project_id}`)"
        >
          查看
        </el-button>
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getReviewList } from '@/api/review'

const router = useRouter()

const searchForm = reactive({
  keyword: '',
  stage: undefined as number | undefined,
})

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const columns: TableColumn[] = [
  { prop: 'project_id', label: '项目ID', width: 80 },
  { prop: 'review_stage', label: '审核阶段', slot: 'stage', width: 120 },
  { prop: 'reviewer_name', label: '审核人', width: 100 },
  { prop: 'review_result', label: '结果', slot: 'status', width: 100 },
  { prop: 'review_comment', label: '审核意见', minWidth: 200 },
  { prop: 'created_at', label: '创建时间', minWidth: 160 },
  { prop: 'review_time', label: '审核时间', minWidth: 160 },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getReviewList({
      page: page.value,
      page_size: pageSize.value,
      ...searchForm,
    })
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadData()
}

function handleReset() {
  searchForm.keyword = ''
  searchForm.stage = undefined
  handleSearch()
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

function stageTagType(stage: number): string {
  const map: Record<number, string> = { 1: '', 2: 'success', 3: 'warning' }
  return map[stage] || 'info'
}

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
