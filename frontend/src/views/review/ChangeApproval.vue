<!--
  ==== 变更/延期申请审批 ====
  解决的问题：项目立项后负责人如需调整成员、预算、周期或延期，必须走受控审批，
    防止绕过审核直接改动立项信息。
  对应角色与路由：role=2 指导教师（审自己指导的项目）、role=4 超管；路由 /review/changes
    （审核工作台内以 Tab 呈现）。
  依赖 API：GET /api/changes（getChangeList）拉取申请；
    POST /api/changes/{id}/approve、POST /api/changes/{id}/reject（审批通过/驳回）。
  业务规则：
    - 项目处于「待校级复审(3)」或「待专家评审(5)」时负责人可提交变更/延期，每阶段限 1 次。
    - 通过后按提交阶段回退重审：3 -> 退回学院初审(1)；5 -> 退回校级复审(3)，
      后端并附加 +1 天缓冲期，因此前端提示中要明确「需重新走后续审核」。
    - 驳回只记录结果与理由，项目停留在原阶段，不改变审核进度。
  关键交互流程：默认筛选「待审核」-> 通过需二次确认 -> 驳回需填写理由 -> 操作后刷新列表。
-->
<template>
  <div class="page-container">
    <!-- 区块：筛选条件，按申请状态过滤，默认只看待审核 -->
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

    <!-- 区块：变更申请列表，含类型、原因、状态与提交时间 -->
    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <!-- 类型列：变更/延期等类型名称由后端下发，缺失时用占位符避免单元格空塌 -->
      <template #change_type_name="{ row }">
        <el-tag size="small">{{ row.change_type_name || '—' }}</el-tag>
      </template>
      <!-- 状态列：申请状态与项目状态是两套枚举，此处按申请状态着色 -->
      <template #status="{ row }">
        <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_name }}</el-tag>
      </template>
      <!-- 操作列：仅「待审核(0)」可审批，已处理记录只读展示，防止重复审批 -->
      <template #actions="{ row }">
        <template v-if="row.status === 0">
          <el-button link type="success" size="small" @click="handleApprove(row)">通过</el-button>
          <el-button link type="danger" size="small" @click="handleReject(row)">驳回</el-button>
        </template>
        <span v-else class="muted">—</span>
      </template>
      <!-- 空状态：当前筛选条件下没有申请时的兜底提示 -->
      <template #empty>
        <EmptyIllustration type="project" description="暂无变更申请" />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
// ==================== 导入 ====================
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getChangeList, approveChangeRequest, rejectChangeRequest } from '@/api/review'
import { formatDateTime } from '@/utils/format'

// ==================== 枚举与筛选 ====================
/**
 * 变更申请自身状态枚举（注意区别于项目状态）：
 * 0=待审核，3=已通过，4=已驳回，5=已撤回（申请人主动撤回）。
 */
const STATUS_OPTIONS = [
  { value: 0, label: '待审核' },
  { value: 3, label: '已通过' },
  { value: 4, label: '已驳回' },
  { value: 5, label: '已撤回' },
]

/** 检索表单：status 为申请状态，默认 0 只列待办；清空下拉表示查全部状态 */
const searchForm = reactive<{ status?: number }>({ status: 0 })

// ==================== 列表状态 ====================
/** 当前页变更申请记录，字段与 getChangeList 返回结构一致 */
const tableData = ref<any[]>([])
/** 满足筛选条件的申请总数，供分页组件使用 */
const total = ref(0)
/** 列表请求进行中标记 */
const loading = ref(false)
/** 当前页码 */
const page = ref(1)
/** 每页条数 */
const pageSize = ref(10)

// ==================== 表格列定义 ====================
/**
 * 变更原因给足宽度便于审批人快速判断必要性；
 * 提交时间统一经 formatDateTime 格式化，避免后端原始时间串直接暴露。
 */
const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'change_type_name', label: '类型', slot: 'change_type_name', width: 120 },
  { prop: 'change_reason', label: '变更原因', minWidth: 240 },
  { prop: 'status', label: '状态', slot: 'status', width: 100 },
  { prop: 'submit_time', label: '提交时间', width: 170, formatter: (_: any, row: any) => formatDateTime(row.submit_time) },
]

// ==================== 数据加载 ====================
/**
 * 按当前状态筛选与分页拉取变更申请。
 * 副作用：更新 tableData / total 与 loading 状态。
 */
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

// ==================== 事件处理 ====================
/** 查询：回到第一页再请求，保证筛选切换后页码有效 */
function handleSearch() {
  page.value = 1
  loadData()
}

/** 重置：恢复默认的「待审核」筛选 */
function handleReset() {
  searchForm.status = 0
  handleSearch()
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
 * 通过变更申请。
 * 业务影响：项目会按提交阶段回退（校级复审提交 -> 学院初审；专家评审提交 -> 校级复审），
 * 并附带 +1 天缓冲，负责人需要重新走后续审核，因此先做二次确认再提交。
 * 副作用：调用 approveChangeRequest、成功提示、刷新列表。
 * @param row 当前行，使用 row.id 作为申请 ID
 */
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

/**
 * 驳回变更申请：必须填写理由，便于申请人了解不通过原因并修正后重提。
 * 副作用：调用 rejectChangeRequest、成功提示、刷新列表；取消弹窗则直接返回不发请求。
 * @param row 当前行，使用 row.id 作为申请 ID
 */
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

/**
 * 申请状态到标签颜色的映射：通过=绿、驳回=红、撤回=灰、其余（待审核）=橙。
 */
function statusTagType(status: number): string {
  if (status === 3) return 'success'
  if (status === 4) return 'danger'
  if (status === 5) return 'info'
  return 'warning'
}

// ==================== 生命周期 ====================
/** 进入页面默认加载「待审核」申请 */
onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
.muted { color: #c0c4cc; }
</style>
