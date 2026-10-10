<!--
  报销申请页（学生端）
  填写报销单、上传凭证、查询进度
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="action-bar">
      <el-button type="primary" :icon="Plus" @click="dialogVisible = true">新建报销</el-button>
    </el-card>

    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <template #status="{ row }">
        <el-tag :type="expenseStatusType(row.status)">{{ expenseStatusLabel(row.status) }}</el-tag>
      </template>
      <template #flow="{ row }">
        <el-button link type="primary" size="small" @click="showFlowDialog(row)">查看流程</el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="file" description="暂无报销记录" />
      </template>
    </PaginationTable>

    <!-- 新建报销弹窗 -->
    <el-dialog center v-model="dialogVisible" title="新建报销申请" width="600px" @close="resetExpenseForm">
      <el-form ref="formRef" :model="expenseForm" :rules="formRules" label-width="100px">
        <el-form-item label="所属项目" prop="project_id">
          <el-select
            v-model="expenseForm.project_id"
            placeholder="请选择项目"
            style="width: 100%"
            @change="handleProjectChange"
          >
            <el-option v-for="p in myProjects" :key="p.id" :label="p.project_name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额(元)" prop="expense_amount">
          <el-input-number v-model="expenseForm.expense_amount" :min="0" :precision="2" style="width: 100%" />
          <div v-if="expenseForm.project_id" class="budget-info" :class="budgetClass">
            可用预算余额：¥ {{ Number(budgetRemain || 0).toFixed(2) }} / 总预算：¥ {{ Number(budgetTotal || 0).toFixed(2) }}
          </div>
        </el-form-item>
        <el-form-item label="事由说明" prop="expense_desc">
          <el-input v-model="expenseForm.expense_desc" type="textarea" :rows="3" placeholder="请说明报销事由" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="发票号码">
          <el-input v-model="expenseForm.invoice_no" placeholder="选填" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="凭证上传">
          <FileUpload
            :form-data="{ biz_type: 'expense', biz_id: 0 }"
            multiple
            list-type="picture-card"
            @success="handleFileSuccess"
            @remove="handleFileRemove"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="submitLoading"
          :disabled="budgetRemain < 0"
          @click="handleSubmit"
        >
          提交
        </el-button>
      </template>
    </el-dialog>

    <!-- 审批流程详情弹窗 -->
    <el-dialog center v-model="flowDialogVisible" title="报销审批流程" width="600px">
      <ApprovalFlow v-if="currentFlowRow" :status="currentFlowRow.status" :comment="currentFlowRow.reject_reason" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import ApprovalFlow from '@/components/ApprovalFlow.vue'
import FileUpload from '@/components/FileUpload.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList } from '@/api/project'
import { formatDateTime } from '@/utils/format'
import service, { post } from '@/utils/request'

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const dialogVisible = ref(false)
const flowDialogVisible = ref(false)
const currentFlowRow = ref<any>(null)
const formRef = ref<FormInstance>()
const submitLoading = ref(false)
const myProjects = ref<any[]>([])
const projectExpenseMap = reactive<Record<number, number>>({})

