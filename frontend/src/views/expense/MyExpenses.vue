<!--
  ==== 报销申请（学生端） ====
  解决的问题：学生项目经费不能线下口头报销，需要在线填单、上传凭证并跟踪多级审批进度。
  对应角色与路由：role=1 学生，路由 /expenses（仅学生可见）。
  依赖 API：
    - POST /api/expenses/list 查询我的报销记录；POST /api/expenses 新建报销单；
    - GET /api/project（getProjectList，status=6）拉取已立项项目作为可报销对象；
    - FileUpload 组件上传凭证后回传文件 id，作为 attachment_ids 提交。
  业务规则：
    - 只能对已立项(status=6)的项目报销，且金额不得超过项目可用预算余额。
    - 可用余额 = 预算总额 - 已占用金额；已占用金额按该项目状态 <=6 的报销单累加，
      驳回(7)的单据不计入占用，避免被驳回后无法再次报销。
    - 报销状态流转：0草稿 -> 1待导师 -> 2导师通过 -> 3待学院 -> 4学院通过 -> 5待财务 -> 6完成；
      任一环节 7=驳回，学生需重新提交。
  关键交互流程：新建报销 -> 选项目（自动带出预算余额）-> 填金额/事由/凭证 -> 前端超额校验 ->
    提交成功刷新列表；列表可「查看流程」查看当前审批到哪一步及驳回原因。
-->
<template>
  <div class="page-container">
    <!-- 区块：操作栏，唯一入口是新建报销弹窗 -->
    <el-card shadow="never" class="action-bar">
      <el-button type="primary" :icon="Plus" @click="dialogVisible = true">新建报销</el-button>
    </el-card>

    <!-- 区块：我的报销记录列表，状态与审批进度分列展示 -->
    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <!-- 状态列：将 0~7 后端状态码翻译为中文并着色 -->
      <template #status="{ row }">
        <el-tag :type="expenseStatusType(row.status)">{{ expenseStatusLabel(row.status) }}</el-tag>
      </template>
      <!-- 审批进度列：打开流程弹窗，展示多级审批节点与驳回原因 -->
      <template #flow="{ row }">
        <el-button link type="primary" size="small" @click="showFlowDialog(row)">查看流程</el-button>
      </template>
      <!-- 空状态：尚无报销记录时的引导提示 -->
      <template #empty>
        <EmptyIllustration type="file" description="暂无报销记录" />
      </template>
    </PaginationTable>

    <!-- 区块：新建报销弹窗，选择项目后实时显示预算余额，金额超额时禁止提交 -->
    <el-dialog center v-model="dialogVisible" title="新建报销申请" width="600px" @close="resetExpenseForm">
      <el-form ref="formRef" :model="expenseForm" :rules="formRules" label-width="100px">
        <!-- 所属项目：仅列出已立项项目，切换项目会重置金额并刷新该项目的已用预算 -->
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
        <!-- 金额与预算提示：余额为负标红并禁用提交，低于 20% 余额给出预警色 -->
        <el-form-item label="金额(元)" prop="expense_amount">
          <el-input-number v-model="expenseForm.expense_amount" :min="0" :precision="2" style="width: 100%" />
          <div v-if="expenseForm.project_id" class="budget-info" :class="budgetClass">
            可用预算余额：¥ {{ Number(budgetRemain || 0).toFixed(2) }} / 总预算：¥ {{ Number(budgetTotal || 0).toFixed(2) }}
          </div>
        </el-form-item>
        <!-- 事由说明：必填，最多 500 字，审批人据此判断支出合理性 -->
        <el-form-item label="事由说明" prop="expense_desc">
          <el-input v-model="expenseForm.expense_desc" type="textarea" :rows="3" placeholder="请说明报销事由" maxlength="500" show-word-limit />
        </el-form-item>
        <!-- 发票号码：选填，用于财务核对纸质/电子发票 -->
        <el-form-item label="发票号码">
          <el-input v-model="expenseForm.invoice_no" placeholder="选填" maxlength="128" show-word-limit />
        </el-form-item>
        <!-- 凭证上传：biz_type=expense 标记业务类型，上传成功后回填附件 id -->
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
      <!-- 弹窗底部：余额为负时直接禁用提交，避免提交后再被后端拒绝 -->
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

    <!-- 区块：审批流程弹窗，展示当前节点与驳回原因 -->
    <el-dialog center v-model="flowDialogVisible" title="报销审批流程" width="600px">
      <ApprovalFlow v-if="currentFlowRow" :status="currentFlowRow.status" :comment="currentFlowRow.reject_reason" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// ==================== 导入 ====================
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

