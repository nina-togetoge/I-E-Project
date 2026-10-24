<!--
  页面名称：经费管理（报销台账 + 分级审批）
  面向角色：系统管理员、学院管理员、指导教师
    - 超级管理员可审批全部报销单的待导师 / 学院 / 财务各阶段
    - 学院管理员仅可审批本院项目报销的导师通过后、学院审批阶段
    - 指导教师仅可审批自己指导项目的「待导师审批」单据
  功能：
    1. 报销单分页列表与汇总指标（单数、总额、已报销、待处理）
    2. 按项目关键词、报销状态筛选
    3. 查看报销详情与票据附件
    4. 按当前审批阶段执行「通过 / 驳回」
  调用 API：
    - POST /api/expenses/list：分页列表；page/page_size 走 URL Query，
      过滤条件 keyword/status 走 POST Body，响应同时返回 summary 汇总
    - PATCH /api/expenses/{id}/review：审批，Body 为 { approved, opinion }
  权限 / 数据范围：
    - 可见范围由后端 DataScope 决定：学生仅本人；教师 / 学院管理员限本院；超管全校
    - 行级 can_approve 由后端结合「当前用户角色 + 单据状态 + 项目导师 / 学院」计算，
      前端只认这个标记，避免对无权单据展示按钮后点出 403
  关键交互：
    - 查询、切换分页都会重新请求列表；查询时回到第 1 页
    - 审批成功后重新加载当前页，汇总指标随之刷新
    - 驳回必须填写原因（取消则不请求），通过默认意见为「同意」