const columns: TableColumn[] = [
  { prop: 'expense_no', label: '报销单号', width: 160 },
  { prop: 'project_name', label: '所属项目', minWidth: 200 },
  { prop: 'expense_amount', label: '金额(¥)', width: 120, formatter: (val: number) => `¥ ${Number(val || 0).toFixed(2)}` },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
  { prop: 'flow', label: '审批进度', slot: 'flow', width: 100 },
  { prop: 'created_at', label: '申请时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

const expenseForm = reactive({
  project_id: undefined as number | undefined,
  expense_amount: 0,
  expense_desc: '',
  invoice_no: '',
  attachment_ids: [] as number[],
})

const selectedProject = computed(() =>
  expenseForm.project_id ? myProjects.value.find((p) => p.id === expenseForm.project_id) : null
)

const budgetTotal = computed(() => Number(selectedProject.value?.budget_amount || 0))

const budgetUsed = computed(() => {
  if (!expenseForm.project_id) return 0
  return projectExpenseMap[expenseForm.project_id] || 0
})

const budgetRemain = computed(() => budgetTotal.value - budgetUsed.value)

const budgetClass = computed(() => {
  if (budgetTotal.value === 0) return 'budget-normal'
  const ratio = budgetRemain.value / budgetTotal.value
  if (budgetRemain.value < 0) return 'budget-over'
  if (ratio < 0.2) return 'budget-warn'
  return 'budget-normal'
})

const formRules: FormRules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  expense_amount: [{ required: true, message: '请输入金额', trigger: 'blur' }],
  expense_desc: [{ required: true, message: '请填写事由', trigger: 'blur' }],
}

async function loadData() {
  loading.value = true
  try {
    const res: any = await service({
      method: 'post',
      url: '/api/expenses/list',
      params: { page: page.value, page_size: pageSize.value },
      data: {},
    })
    tableData.value = res.data.items || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadMyProjects() {
  const res = await getProjectList({ page: 1, page_size: 100, status: 6 })
  myProjects.value = res.data.items.map((p: any) => ({ ...p, budget_used: p.budget_used || 0 }))
}

async function handleProjectChange(projectId: number) {
  expenseForm.expense_amount = 0
  try {
    const res: any = await service({
      method: 'post',
      url: '/api/expenses/list',
      params: { page: 1, page_size: 1000 },
      data: { project_id: projectId },
    })
    const items: any[] = res.data.items || []
    const used = items
      .filter((e) => e.status <= 6)
      .reduce((sum, e) => sum + Number(e.expense_amount || 0), 0)
    projectExpenseMap[projectId] = used
  } catch {
    const proj = myProjects.value.find((p) => p.id === projectId)
    projectExpenseMap[projectId] = proj?.budget_used || 0
  }
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

function showFlowDialog(row: any) {
  currentFlowRow.value = row
  flowDialogVisible.value = true
}

function resetExpenseForm() {
  expenseForm.project_id = undefined
  expenseForm.expense_amount = 0
  expenseForm.expense_desc = ''
  expenseForm.invoice_no = ''
  expenseForm.attachment_ids = []
  formRef.value?.resetFields()
}

function handleFileSuccess(file: any) {
  if (file?.id && !expenseForm.attachment_ids.includes(file.id)) {
    expenseForm.attachment_ids.push(file.id)
  }
}

function handleFileRemove(file: any) {
  const id = file?.response?.data?.id
  if (id !== undefined) {
    const idx = expenseForm.attachment_ids.indexOf(id)
    if (idx > -1) expenseForm.attachment_ids.splice(idx, 1)
  }
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    if (expenseForm.expense_amount > budgetRemain.value) {
      ElMessage.error(`报销金额超过可用预算余额，剩余仅¥${Number(budgetRemain.value || 0).toFixed(2)}`)
      return
    }
    submitLoading.value = true
    try {
      await post('/api/expenses', {
        project_id: expenseForm.project_id,
        expense_amount: expenseForm.expense_amount,
        expense_desc: expenseForm.expense_desc,
        invoice_no: expenseForm.invoice_no || undefined,
        attachment_ids: expenseForm.attachment_ids,
      })
      ElMessage.success('报销申请已提交')
      dialogVisible.value = false
      loadData()
    } finally {
      submitLoading.value = false
    }
  })
}

function expenseStatusLabel(status: number) {
  const map: Record<number, string> = {
    0: '草稿',
    1: '待导师审批',
    2: '导师审批通过',
    3: '待学院审批',
    4: '学院审批通过',
    5: '待财务审批',
    6: '已完成',
    7: '已驳回',
  }
  return map[status] || '未知'
}

function expenseStatusType(status: number): string {
  const map: Record<number, string> = {
    0: 'info',       // 草稿
    1: 'warning',    // 待导师审批
    2: '',            // 导师审批通过
    3: 'warning',    // 待学院审批
    4: '',            // 学院审批通过
    5: 'warning',    // 待财务审批
    6: 'success',   // 已完成
    7: 'danger',    // 已驳回
  }
  return map[status] || 'info'
}

onMounted(() => {
  loadData()
  loadMyProjects()
})
</script>

<style scoped>
.action-bar { margin-bottom: 16px; }
.budget-info {
  margin-top: 8px;
  font-size: 13px;
  padding: 6px 10px;
  border-radius: 4px;
}
.budget-normal {
  color: var(--el-color-success);
  background-color: var(--el-color-success-light-9);
}
.budget-warn {
  color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
}
.budget-over {
  color: var(--el-color-danger);
  background-color: var(--el-color-danger-light-9);
}
</style>