// ==================== 列表与弹窗状态 ====================
/** 当前页报销记录，字段含报销单号、项目、金额、状态、驳回原因等 */
const tableData = ref<any[]>([])
/** 报销记录总数，供分页组件计算页数 */
const total = ref(0)
/** 列表请求进行中标记 */
const loading = ref(false)
/** 当前页码 */
const page = ref(1)
/** 每页条数 */
const pageSize = ref(10)
/** 新建报销弹窗显隐 */
const dialogVisible = ref(false)
/** 审批流程弹窗显隐 */
const flowDialogVisible = ref(false)
/** 流程弹窗当前查看的报销行，驱动 ApprovalFlow 的 status/comment */
const currentFlowRow = ref<any>(null)
/** 新建报销表单实例，用于提交前 validate 与关闭时 resetFields */
const formRef = ref<FormInstance>()
/** 提交按钮 loading，防止重复提交生成多张单据 */
const submitLoading = ref(false)
/** 我可报销的项目列表（仅已立项 status=6），作为「所属项目」下拉数据源 */
const myProjects = ref<any[]>([])
/** 项目已用预算缓存，key=project_id，value=已占用金额；由 handleProjectChange 拉取后写入 */
const projectExpenseMap = reactive<Record<number, number>>({})

// ==================== 表格列定义 ====================
/**
 * 金额统一按两位小数展示；申请时间经 formatDateTime 格式化；
 * 审批进度列单独成列，便于快速跳到流程详情。
 */
