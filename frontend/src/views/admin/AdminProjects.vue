<!--
  管理员端 - 项目全量管理
  多条件筛选、查看详情、专家分配、导出
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 150px">
            <el-option label="草稿" :value="0" />
            <el-option label="待学院初审" :value="1" />
            <el-option label="学院初审通过" :value="2" />
            <el-option label="待校级复审" :value="3" />
            <el-option label="校级复审通过" :value="4" />
            <el-option label="待专家评审" :value="5" />
            <el-option label="已立项" :value="6" />
            <el-option label="中期检查中" :value="7" />
            <el-option label="待结题" :value="8" />
            <el-option label="已结题" :value="9" />
            <el-option label="已驳回" :value="10" />
            <el-option label="已撤销" :value="11" />
          </el-select>
        </el-form-item>
        <el-form-item label="学院">
          <el-select v-model="searchForm.college_id" placeholder="全部学院" clearable style="width: 180px">
            <el-option v-for="c in colleges" :key="c.id" :label="c.college_name" :value="c.id" />
          </el-select>
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
      <template #status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #actions="{ row }">
        <el-button link type="primary" size="small" @click="router.push(`/projects/${row.id}`)">详情</el-button>
        <el-button v-if="row.status === 4 || row.status === 5" link type="warning" size="small" @click="openAssignDialog(row)">
          分配专家
        </el-button>
      </template>
    </PaginationTable>

    <!-- 专家分配弹窗 -->
    <el-dialog v-model="assignDialogVisible" title="分配评审专家" width="500px">
      <el-select v-model="selectedExperts" multiple filterable placeholder="选择专家" style="width: 100%">
        <el-option
          v-for="e in expertList"
          :key="e.id"
          :label="`${e.real_name}（${e.college_name || ''}）`"
          :value="e.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="assignDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAssign">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Download } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList, exportProjects } from '@/api/project'
import { getColleges } from '@/api/auth'
import { getUserList } from '@/api/user'
import { assignExperts } from '@/api/review'
import { download } from '@/utils/request'

const router = useRouter()

const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined,
  college_id: undefined as number | undefined,
})

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const colleges = ref<any[]>([])
const expertList = ref<any[]>([])
const assignDialogVisible = ref(false)
const selectedExperts = ref<number[]>([])
const currentProject = ref<any>(null)

const columns: TableColumn[] = [
  { prop: 'project_no', label: '项目编号', minWidth: 140 },
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'leader_name', label: '负责人', width: 100 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'college_name', label: '学院', width: 120 },
  { prop: 'budget_amount', label: '预算(¥)', width: 100, formatter: (val: number) => val?.toFixed(2) || '0.00' },
  { prop: 'status', label: '状态', slot: 'status', width: 100 },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getProjectList({ page: page.value, page_size: pageSize.value, ...searchForm })
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

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

async function handleExport() {
  await download('/api/excel/export/projects', searchForm, '项目名单.xlsx')
  ElMessage.success('导出成功')
}

async function openAssignDialog(row: any) {
  currentProject.value = row
  selectedExperts.value = []
  if (expertList.value.length === 0) {
    const res = await getUserList({ page: 1, page_size: 100, role: 3 })
    expertList.value = res.data.items
  }
  assignDialogVisible.value = true
}

async function handleAssign() {
  if (selectedExperts.value.length === 0) {
    ElMessage.warning('请至少选择一名专家')
    return
  }
  await assignExperts({
    project_id: currentProject.value.id,
    expert_ids: selectedExperts.value,
  })
  ElMessage.success('专家分配成功')
  assignDialogVisible.value = false
  loadData()
}

onMounted(async () => {
  const res = await getColleges()
  colleges.value = res.data || []
  loadData()
})
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
