<!--
  我的项目列表页（学生端）
  按状态筛选、查看详情、申报入口
-->
<template>
  <div class="page-container" id="my-projects-print">
    <!-- 搜索 -->
    <el-card shadow="never" class="search-card no-print">
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
    <div class="action-bar no-print">
      <el-button type="primary" :icon="EditPen" @click="router.push('/projects/create')">新建项目申报</el-button>

      <template v-if="selectedRows.length > 0">
        <el-divider direction="vertical" />
        <span style="color: #606266; margin-right: 8px;">已选 <b style="color: var(--el-color-primary);">{{ selectedRows.length }}</b> 项</span>
        <el-button :icon="Download" @click="handleBatchExport">批量导出 Excel</el-button>
        <el-button :icon="Printer" @click="handleBatchPrint">批量打印申请书</el-button>
        <el-button
          type="success"
          :icon="Check"
          :disabled="draftSelectedIds.length === 0"
          @click="handleBatchSubmit"
        >
          批量提交{{ draftSelectedIds.length > 0 ? `(${draftSelectedIds.length})` : '' }}
        </el-button>
        <el-button
          type="danger"
          :icon="Delete"
          :disabled="draftSelectedIds.length === 0"
          @click="handleBatchDelete"
        >
          批量删除{{ draftSelectedIds.length > 0 ? `(${draftSelectedIds.length})` : '' }}
        </el-button>
      </template>
    </div>

    <!-- 表格 -->
    <PaginationTable
      :data="sortedTableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      :selection="true"
      @page-change="handlePageChange"
      @selection-change="handleSelectionChange"
    >
      <template #status="{ row }">
        <StatusTag :status="row.status" />
      </template>
      <template #actions="{ row }">
        <el-button link type="primary" size="small" @click="projectDetailStore.open(row.id)">查看</el-button>
        <el-button v-if="canEdit(row)" link type="warning" size="small" @click="handleEdit(row)">编辑</el-button>
        <el-button v-if="canSubmit(row)" link type="success" size="small" @click="handleSubmit(row)">提交</el-button>
        <el-button v-if="canWithdraw(row)" link type="danger" size="small" @click="handleWithdraw(row)">撤回</el-button>
        <el-button v-if="row.status === 0" link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="project" description="暂无项目，快去创建一个吧" />
      </template>
    </PaginationTable>

    <!-- 编辑弹窗 -->
    <el-dialog
      center
      v-model="editDialogVisible"
      title="编辑项目"
      width="720px"
      :close-on-click-modal="false"
      @closed="editingId = null"
    >
      <div v-loading="editLoading">
        <el-form :model="editForm" label-width="100px">
          <el-form-item label="项目名称" required>
            <el-input v-model="editForm.project_name" placeholder="请输入项目名称" maxlength="100" show-word-limit />
          </el-form-item>
          <el-form-item label="项目类别" required>
            <el-select v-model="editForm.project_type" placeholder="请选择类别" style="width: 100%">
              <el-option label="创新训练项目" :value="1" />
              <el-option label="创业训练项目" :value="2" />
              <el-option label="创业实践项目" :value="3" />
            </el-select>
          </el-form-item>
          <el-form-item label="项目级别">
            <el-select v-model="editForm.project_level" placeholder="请选择级别" style="width: 100%">
              <el-option label="院级" :value="1" />
              <el-option label="校级" :value="2" />
              <el-option label="省部级" :value="3" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属学院" required>
            <el-select v-model="editForm.college_id" filterable placeholder="请选择学院" style="width: 100%">
              <el-option v-for="c in collegeOptions" :key="c.id" :label="c.college_name" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="参赛比赛">
            <el-select v-model="editForm.competition_id" filterable placeholder="请选择参加的比赛（可选）" clearable style="width: 100%">
              <el-option v-for="c in competitionOptions" :key="c.id" :label="c.title" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="指导教师" required>
            <el-select
              v-model="editForm.teacher_id"
              filterable
              remote
              :remote-method="searchTeacher"
              :loading="teacherLoading"
              placeholder="输入教师姓名搜索"
              style="width: 100%"
            >
              <el-option
                v-for="t in teacherOptions"
                :key="t.id"
                :label="`${t.real_name}（${t.college_name || ''}）`"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="摘要">
            <el-input v-model="editForm.project_summary" type="textarea" :rows="3" placeholder="200字以内的项目摘要" maxlength="200" show-word-limit />
          </el-form-item>
          <el-form-item label="开始日期">
            <el-date-picker v-model="editForm.start_date" type="date" placeholder="选择开始日期" style="width: 100%" />
          </el-form-item>
          <el-form-item label="结束日期">
            <el-date-picker v-model="editForm.end_date" type="date" placeholder="选择结束日期" style="width: 100%" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button type="primary" :loading="editSaving" @click="handleEditConfirm">确定</el-button>
        <el-button :loading="editSaving" @click="handleEditSaveDraft">暂存</el-button>
        <el-button @click="editDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, EditPen, Download, Printer, Check, Delete } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList, submitProject, deleteProject, exportProjects, withdrawProject, getProjectDetail, updateProject } from '@/api/project'
