<!--
  操作日志查询页（管理员端）
  多条件筛选查询，支持导出
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="操作人/模块/描述" clearable />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker
            v-model="searchForm.dateRange"
            type="daterange"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DD"
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Download" @click="handleExport">导出</el-button>
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
      <template #operation_type="{ row }">
        <el-tag :type="opTypeTag(row.operation_type)">{{ row.operation_type }}</el-tag>
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Download } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getOperationLogs } from '@/api/common'
import { download } from '@/utils/request'

const searchForm = reactive({
  keyword: '',
  dateRange: [] as string[],
})

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const columns: TableColumn[] = [
  { prop: 'operator_name', label: '操作人', width: 100 },
  { prop: 'operator_role', label: '角色', width: 100 },
  { prop: 'module_name', label: '模块', width: 120 },
  { prop: 'operation_type', label: '操作类型', slot: 'operation_type', width: 100 },
  { prop: 'description', label: '描述', minWidth: 200 },
  { prop: 'ip_address', label: 'IP', width: 130 },
  { prop: 'created_at', label: '操作时间', minWidth: 160 },
]

async function loadData() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value, keyword: searchForm.keyword }
    if (searchForm.dateRange.length === 2) {
      params.start_time = searchForm.dateRange[0]
      params.end_time = searchForm.dateRange[1]
    }
    const res = await getOperationLogs(params)
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; loadData() }
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

async function handleExport() {
  await download('/api/logs/export', searchForm, '操作日志.xlsx')
  ElMessage.success('导出成功')
}

function opTypeTag(type: string): string {
  const map: Record<string, string> = { CREATE: 'success', UPDATE: 'warning', DELETE: 'danger', LOGIN: '', }
  return map[type] || 'info'
}

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