-->
<template>
  <div class="page-container">
    <!--
      统计卡片区
      数据来自列表接口同一响应的 summary，与表格共用一次请求，避免额外轮询。
      「待处理」包含草稿与各级已通过但未办结的单据，因此与「待处理」筛选下拉不是同一口径。
      所有数值用 Number(... || 0) 兜底，接口未返回时显示 0 而不是 NaN。
    -->
    <el-row :gutter="20" class="stat-row">
      <el-col :span="6">
        <el-card shadow="hover"><div class="stat-card">
          <p class="stat-value">{{ Number(summary.total_count || 0) }}</p>
          <p class="stat-label">报销单数</p>
        </div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover"><div class="stat-card">
          <p class="stat-value">¥ {{ Number(summary.total_amount || 0).toFixed(2) }}</p>
          <p class="stat-label">报销总额</p>
        </div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover"><div class="stat-card">
          <p class="stat-value">¥ {{ Number(summary.approved_amount || 0).toFixed(2) }}</p>
          <p class="stat-label">已报销</p>
        </div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover"><div class="stat-card">
          <p class="stat-value">{{ Number(summary.pending_count || 0) }}</p>
          <p class="stat-label">待处理</p>
        </div></el-card>
      </el-col>
    </el-row>

    <!--
      筛选区
      keyword 由后端同时匹配项目名称、项目编号与报销单号；status 对应 8 态模型中的 1~7，
      草稿（0）不在筛选项里——管理员关注的是已提交、进入审批流程的单据。
      点击查询会先重置页码再请求，防止停留在越界页码导致空列表。
    -->
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="项目">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部" clearable style="width: 140px">
            <el-option label="待导师审批" :value="1" />
            <el-option label="导师审批通过" :value="2" />
            <el-option label="待学院审批" :value="3" />
            <el-option label="学院审批通过" :value="4" />
            <el-option label="待财务审批" :value="5" />
            <el-option label="已完成" :value="6" />
            <el-option label="已驳回" :value="7" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!--
      报销列表
      列定义在 script 的 columns 中，状态与操作列通过插槽渲染。
      「通过 / 驳回」只在 row.can_approve 为真时出现：该字段由后端按审批阶段计算，
      不同阶段对应不同审批人（导师本人 / 本院学院管理员 / 超管财务终审）。
      :loading 绑定 actionLoadingId 使被点击行进入加载态，同时也能阻止同一行的重复提交。
      空数据使用统一空状态插画，避免只有表头没有反馈。
    -->
    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <template #status="{ row }">
        <el-tag :type="expenseStatusTagType(row.status)">{{ row.status_text || '未知' }}</el-tag>
      </template>
      <template #actions="{ row }">
        <el-button link type="primary" size="small" @click="handleView(row)">查看</el-button>
        <el-button
          v-if="row.can_approve"
          link type="success" size="small"
          :loading="actionLoadingId === row.id"
          @click="handleApprove(row, true)"
        >通过</el-button>
        <el-button
          v-if="row.can_approve"
          link type="danger" size="small"
          :loading="actionLoadingId === row.id"
          @click="handleApprove(row, false)"
        >驳回</el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="file" description="暂无报销数据" />
      </template>
    </PaginationTable>

    <!--
      报销详情弹窗
      只读展示，不提供编辑入口；currentExpense 为空时用 v-if 不渲染内容，
      防止弹窗打开瞬间读取 undefined 字段报错。
      驳回原因仅在存在 reject_reason 时显示（被驳回的单据才需要解释）。
      票据附件交给 ProjectAttachmentList 统一处理预览与下载，避免各页重复实现。
    -->
    <el-dialog center v-model="showDetail" title="报销单详情" width="640px">
      <template v-if="currentExpense">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="报销单号">{{ currentExpense.expense_no }}</el-descriptions-item>
          <el-descriptions-item label="所属项目">{{ currentExpense.project_name }}</el-descriptions-item>
          <el-descriptions-item label="申请人">{{ currentExpense.applicant_name }}</el-descriptions-item>
          <el-descriptions-item label="金额">¥ {{ Number(currentExpense.expense_amount || 0).toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="expenseStatusTagType(currentExpense.status)">{{ currentExpense.status_text }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="申请时间">{{ currentExpense.created_at }}</el-descriptions-item>
          <el-descriptions-item label="费用说明" :span="2">{{ currentExpense.expense_desc }}</el-descriptions-item>
          <el-descriptions-item label="发票号" :span="2">{{ currentExpense.invoice_no || '-' }}</el-descriptions-item>
          <el-descriptions-item v-if="currentExpense.reject_reason" label="驳回原因" :span="2">
            <span style="color: var(--el-color-danger)">{{ currentExpense.reject_reason }}</span>
          </el-descriptions-item>
        </el-descriptions>
        <div style="margin-top: 16px;">
          <div style="font-weight: 600; margin-bottom: 8px;">票据附件</div>
          <ProjectAttachmentList :attachments="currentExpense.attachments" />
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { formatDateTime } from '@/utils/format'
import service, { post, patch } from '@/utils/request'

// ==================== 列表状态与筛选 ====================
// 查询条件：keyword 命中项目名称/编号或报销单号；status 选择具体审批状态
const searchForm = reactive({ keyword: '', status: undefined as number | undefined })
// 当前页报销数据（后端已按数据范围过滤）
const tableData = ref<any[]>([])
// 服务端总条数，驱动 PaginationTable 的分页器
const total = ref(0)
// 列表请求状态，避免翻页时出现旧数据闪烁
const loading = ref(false)
// 当前页码，从 1 开始；查询时回到 1，翻页时由组件回传
const page = ref(1)
// 每页条数，与组件 page-size 双向联动
const pageSize = ref(10)
// 汇总指标，与列表同一次响应返回，减少一次统计请求
const summary = ref<any>({})
// 详情弹窗显隐
const showDetail = ref(false)
// 当前查看的报销单，仅在弹窗打开期间有值
const currentExpense = ref<any>(null)
// 正在审批的行 id：用于单行按钮 loading，并阻止同一行重复提交
const actionLoadingId = ref<number | null>(null)

/**
 * 打开报销详情弹窗
 * @param row 列表行数据（含 expense_no、金额、状态、附件等）
 * 副作用：写入 currentExpense 并显示弹窗；仅前端展示，不发起请求。
 */
function handleView(row: any) {
  currentExpense.value = row
  showDetail.value = true
}

// ==================== 表格列定义 ====================
// 操作列不在此声明，由模板 #actions 插槽提供，以便受 can_approve 控制
const columns: TableColumn[] = [
  { prop: 'expense_no', label: '报销单号', width: 160 },
  { prop: 'project_name', label: '项目', minWidth: 200 },
  { prop: 'expense_amount', label: '金额(¥)', width: 120, formatter: (v: number) => `¥ ${Number(v || 0).toFixed(2)}` },
  { prop: 'applicant_name', label: '申请人', width: 100 },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
  { prop: 'created_at', label: '申请时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

// ==================== 数据加载 ====================
/**
 * 加载当前页报销列表及汇总
 * 参数：读取 searchForm、page、pageSize。
 * 数据传递：分页参数放 Query（后端 PaginationParams 从 Query 读取），
 *   过滤条件放 POST Body（后端 ExpenseQueryRequest 从 Body 读取），两者不能混放。
 * 副作用：覆盖 tableData / total / summary。
 * 失败处理：不在此捕获，交给全局请求拦截器提示；finally 保证 loading 复位，
 *   否则接口报错后表格会一直处于加载遮罩。
 */
async function loadData() {
  loading.value = true
  try {
    // page/page_size 通过 URL Query 传（后端 PaginationParams = Depends() 读 Query）
    // 过滤条件 status/keyword 通过 POST Body 传
    const res: any = await service({
      method: 'post',
      url: '/api/expenses/list',
      params: { page: page.value, page_size: pageSize.value },
      data: searchForm,
    })
    tableData.value = res.data.items || []
    total.value = res.data.total || 0
    summary.value = res.data.summary || {}
  } finally {
    loading.value = false
  }
}

// ==================== 查询与分页 ====================
/** 点击查询：强制回到第 1 页再请求，避免筛选后页码超出结果总数 */
function handleSearch() { page.value = 1; loadData() }
/**
 * 分页变化回调（由 PaginationTable 触发）
 * @param p 目标页码
 * @param ps 每页条数（组件在切换 page-size 时会同时回到第 1 页）
 */
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

// ==================== 审批操作 ====================
/**
 * 通过 / 驳回报销单
 * @param row 当前报销行，必须带 id 与 can_approve（后端已校验当前阶段审批人）
 * @param approve true 通过；false 驳回
 * 交互逻辑：
 *   - 通过无需填写意见，默认「同意」；
 *   - 驳回必须填原因，用户取消输入框时不发请求，避免产生没有理由的驳回记录。
 * 副作用：请求期间锁定该行按钮 loading；成功后提示并刷新列表与汇总。
 * 失败处理：捕获后弹出后端 message（如「仅项目所属学院管理员可审批」），
 *   finally 解除 loading，避免按钮永久转圈。
 */
async function handleApprove(row: any, approve: boolean) {
  let opinion = '同意'
  if (!approve) {
    try {
      const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回', { type: 'warning' })
      opinion = value || ''
    } catch {
      return // 用户取消
    }
  }
  actionLoadingId.value = row.id
  try {
    await patch(`/api/expenses/${row.id}/review`, { approved: approve, opinion })
    ElMessage.success(approve ? '已通过' : '已驳回')
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '审批失败')
  } finally {
    actionLoadingId.value = null
  }
}

// ==================== 状态展示 ====================
/**
 * 报销状态 → el-tag type 映射（8 态模型）
 * 1/3/5 为各级「待审批」用警告色；2/4 为中间通过态不强调；
 * 6 已完成用成功色；7 已驳回用危险色；未知状态回退 info，避免标签无样式。
 * @param status 后端返回的 status 数值
 */
function expenseStatusTagType(status: number): string {
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
// 首屏加载第 1 页数据；onMounted 不再额外请求汇总，summary 随列表返回
onMounted(() => loadData())
</script>

<style scoped>
.stat-row { margin-bottom: 20px; }
.stat-card { text-align: center; }
.stat-value { font-size: 22px; font-weight: 600; color: #303133; }
.stat-label { font-size: 13px; color: #909399; margin-top: 4px; }
.search-card { margin-bottom: 16px; }
</style>