import { getColleges } from '@/api/auth'
import { getCompetitionList } from '@/api/competition'
import { getUserList } from '@/api/user'
import * as XLSX from 'xlsx'
import { saveAs } from 'file-saver'
import { STATUS_LABELS } from '@/api/types'
import { formatDateTime } from '@/utils/format'
import { useDebounce } from '@/composables/useDebounce'
import { useProjectDetailStore } from '@/store/projectDetail'

const router = useRouter()
const projectDetailStore = useProjectDetailStore()

const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined,
})

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const selectedRows = ref<any[]>([])

// ==================== 编辑弹窗 ====================
const editDialogVisible = ref(false)
const editingId = ref<number | null>(null)
const editLoading = ref(false)
const editSaving = ref(false)
const editForm = reactive({
  project_name: '',
  project_type: undefined as number | undefined,
  project_level: 1 as number,
  college_id: undefined as number | undefined,
  competition_id: undefined as number | undefined,
  project_summary: '',
  start_date: '',
  end_date: '',
  teacher_id: undefined as number | undefined,
})
const collegeOptions = ref<any[]>([])
const competitionOptions = ref<any[]>([])
const teacherOptions = ref<any[]>([])
const teacherLoading = ref(false)

async function loadEditForm(id: number) {
  editLoading.value = true
  try {
    const [detailRes, collegeRes, compRes] = await Promise.all([
      getProjectDetail(id),
      getColleges().catch(() => ({ data: [] })),
      getCompetitionList({ page: 1, page_size: 100 }).catch(() => ({ data: { items: [] } })),
    ])
    const p = detailRes.data
    editForm.project_name = p.project_name || ''
    editForm.project_type = p.project_type
    editForm.project_level = p.project_level || 1
    editForm.college_id = p.college_id
    editForm.competition_id = p.competition_id ?? undefined
    editForm.project_summary = p.project_summary || ''
    editForm.start_date = p.start_date || ''
    editForm.end_date = p.end_date || ''
    editForm.teacher_id = p.teacher_id ?? undefined
    collegeOptions.value = (collegeRes as any).data || []
    competitionOptions.value = ((compRes as any).data?.items || []).filter((c: any) => [1, 2].includes(c.status))
    // 教师：若有 teacher_id 直接填充，否则按姓名搜索
    if (p.teacher_id) {
      teacherOptions.value = [{ id: p.teacher_id, real_name: p.teacher_name || '' }]
      editForm.teacher_id = p.teacher_id
    } else if (p.teacher_name) {
      try {
        const tRes: any = await getUserList({ keyword: p.teacher_name, role: 2, page: 1, page_size: 10 })
        const items = tRes.data?.items || []
        const matched = items.find((t: any) => t.real_name === p.teacher_name) || items[0]
        if (matched) {
          teacherOptions.value = [matched]
          editForm.teacher_id = matched.id
        }
      } catch { /* ignore */ }
    }
  } catch {
    ElMessage.error('加载项目数据失败')
  } finally {
    editLoading.value = false
  }
}

async function searchTeacher(query: string) {
  if (!query) { teacherOptions.value = []; return }
  teacherLoading.value = true
  try {
    const res: any = await getUserList({ keyword: query, role: 2, page: 1, page_size: 20 })
    teacherOptions.value = res.data?.items || []
  } catch { ElMessage.error('教师搜索失败') }
  finally { teacherLoading.value = false }
}

function buildEditPayload() {
  return {
    project_name: editForm.project_name,
    project_type: editForm.project_type,
    project_level: editForm.project_level,
    college_id: editForm.college_id,
    competition_id: editForm.competition_id || null,
    project_summary: editForm.project_summary,
    start_date: editForm.start_date || null,
    end_date: editForm.end_date || null,
    teacher_id: editForm.teacher_id || null,
  }
}

async function handleEditSaveDraft() {
  if (!editingId.value) return
  editSaving.value = true
  try {
    await updateProject(editingId.value, buildEditPayload())
    ElMessage.success('暂存成功')
    editDialogVisible.value = false
    loadData()
  } finally { editSaving.value = false }
}

async function handleEditConfirm() {
  if (!editingId.value) return
  if (!editForm.project_name.trim()) { ElMessage.warning('请输入项目名称'); return }
  if (!editForm.project_type) { ElMessage.warning('请选择项目类别'); return }
  if (!editForm.college_id) { ElMessage.warning('请选择所属学院'); return }
  if (!editForm.teacher_id) { ElMessage.warning('请选择指导教师'); return }
  editSaving.value = true
  try {
    await updateProject(editingId.value, buildEditPayload())
    await submitProject(editingId.value)
    ElMessage.success('已提交，等待审核')
    editDialogVisible.value = false
    loadData()
  } finally { editSaving.value = false }
}

const draftSelectedIds = computed(() => selectedRows.value.filter((r) => r.status === 0).map((r) => r.id))

const sortedTableData = computed(() => {
  return [...tableData.value]
})

