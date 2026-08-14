<!--
  专家端 - 待评审项目列表
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
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
        <el-tag :type="row.status === 0 ? 'warning' : 'success'">
          {{ row.status === 0 ? '待评审' : '已评审' }}
        </el-tag>
      </template>
      <template #actions="{ row }">
        <el-button
          v-if="row.status === 0"
          link
          type="primary"
          size="small"
          @click="router.push(`/review/${row.id}`)"
        >
          评审
        </el-button>
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getReviewList } from '@/api/review'

const router = useRouter()
const searchForm = reactive({ keyword: '' })
const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const columns: TableColumn[] = [
  { prop: 'project_code', label: '项目编号', minWidth: 140 },
  { prop: 'project_title', label: '项目名称', minWidth: 200 },
  { prop: 'reviewer_name', label: '专家', width: 100 },
  { prop: 'status', label: '状态', slot: 'status', width: 100 },
  { prop: 'created_at', label: '分配时间', minWidth: 160 },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getReviewList({ page: page.value, page_size: pageSize.value, stage: 3, ...searchForm })
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; loadData() }
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
