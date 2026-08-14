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
    </PaginationTable>

    <!-- 新建报销弹窗 -->
    <el-dialog v-model="dialogVisible" title="新建报销申请" width="600px">
      <el-form ref="formRef" :model="expenseForm" :rules="formRules" label-width="100px">
        <el-form-item label="所属项目" prop="project_id">
          <el-select v-model="expenseForm.project_id" placeholder="请选择项目" style="width: 100%">
            <el-option v-for="p in myProjects" :key="p.id" :label="p.title" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="报销科目" prop="subject">
          <el-select v-model="expenseForm.subject" placeholder="请选择科目" style="width: 100%">
            <el-option label="材料费" value="材料费" />
            <el-option label="测试化验加工费" value="测试化验加工费" />
            <el-option label="差旅费" value="差旅费" />
            <el-option label="会议费" value="会议费" />
            <el-option label="劳务费" value="劳务费" />
            <el-option label="专家咨询费" value="专家咨询费" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额(元)" prop="amount">
          <el-input-number v-model="expenseForm.amount" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="事由说明" prop="description">
          <el-input v-model="expenseForm.description" type="textarea" :rows="3" placeholder="请说明报销事由" />
        </el-form-item>
        <el-form-item label="凭证附件">
          <FileUpload :accept="['.pdf', '.jpg', '.jpeg', '.png', '.zip']" @success="handleFileUpload" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, type FormInstance, type FormRules } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import FileUpload from '@/components/FileUpload.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList } from '@/api/project'
import { post } from '@/utils/request'

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const submitLoading = ref(false)
const myProjects = ref<any[]>([])

const columns: TableColumn[] = [
  { prop: 'id', label: '报销单号', width: 100 },
  { prop: 'project_title', label: '所属项目', minWidth: 200 },
  { prop: 'subject', label: '科目', width: 120 },
  { prop: 'amount', label: '金额(¥)', width: 100, formatter: (val: number) => `¥ ${val?.toFixed(2)}` },
  { prop: 'status', label: '状态', slot: 'status', width: 100 },
  { prop: 'created_at', label: '申请时间', minWidth: 160 },
]

const expenseForm = reactive({
  project_id: undefined as number | undefined,
  subject: '',
  amount: 0,
  description: '',
  attachments: [] as any[],
})

const formRules: FormRules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  subject: [{ required: true, message: '请选择科目', trigger: 'change' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }],
  description: [{ required: true, message: '请填写事由', trigger: 'blur' }],
}

async function loadData() {
  loading.value = true
  try {
    const res = await post('/api/expenses/list', {
      page: page.value,
      page_size: pageSize.value,
    })
    tableData.value = res.data.items || []
    total.value = res.data.total || 0
  } finally {
    loading.value = false
  }
}

async function loadMyProjects() {
  const res = await getProjectList({ page: 1, page_size: 100, status: 50 })
  myProjects.value = res.data.items
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

function handleFileUpload(file: any) {
  expenseForm.attachments.push(file)
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitLoading.value = true
    try {
      await post('/api/expenses', {
        project_id: expenseForm.project_id,
        subject: expenseForm.subject,
        amount: expenseForm.amount,
        description: expenseForm.description,
        attachments: expenseForm.attachments,
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
  const map: Record<number, string> = { 0: '待审批', 1: '已通过', 2: '已驳回', 3: '已报销' }
  return map[status] || '未知'
}

function expenseStatusType(status: number): string {
  const map: Record<number, string> = { 0: 'warning', 1: 'success', 2: 'danger', 3: '' }
  return map[status] || 'info'
}

onMounted(() => {
  loadData()
  loadMyProjects()
})
</script>

<style scoped>
.action-bar { margin-bottom: 16px; }
</style>