const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'competition_name', label: '参赛比赛', minWidth: 180, formatter: (val: string) => val || '-' },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
  { prop: 'created_at', label: '创建时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

function handleSelectionChange(rows: any[]) {
  selectedRows.value = rows
}

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

const debouncedLoadData = useDebounce(loadData, 400)

watch(
  () => [searchForm.keyword, searchForm.status],
  () => {
    page.value = 1
    debouncedLoadData()
  }
)

function handleSearch() {
  page.value = 1
  debouncedLoadData.flush()
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

// ==================== 操作按钮权限判断 ====================
// 可编辑：草稿或已驳回
function canEdit(row: any) {
  return row.status === 0 || row.status === 10
}
// 可提交：草稿或已驳回
function canSubmit(row: any) {
  return row.status === 0 || row.status === 10
}
// 可撤回：已提交待审核的状态（12待教师确认、1待学院、2学院通过、3待校级、4校级通过、5待专家）
function canWithdraw(row: any) {
  return [12, 1, 2, 3, 4, 5].includes(row.status)
}

function handleEdit(row: any) {
  editingId.value = row.id
  editDialogVisible.value = true
  loadEditForm(row.id)
}

async function handleSubmit(row: any) {
  await ElMessageBox.confirm(`确定提交项目「${row.project_name}」进入审核流程？提交后不可修改`, '提示', { type: 'warning' })
  await submitProject(row.id)
  ElMessage.success('已提交，等待审核')
  loadData()
}

async function handleWithdraw(row: any) {
  await ElMessageBox.confirm(`确定撤回项目「${row.project_name}」？撤回后可重新编辑提交`, '提示', { type: 'warning' })
  await withdrawProject(row.id)
  ElMessage.success('已撤回')
  loadData()
}

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确定删除项目「${row.project_name}」？`, '提示', { type: 'warning' })
  await deleteProject(row.id)
  ElMessage.success('删除成功')
  loadData()
}

// ==================== 批量操作 ====================

async function handleBatchExport() {
  if (selectedRows.value.length === 0) return
  try {
    const ids = selectedRows.value.map((r) => r.id).join(',')
    await exportProjects({ ...searchForm })
    ElMessage.success('导出任务已触发')
  } catch {
    const exportData = selectedRows.value.map((r) => ({
      项目编号: r.project_no || '-',
      项目名称: r.project_name,
      项目类别: r.project_type_name,
      项目级别: r.project_level_name,
      负责人: r.leader_name,
      指导教师: r.teacher_name || '-',
      所属学院: r.college_name,
      预算金额: Number(r.budget_amount || 0).toFixed(2),
      状态: STATUS_LABELS[r.status] || r.status,
      创建时间: formatDateTime(r.created_at),
      提交时间: formatDateTime(r.submit_time) || '-',
    }))
    const ws = XLSX.utils.json_to_sheet(exportData)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '项目列表')
    const excelBuf = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    const blob = new Blob([excelBuf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const fileName = `我的项目列表_${new Date().toISOString().slice(0, 10)}.xlsx`
    saveAs(blob, fileName)
    ElMessage.success(`已导出 ${selectedRows.value.length} 条数据`)
  }
}

function handleBatchPrint() {
  if (selectedRows.value.length === 0) return
  const style = document.createElement('style')
  style.className = 'print-temp-style'
  style.innerHTML = `
    @media print {
      .no-print { display: none !important; }
      body { background: #fff !important; }
      .el-table th, .el-table td { color: #333 !important; border-color: #999 !important; }
      .el-card { box-shadow: none !important; border: none !important; }
    }
  `
  document.head.appendChild(style)
  window.print()
  setTimeout(() => {
    const s = document.querySelector('.print-temp-style')
    if (s) s.remove()
  }, 500)
}

async function handleBatchSubmit() {
  if (draftSelectedIds.value.length === 0) return
  const n = draftSelectedIds.value.length
  await ElMessageBox.confirm(
    `确定提交选中的 ${n} 个草稿项目进入审核流程？提交后不可修改。（非草稿项目将被自动跳过）`,
    '批量提交确认',
    { type: 'warning' }
  )
  let success = 0
  let fail = 0
  for (const id of draftSelectedIds.value) {
    try {
      await submitProject(id)
      success++
    } catch {
      fail++
    }
  }
  ElMessage.success(`批量提交完成：成功 ${success} 个，失败 ${fail} 个`)
  selectedRows.value = []
  loadData()
}

async function handleBatchDelete() {
  if (draftSelectedIds.value.length === 0) return
  const n = draftSelectedIds.value.length
  await ElMessageBox.confirm(
    `确定删除选中的 ${n} 个草稿项目？删除后不可恢复。（非草稿项目将被自动跳过）`,
    '批量删除确认',
    { type: 'warning' }
  )
  let success = 0
  let fail = 0
  for (const id of draftSelectedIds.value) {
    try {
      await deleteProject(id)
      success++
    } catch {
      fail++
    }
  }
  ElMessage.success(`批量删除完成：成功 ${success} 个，失败 ${fail} 个`)
  selectedRows.value = []
  loadData()
}

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
.action-bar { margin-bottom: 16px; }
</style>
