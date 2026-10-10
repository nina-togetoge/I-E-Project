<!--
  待审核列表页（教师/管理员端）
  根据角色展示待当前用户审核的项目：
    教师 -> 待指导教师确认
    学院管理员 -> 待学院初审
    超管 -> 待校级复审
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable style="width: 220px" />
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
      <template #status="{ row }">
        <el-tag :type="statusTagType(row.status)">{{ row.status_name }}</el-tag>
      </template>
      <template #actions="{ row }">
        <el-button
          link
          type="primary"
          size="small"
          @click="router.push(`/review/${row.id}`)"
        >
          审核
        </el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="project" description="暂无待审核项目" />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getReviewList } from '@/api/review'

const router = useRouter()

const searchForm = reactive({
  keyword: '',
})

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 220 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'college_name', label: '学院', width: 160 },
  { prop: 'leader_name', label: '负责人', width: 100 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'budget_amount', label: '预算(元)', width: 120 },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getReviewList({
      page: page.value,
      page_size: pageSize.value,
      keyword: searchForm.keyword,
    } as any)
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
  handleSearch()
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

function statusTagType(status: number): string {
  const map: Record<number, string> = {
    12: 'warning', // 待指导教师确认
    1: 'primary',  // 待学院初审
    3: 'success',  // 待校级复审
  }
  return map[status] || 'info'
}

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
