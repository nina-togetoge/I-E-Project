<!--
  变更/延期申请审批（指导教师 / 超级管理员）
  项目处于「待校级复审(3)/待专家评审(5)」时，负责人可提交变更申请；
  由该项目的指导教师单级审批：通过 -> 按提交阶段退回（3→待学院初审，5→待校级复审）；
  驳回 -> 仅记录结果，项目停留在原阶段。
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部" clearable style="width: 160px">
            <el-option v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
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
      <template #change_type_name="{ row }">
        <el-tag size="small">{{ row.change_type_name || '—' }}</el-tag>
      </template>
      <template #status="{ row }">
        <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_name }}</el-tag>
      </template>
      <template #actions="{ row }">
        <template v-if="row.status === 0">
          <el-button link type="success" size="small" @click="handleApprove(row)">通过</el-button>
          <el-button link type="danger" size="small" @click="handleReject(row)">驳回</el-button>
        </template>
        <span v-else class="muted">—</span>
      </template>
      <template #empty>
        <EmptyIllustration type="project" description="暂无变更申请" />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getChangeList, approveChangeRequest, rejectChangeRequest } from '@/api/review'
import { formatDateTime } from '@/utils/format'

const STATUS_OPTIONS = [
  { value: 0, label: '待审核' },
  { value: 3, label: '已通过' },
  { value: 4, label: '已驳回' },
  { value: 5, label: '已撤回' },
]

const searchForm = reactive<{ status?: number }>({ status: 0 })

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'change_type_name', label: '类型', slot: 'change_type_name', width: 120 },
  { prop: 'change_reason', label: '变更原因', minWidth: 240 },
  { prop: 'status', label: '状态', slot: 'status', width: 100 },
  { prop: 'submit_time', label: '提交时间', width: 170, formatter: (_: any, row: any) => formatDateTime(row.submit_time) },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getChangeList({
      page: page.value,
      page_size: pageSize.value,
      status: searchForm.status,
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
  searchForm.status = 0
  handleSearch()
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

async function handleApprove(row: any) {
  try {
    await ElMessageBox.confirm(
      '通过后项目将退回上一审核阶段（待校级复审提交→退回学院初审；待专家评审提交→退回校级复审），需重新走后续审核流程。确定通过？',
      '通过变更申请',
      { type: 'warning', confirmButtonText: '确定通过', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await approveChangeRequest(row.id)
  ElMessage.success('已通过，项目已退回上一审核阶段')
  loadData()
}

async function handleReject(row: any) {
  let comment = ''
  try {
    const { value } = await ElMessageBox.prompt('请填写驳回理由', '驳回变更申请', {
      confirmButtonText: '确定驳回',
      cancelButtonText: '取消',
      inputPlaceholder: '驳回理由',
    })
    comment = value || ''
  } catch {
    return
  }
  await rejectChangeRequest(row.id, comment)
  ElMessage.success('已驳回')
  loadData()
}

function statusTagType(status: number): string {
  if (status === 3) return 'success'
  if (status === 4) return 'danger'
  if (status === 5) return 'info'
  return 'warning'
}

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
.muted { color: #c0c4cc; }
</style>
