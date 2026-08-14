<!--
  管理员端 - 经费管理
  经费台账总览、报销审批、预算执行率统计
-->
<template>
  <div class="page-container">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stat-row">
      <el-col :span="6">
        <el-card shadow="hover"><div class="stat-card">
          <p class="stat-value">¥ {{ summary.total_budget?.toFixed(2) || '0.00' }}</p>
          <p class="stat-label">总预算</p>
        </div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover"><div class="stat-card">
          <p class="stat-value">¥ {{ summary.total_expensed?.toFixed(2) || '0.00' }}</p>
          <p class="stat-label">已使用</p>
        </div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover"><div class="stat-card">
          <p class="stat-value">¥ {{ summary.total_remaining?.toFixed(2) || '0.00' }}</p>
          <p class="stat-label">剩余</p>
        </div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover"><div class="stat-card">
          <p class="stat-value">{{ summary.execution_rate || 0 }}%</p>
          <p class="stat-label">执行率</p>
        </div></el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="项目">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部" clearable style="width: 100px">
            <el-option label="待审批" :value="0" />
            <el-option label="已通过" :value="1" />
            <el-option label="已驳回" :value="2" />
          </el-select>
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
        <el-tag :type="row.status === 0 ? 'warning' : row.status === 1 ? 'success' : 'danger'">
          {{ ['待审批', '已通过', '已驳回'][row.status] }}
        </el-tag>
      </template>
      <template #actions="{ row }">
        <el-button v-if="row.status === 0" link type="success" size="small" @click="handleApprove(row, true)">通过</el-button>
        <el-button v-if="row.status === 0" link type="danger" size="small" @click="handleApprove(row, false)">驳回</el-button>
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { post, put } from '@/utils/request'

const searchForm = reactive({ keyword: '', status: undefined as number | undefined })
const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const summary = ref<any>({})

const columns: TableColumn[] = [
  { prop: 'project_title', label: '项目', minWidth: 200 },
  { prop: 'subject', label: '科目', width: 120 },
  { prop: 'amount', label: '金额(¥)', width: 100, formatter: (v: number) => `¥ ${v?.toFixed(2)}` },
  { prop: 'applicant_name', label: '申请人', width: 100 },
  { prop: 'status', label: '状态', slot: 'status', width: 100 },
  { prop: 'created_at', label: '申请时间', minWidth: 160 },
]

async function loadData() {
  loading.value = true
  try {
    const res = await post('/api/expenses/list', { page: page.value, page_size: pageSize.value, ...searchForm })
    tableData.value = res.data.items || []
    total.value = res.data.total || 0
    summary.value = res.data.summary || {}
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; loadData() }
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

async function handleApprove(row: any, approve: boolean) {
  if (!approve) {
    const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回', { type: 'warning' })
    await put(`/api/expenses/${row.id}/review`, { status: 2, opinion: value })
  } else {
    await put(`/api/expenses/${row.id}/review`, { status: 1, opinion: '同意' })
  }
  ElMessage.success(approve ? '已通过' : '已驳回')
  loadData()
}

onMounted(() => loadData())
</script>

<style scoped>
.stat-row { margin-bottom: 20px; }
.stat-card { text-align: center; }
.stat-value { font-size: 22px; font-weight: 600; color: #303133; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.search-card { margin-bottom: 16px; }
</style>
