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
            <el-option label="待校级复审" :value="3" />
            <el-option label="待分配评审专家" :value="13" />
            <el-option label="待专家评审" :value="5" />
            <el-option label="已立项" :value="6" />
            <el-option label="中期检查中" :value="7" />
            <el-option label="待结题" :value="8" />
            <el-option label="已结题" :value="9" />
            <el-option label="已撤销" :value="11" />
          </el-select>
        </el-form-item>
        <el-form-item label="学院">
          <el-select
            v-model="searchForm.college_id"
            :placeholder="userStore.isCollegeAdmin ? '本院' : '全部学院'"
            :clearable="!userStore.isCollegeAdmin"
            :disabled="userStore.isCollegeAdmin"
            style="width: 180px"
          >
            <el-option v-for="c in colleges" :key="c.id" :label="c.college_name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="searchForm.project_type" placeholder="全部类别" clearable style="width: 130px">
            <el-option label="创新训练" :value="1" />
            <el-option label="创业训练" :value="2" />
            <el-option label="创业实践" :value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="searchForm.project_level" placeholder="全部级别" clearable style="width: 130px">
            <el-option label="院级" :value="1" />
            <el-option label="校级" :value="2" />
            <el-option label="省级" :value="3" />
            <el-option label="国家级" :value="4" />
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
        <el-button link type="primary" size="small" @click="projectDetailStore.open(row.id)">详情</el-button>
        <el-button
          v-if="userStore.isAdmin && (row.status === 13 || row.status === 5) && (userStore.isSuperAdmin || row.college_id === userStore.collegeId)"
          link
          :type="row.assigned_expert_count > 0 ? 'success' : 'warning'"
          size="small"
          @click="openAssignDialog(row)"
        >
          {{ row.status === 13 ? '分配专家' : (row.assigned_expert_count > 0 ? `已分配(${row.assigned_expert_count})` : '分配专家') }}
        </el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="project" description="暂无项目数据" />
      </template>
    </PaginationTable>

    <!-- 专家分配弹窗 -->
    <el-dialog center v-model="assignDialogVisible" title="分配评审专家" width="500px">
      <el-alert
        v-if="currentProject?.reviewed_expert_count > 0"
        type="warning"
        :closable="false"
        show-icon
        title="已有专家提交评审，专家名单已锁定"
        description="评审已开始，调整名单会使已有评分与名单不一致，因此不再允许修改。"
        style="margin-bottom: 12px"
      />
      <el-select
        v-model="selectedExperts"
        multiple
        filterable
        placeholder="选择专家（至少 2 位）"
        :disabled="currentProject?.reviewed_expert_count > 0"
        style="width: 100%"
      >
        <el-option
          v-for="e in expertList"
          :key="e.id"
          :label="`${e.real_name}（${e.college_name || ''}）`"
          :value="e.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="assignDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="currentProject?.reviewed_expert_count > 0" @click="handleAssign">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Download } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList } from '@/api/project'
import { getColleges } from '@/api/auth'
import { getUserList } from '@/api/user'
import { assignExperts, getReviewHistory } from '@/api/review'
import { download } from '@/utils/request'
import { useUserStore } from '@/store/user'
import { useProjectDetailStore } from '@/store/projectDetail'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const projectDetailStore = useProjectDetailStore()

const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined,
  college_id: undefined as number | undefined,
  project_type: undefined as number | undefined,
  project_level: undefined as number | undefined,
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
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'project_level_name', label: '级别', width: 90 },
  { prop: 'leader_name', label: '负责人', width: 100 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'college_name', label: '学院', width: 120 },
  { prop: 'budget_amount', label: '预算(¥)', width: 100, formatter: (val: number) => Number(val || 0).toFixed(2) },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
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
  if (!userStore.isAdmin) {
    ElMessage.error('仅管理员可分配专家')
    return
  }
  if (!userStore.isSuperAdmin && row.college_id !== userStore.collegeId) {
    ElMessage.error('仅可分配本院项目的评审专家')
    return
  }
  currentProject.value = row
  selectedExperts.value = []
  // 并行加载专家列表和已分配专家；失败时提示且不打开弹窗（避免弹窗空白卡死）
  try {
    const [expertRes, flowRes] = await Promise.all([
      expertList.value.length > 0 ? Promise.resolve({ data: { items: expertList.value } }) : getUserList({ page: 1, page_size: 100, role: 3 }),
      row.assigned_expert_count > 0 ? getReviewHistory(row.id) : Promise.resolve(null),
    ])
    expertList.value = expertRes.data.items
    if (flowRes?.data?.assigned_expert_ids?.length) {
      selectedExperts.value = flowRes.data.assigned_expert_ids
    }
    assignDialogVisible.value = true
  } catch {
    ElMessage.error('加载专家列表失败，请稍后重试')
  }
}

async function handleAssign() {
  if (currentProject.value?.reviewed_expert_count > 0) {
    ElMessage.warning('已有专家提交评审，无法调整专家名单')
    return
  }
  // 与后端 ExpertAssignRequest(min_length=2) / settings.EXPERT_MIN_COUNT 保持一致
  if (selectedExperts.value.length < 2) {
    ElMessage.warning('每个项目至少需分配 2 位评审专家')
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
  // 学院列表加载失败不应阻断项目列表加载
  try {
    const res = await getColleges()
    colleges.value = res.data || []
  } catch {
    colleges.value = []
  }
  if (userStore.isCollegeAdmin) {
    searchForm.college_id = userStore.collegeId ?? undefined
  }
  if (route.query.status) {
    searchForm.status = Number(route.query.status)
  }
  if (route.query.type) {
    searchForm.project_type = Number(route.query.type)
  }
  loadData()
})
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