const columns: TableColumn[] = [
  { prop: 'expense_no', label: '报销单号', width: 160 },
  { prop: 'project_name', label: '所属项目', minWidth: 200 },
  { prop: 'expense_amount', label: '金额(¥)', width: 120, formatter: (val: number) => `¥ ${Number(val || 0).toFixed(2)}` },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
  { prop: 'flow', label: '审批进度', slot: 'flow', width: 100 },
  { prop: 'created_at', label: '申请时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

// ==================== 新建报销表单 ====================
/**
 * attachment_ids 存的是凭证文件 id 数组，随报销单一起提交给后端做关联；
 * 表单不包含 status 字段，新建后由后端置为初始待审批状态。
 */
const expenseForm = reactive({
  project_id: undefined as number | undefined,
  expense_amount: 0,
  expense_desc: '',
  invoice_no: '',
  attachment_ids: [] as number[],
})

// ==================== 预算计算 ====================
/**
 * 依赖 expenseForm.project_id 与 myProjects，输出当前选中的项目对象。
 * 目的：为预算总额、余额等计算提供统一数据源，避免多处 find 重复。
 */
const selectedProject = computed(() =>
  expenseForm.project_id ? myProjects.value.find((p) => p.id === expenseForm.project_id) : null
)

/**
 * 依赖 selectedProject，输出项目预算总额；未选项目时为 0，保证展示与计算不出 NaN。
 */
const budgetTotal = computed(() => Number(selectedProject.value?.budget_amount || 0))

/**
 * 依赖 expenseForm.project_id 与 projectExpenseMap，输出该项目已占用金额。
 * 已占用金额在 handleProjectChange 中按报销单累计，驳回单不计入。
 */
const budgetUsed = computed(() => {
  if (!expenseForm.project_id) return 0
  return projectExpenseMap[expenseForm.project_id] || 0
})

/**
 * 可用余额 = 预算总额 - 已占用金额；可能为负，用于超额拦截与红色提示。
 */
const budgetRemain = computed(() => budgetTotal.value - budgetUsed.value)

/**
 * 依赖余额与总额，输出预算提示条样式类：
 * 超支 -> budget-over（红）；余额占比低于 20% -> budget-warn（橙）；其余 -> budget-normal（绿）。
 */
const budgetClass = computed(() => {
  if (budgetTotal.value === 0) return 'budget-normal'
  const ratio = budgetRemain.value / budgetTotal.value
  if (budgetRemain.value < 0) return 'budget-over'
  if (ratio < 0.2) return 'budget-warn'
  return 'budget-normal'
})

// ==================== 表单校验规则 ====================
/** 项目、金额、事由均必填；金额只做非空校验，超额逻辑在提交时单独提示 */
const formRules: FormRules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  expense_amount: [{ required: true, message: '请输入金额', trigger: 'blur' }],
  expense_desc: [{ required: true, message: '请填写事由', trigger: 'blur' }],
}

// ==================== 数据加载 ====================
/**
 * 拉取当前学生的报销记录（分页）。
 * 接口为 POST /api/expenses/list，学生身份由登录态决定，前端不传用户 id。
 * 副作用：更新 tableData / total 与 loading 状态。
 */
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

/**
 * 拉取可用于报销的项目（先只取已立项 status=6 的前 100 条）。
 * 给每条补上 budget_used 默认值，供预算接口失败时兜底使用。
 */
async function loadMyProjects() {
  const res = await getProjectList({ page: 1, page_size: 100, status: 6 })
  myProjects.value = res.data.items.map((p: any) => ({ ...p, budget_used: p.budget_used || 0 }))
}

// ==================== 事件处理 ====================
/**
 * 切换所属项目时的联动：
 * 1) 清空已填金额，防止把 A 项目的金额带到 B 项目；
 * 2) 拉取该项目全部报销单，累加状态 <=6（未驳回）的金额作为已占用预算并缓存；
 * 3) 接口异常时退回项目自带的 budget_used，保证页面仍能显示余额。
 * 副作用：发起一次 POST /api/expenses/list 请求，写入 projectExpenseMap。
 * @param projectId 新选中的项目 ID
 */
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

/**
 * 分页变化：同步页码与每页条数后重新加载。
 * @param p 新页码
 * @param ps 新每页条数
 */
function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

/**
 * 打开审批流程弹窗并记录当前行，ApprovalFlow 依据 status 渲染节点、依据 reject_reason 显示驳回原因。
 * @param row 报销记录行
 */
function showFlowDialog(row: any) {
  currentFlowRow.value = row
  flowDialogVisible.value = true
}

/**
 * 关闭新建弹窗时重置表单。
 * 目的：避免下次打开残留上一次的项目、金额、说明与附件 id。
 * 副作用：清空 expenseForm 各字段并调用 resetFields 清除校验态。
 */
function resetExpenseForm() {
  expenseForm.project_id = undefined
  expenseForm.expense_amount = 0
  expenseForm.expense_desc = ''
  expenseForm.invoice_no = ''
  expenseForm.attachment_ids = []
  formRef.value?.resetFields()
}

/**
 * 凭证上传成功回调：把后端返回的文件 id 去重后加入附件列表。
 * @param file FileUpload 回传的文件对象，读取 file.id
 */
function handleFileSuccess(file: any) {
  if (file?.id && !expenseForm.attachment_ids.includes(file.id)) {
    expenseForm.attachment_ids.push(file.id)
  }
}

/**
 * 凭证移除回调：从附件 id 列表中同步删除，保证提交时不再携带已删文件。
 * @param file 被移除的文件对象，id 位于 response.data.id
 */
function handleFileRemove(file: any) {
  const id = file?.response?.data?.id
  if (id !== undefined) {
    const idx = expenseForm.attachment_ids.indexOf(id)
    if (idx > -1) expenseForm.attachment_ids.splice(idx, 1)
  }
}

/**
 * 提交报销申请。
 * 流程：表单校验 -> 金额不得超过可用预算余额（前端拦截，后端仍会二次校验）->
 *   POST /api/expenses 创建单据 -> 成功提示 -> 关闭弹窗 -> 刷新列表。
 * 副作用：发起创建请求、ElMessage 提示、刷新列表；失败时保留弹窗便于修改。
 */
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

// ==================== 状态映射 ====================
/**
 * 报销状态码转中文：
 * 0草稿 / 1待导师 / 2导师通过 / 3待学院 / 4学院通过 / 5待财务 / 6完成 / 7驳回。
 */
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

/**
 * 报销状态对应的标签颜色：待办类用橙色、完成用绿色、驳回用红色、草稿用灰色。
 */
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

// ==================== 生命周期 ====================
/** 页面挂载时并行加载报销列表与可报销项目，减少首屏等待 */
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
