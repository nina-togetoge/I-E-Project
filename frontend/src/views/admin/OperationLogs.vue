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
        <el-form-item>
          <el-button type="primary" link @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '收起筛选 ▲' : '高级筛选 ▼' }}
          </el-button>
        </el-form-item>
      </el-form>

      <el-form v-show="showAdvanced" :inline="true" :model="searchForm" style="margin-top: 12px; border-top: 1px solid #ebeef5; padding-top: 12px;">
        <el-form-item label="模块">
          <el-select v-model="searchForm.modules" multiple placeholder="全部模块" clearable style="width: 220px">
            <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="操作类型">
          <el-select v-model="searchForm.operation_types" multiple placeholder="全部类型" clearable style="width: 260px">
            <el-option v-for="t in operationTypeOptions" :key="t.value" :value="t.value">
              <el-tag :type="t.tagType" size="small" effect="light">{{ t.value }}</el-tag>
              <span style="margin-left: 6px;">{{ t.label }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="操作人角色">
          <el-select v-model="searchForm.user_roles" multiple placeholder="全部角色" clearable style="width: 200px">
            <el-option label="学生" :value="1" />
            <el-option label="教师" :value="2" />
            <el-option label="专家" :value="3" />
            <el-option label="管理员" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item label="结果">
          <el-select v-model="searchForm.statuses" multiple placeholder="全部结果" clearable style="width: 180px">
            <el-option :value="'success'">
              <el-tag type="success" size="small" effect="light">成功</el-tag>
            </el-option>
            <el-option :value="'fail'">
              <el-tag type="danger" size="small" effect="light">失败</el-tag>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="handleResetAdvanced">重置条件</el-button>
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
      <template #user_role="{ row }">
        <el-tag :type="roleTagType(row.user_role)">{{ roleLabel(row.user_role) }}</el-tag>
      </template>
      <template #status="{ row }">
        <el-tag :type="row.status === 'success' || row.status === 1 ? 'success' : 'danger'" size="small">
          {{ row.status === 'success' || row.status === 1 ? '成功' : '失败' }}
        </el-tag>
      </template>
      <template #empty>
        <EmptyIllustration type="default" description="暂无操作日志" />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Download } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getOperationLogs } from '@/api/common'
import { download } from '@/utils/request'
import { formatDateTime } from '@/utils/format'
import { useDebounce } from '@/composables/useDebounce'

const showAdvanced = ref(false)

const moduleOptions = ['项目管理', '审核管理', '报销管理', '用户管理', '文件管理', '系统管理', '认证模块']
const operationTypeOptions: { value: string; label: string; tagType: string }[] = [
  { value: 'CREATE', label: '新增', tagType: 'success' },
  { value: 'UPDATE', label: '更新', tagType: 'warning' },
  { value: 'DELETE', label: '删除', tagType: 'danger' },
  { value: 'LOGIN', label: '登录', tagType: 'info' },
  { value: 'EXPORT', label: '导出', tagType: 'primary' },
  { value: 'IMPORT', label: '导入', tagType: '' },
]

const searchForm = reactive({
  keyword: '',
  dateRange: [] as string[],
  modules: [] as string[],
  operation_types: [] as string[],
  user_roles: [] as number[],
  statuses: [] as string[],
})

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const columns: TableColumn[] = [
  { prop: 'real_name', label: '操作人', width: 100 },
  { prop: 'user_role', label: '角色', slot: 'user_role', width: 100 },
  { prop: 'module_name', label: '模块', width: 120 },
  { prop: 'operation_type', label: '操作类型', slot: 'operation_type', width: 100 },
  { prop: 'operation_desc', label: '描述', minWidth: 200 },
  { prop: 'ip_address', label: 'IP', width: 130 },
  { prop: 'status', label: '结果', slot: 'status', width: 80 },
  { prop: 'operation_time', label: '操作时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

async function loadData() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value, keyword: searchForm.keyword }
    if (searchForm.dateRange.length === 2) {
      params.start_time = searchForm.dateRange[0]
      params.end_time = searchForm.dateRange[1]
    }
    if (searchForm.modules.length > 0) params.modules = searchForm.modules.join(',')
    if (searchForm.operation_types.length > 0) params.operation_types = searchForm.operation_types.join(',')
    if (searchForm.user_roles.length > 0) params.user_roles = searchForm.user_roles.join(',')
    if (searchForm.statuses.length > 0) params.statuses = searchForm.statuses.join(',')
    const res = await getOperationLogs(params)
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

const debouncedLoadData = useDebounce(loadData, 400)

watch(
  () => [
    searchForm.keyword,
    searchForm.dateRange?.[0],
    searchForm.dateRange?.[1],
    searchForm.modules.length,
    searchForm.operation_types.length,
    searchForm.user_roles.length,
    searchForm.statuses.length,
  ],
  () => {
    page.value = 1
    debouncedLoadData()
  }
)

function handleSearch() { page.value = 1; debouncedLoadData.flush() }
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

function handleResetAdvanced() {
  searchForm.modules = []
  searchForm.operation_types = []
  searchForm.user_roles = []
  searchForm.statuses = []
}

async function handleExport() {
  const params: any = { ...searchForm }
  if (searchForm.modules.length > 0) params.modules = searchForm.modules.join(',')
  if (searchForm.operation_types.length > 0) params.operation_types = searchForm.operation_types.join(',')
  if (searchForm.user_roles.length > 0) params.user_roles = searchForm.user_roles.join(',')
  if (searchForm.statuses.length > 0) params.statuses = searchForm.statuses.join(',')
  await download('/api/excel/export/logs', params, '操作日志.xlsx')
  ElMessage.success('导出成功')
}

function opTypeTag(type: string): string {
  const map: Record<string, string> = { CREATE: 'success', UPDATE: 'warning', DELETE: 'danger', LOGIN: 'info', EXPORT: 'primary', IMPORT: '' }
  return map[type] || 'info'
}

function roleLabel(role: number) {
  const map: Record<number, string> = { 1: '学生', 2: '教师', 3: '专家', 4: '管理员' }
  return map[role] || '-'
}

function roleTagType(role: number): string {
  const map: Record<number, string> = { 1: '', 2: 'success', 3: 'warning', 4: 'danger' }
  return map[role] || 'info'
}

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
