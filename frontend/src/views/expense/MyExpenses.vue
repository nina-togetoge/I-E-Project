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
            <el-option v-for="p in myProjects" :key="p.id" :label="p.project_name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额(元)" prop="expense_amount">
          <el-input-number v-model="expenseForm.expense_amount" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="事由说明" prop="expense_desc">
          <el-input v-model="expenseForm.expense_desc" type="textarea" :rows="3" placeholder="请说明报销事由" />
        </el-form-item>
        <el-form-item label="发票号码">
          <el-input v-model="expenseForm.invoice_no" placeholder="选填" />
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
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList } from '@/api/project'
import service, { post } from '@/utils/request'

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
  { prop: 'expense_no', label: '报销单号', width: 160 },
  { prop: 'project_name', label: '所属项目', minWidth: 200 },
  { prop: 'expense_amount', label: '金额(¥)', width: 120, formatter: (val: number) => `¥ ${Number(val || 0).toFixed(2)}` },
  { prop: 'status', label: '状态', slot: 'status', width: 100 },
  { prop: 'created_at', label: '申请时间', minWidth: 160 },
]

const expenseForm = reactive({
  project_id: undefined as number | undefined,
  expense_amount: 0,
  expense_desc: '',
  invoice_no: '',
})

const formRules: FormRules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  expense_amount: [{ required: true, message: '请输入金额', trigger: 'blur' }],
  expense_desc: [{ required: true, message: '请填写事由', trigger: 'blur' }],
}

async function loadData() {
  loading.value = true
  try {
    // page/page_size 通过 URL Query 传（后端 PaginationParams = Depends() 读 Query）
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
  myProjects.value = res.data.items
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    submitLoading.value = true
    try {
      await post('/api/expenses', {
        project_id: expenseForm.project_id,
        expense_amount: expenseForm.expense_amount,
        expense_desc: expenseForm.expense_desc,
        invoice_no: expenseForm.invoice_no || undefined,
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
</style>
