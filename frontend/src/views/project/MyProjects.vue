<!--
  我的项目列表页（学生端）
  按状态筛选、查看详情、申报入口
-->
<template>
  <div class="page-container">
    <!-- 搜索 -->
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="项目名称">
          <el-input v-model="searchForm.keyword" placeholder="请输入关键词" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 130px">
            <el-option label="草稿" :value="0" />
            <el-option label="待学院初审" :value="1" />
            <el-option label="待校级复审" :value="3" />
            <el-option label="待专家评审" :value="5" />
            <el-option label="已立项" :value="6" />
            <el-option label="中期检查中" :value="7" />
            <el-option label="待结题" :value="8" />
            <el-option label="已结题" :value="9" />
            <el-option label="已驳回" :value="10" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 操作栏 -->
    <div class="action-bar">
      <el-button type="primary" :icon="EditPen" @click="router.push('/projects/create')">新建项目申报</el-button>
    </div>

    <!-- 表格 -->
    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <template #status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #actions="{ row }">
        <el-button link type="primary" size="small" @click="router.push(`/projects/${row.id}`)">查看</el-button>
        <el-button v-if="row.status === 0" link type="warning" size="small" @click="handleEdit(row)">编辑</el-button>
        <el-button v-if="row.status === 0" link type="success" size="small" @click="handleSubmit(row)">提交</el-button>
        <el-button v-if="row.status === 0" link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, EditPen } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList, submitProject, deleteProject } from '@/api/project'

const router = useRouter()

const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined,
})

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const columns: TableColumn[] = [
  { prop: 'project_no', label: '项目编号', minWidth: 140 },
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'budget_amount', label: '预算(¥)', width: 100, formatter: (val: number) => Number(val || 0).toFixed(2) },
  { prop: 'status', label: '状态', slot: 'status', width: 100 },
  { prop: 'created_at', label: '创建时间', minWidth: 160 },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getProjectList({
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
  searchForm.status = undefined
  handleSearch()
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

function handleEdit(row: any) {
  router.push(`/projects/create?id=${row.id}`)
}

async function handleSubmit(row: any) {
  await ElMessageBox.confirm(`确定提交项目「${row.project_name}」进入审核流程？提交后不可修改`, '提示', { type: 'warning' })
  await submitProject(row.id)
  ElMessage.success('已提交，等待审核')
  loadData()
}

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确定删除项目「${row.project_name}」？`, '提示', { type: 'warning' })
  await deleteProject(row.id)
  ElMessage.success('删除成功')
  loadData()
}

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
.action-bar { margin-bottom: 16px; }
</style>
