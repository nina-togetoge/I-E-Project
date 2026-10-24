<!--
  页面名称：项目全量管理（管理员端）
  面向角色：系统管理员（全校项目）、学院管理员（仅本院项目）
  功能：
    1. 按关键词、状态、学院、类别、级别多条件筛选项目
    2. 分页查看项目列表并跳转详情
    3. 为「待分配评审专家 / 待专家评审」项目分配评审专家
    4. 按当前筛选导出项目名单 Excel
  调用 API：
    - GET  /api/projects：项目分页列表（分页与筛选均走 Query）
    - GET  /api/projects/{id}：详情由 projectDetailStore 打开时统一加载
    - GET  /api/colleges：学院筛选下拉
    - GET  /api/users?role=3：评审专家候选列表
    - GET  /api/reviews/flow/{projectId}：已分配专家（用于回填多选框）
    - POST /api/reviews/assign-experts：提交专家名单
    - GET  /api/excel/export/projects：导出项目名单
  权限 / 数据范围：
    - 列表与导出由后端 DataScope 过滤；学院管理员的学院下拉禁用并锁定本院
    - 「分配专家」按钮仅管理员可见，且学院管理员只能操作本院项目
    - 专家分配弹窗中，一旦有专家提交评审，名单只读（避免评分与名单不一致）
  关键交互：
    - 从统计看板点击图表下钻时，route.query 携带 status/type，初始化时写入筛选条件
    - 查询重置到第 1 页；分页由 PaginationTable 回传页码与每页条数
    - 分配专家成功后关闭弹窗并刷新列表，使已分配数量立即更新
-->
<template>
  <div class="page-container">
    <!--
      筛选区
      状态取值覆盖项目主流程：1 待学院初审、3 待校级复审、13 待分配专家、5 待专家评审、
      6 已立项、7 中期检查、8 待结题、9 已结题、11 已撤销。
      学院下拉对学院管理员禁用且不可清空，避免前端误传他院条件；
      「导出」把当前筛选条件一起带给导出接口，保证导出与列表口径一致。
    -->
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 150px">
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

    <!--
      项目列表
      状态列交给 StatusTag 统一映射颜色；操作列始终有「详情」，详情弹窗由全局
      projectDetailStore.open(id) 管理，避免本页重复实现详情逻辑。
      「分配专家」显示条件同时满足：
        1) 当前用户为管理员；
        2) 项目处于待分配专家（13）或待专家评审（5），其他阶段不需要名单维护；
        3) 超级管理员不限学院，学院管理员仅限本院项目，防止越权分配。
      按钮颜色反映已分配状态：有专家用 success，未分配用 warning，文案带已分配人数。
    -->
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

    <!--
      专家分配弹窗
      评审已开始（reviewed_expert_count > 0）时：
        - 顶部提示名单已锁定并解释原因；
        - 多选框与「确定」按钮均禁用，仅保留取消；
      这样避免在已有评分的情况下换人导致评分与名单不一致。
      专家下拉支持过滤，候选来自 role=3 的用户；tag 中附带学院便于重名区分。
    -->
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

// ==================== 筛选与列表状态 ====================
// 查询条件；undefined 表示该维度不筛选，提交时会被请求层忽略或由后端按空值处理
const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined,
  college_id: undefined as number | undefined,
  project_type: undefined as number | undefined,
  project_level: undefined as number | undefined,
})

// 当前页项目列表（后端已按 DataScope 过滤）
const tableData = ref<any[]>([])
// 服务端总数，驱动分页器
const total = ref(0)
// 列表加载状态
const loading = ref(false)
// 当前页码
const page = ref(1)
// 每页条数，与 PaginationTable 联动
const pageSize = ref(10)
// 学院筛选下拉
const colleges = ref<any[]>([])
// 专家候选列表；首次加载后缓存，避免每次打开弹窗都请求
const expertList = ref<any[]>([])
// 专家分配弹窗显隐
const assignDialogVisible = ref(false)
// 弹窗中已选专家 id，提交前至少 2 位
const selectedExperts = ref<number[]>([])
// 当前正在分配专家的项目行，弹窗关闭后仍保留但不再使用
const currentProject = ref<any>(null)

// ==================== 表格列定义 ====================
// 列只包含基础字段；状态、操作通过插槽扩展
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

// ==================== 数据加载 ====================
/**
 * 加载当前页项目
 * 请求：getProjectList，分页参数与 searchForm 合并后全部作为 Query 发出。
 * 副作用：覆盖 tableData/total。
 * 失败处理：不在此捕获，由全局请求拦截器统一提示；finally 复位 loading。
 */
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

// ==================== 查询与分页 ====================
/** 查询：重置到第 1 页，避免筛选后当前页超出结果范围 */
function handleSearch() {
  page.value = 1
  loadData()
}

/**
 * 分页回调
 * @param p 页码
 * @param ps 每页条数（组件切换条数时会同时回传第 1 页）
 */
function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

// ==================== 导出 ====================
/**
 * 导出项目名单
 * 将当前 searchForm 作为查询参数交给导出接口，后端同样按 DataScope 截取数据范围，
 * 因此学院管理员导出的只会是本院项目。download 内部按 blob 处理并触发保存。
 * 失败处理：未在本地捕获，接口异常由全局拦截器提示；成功后才提示「导出成功」。
 */
async function handleExport() {
  await download('/api/excel/export/projects', searchForm, '项目名单.xlsx')
  ElMessage.success('导出成功')
}

// ==================== 专家分配 ====================
/**
 * 打开专家分配弹窗
 * @param row 目标项目行，需包含 id、college_id、assigned_expert_count
 * 权限前置校验（与后端一致，前端拦截减少无效请求）：
 *   - 非管理员直接拒绝；
 *   - 学院管理员只能操作本院项目。
 * 数据加载：并行拉取专家候选与已分配名单：
 *   - 专家列表已缓存则复用，不再重复请求；
 *   - 仅在已有分配人数时才请求流程详情，省掉一次无用请求。
 * 失败处理：任一请求失败弹出「加载专家列表失败」，并且不打开弹窗，
 *   避免出现空白弹窗让用户误以为没有专家可选。
 * 副作用：填充 expertList/selectedExperts，成功后显示弹窗。
 */
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

/**
 * 提交专家分配
 * 前置条件：
 *   - 已有专家提交评审时禁止调整（与弹窗禁用形成双重保护）；
 *   - 至少选择 2 位专家，与后端 ExpertAssignRequest 的最小长度、settings.EXPERT_MIN_COUNT 保持一致。
 * 副作用：成功后提示、关闭弹窗、刷新列表以更新已分配人数。
 * 失败处理：本地未捕获，接口异常由全局拦截器提示；弹窗保持打开，用户可修正后重试。
 */
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

// ==================== 初始化 ====================
// 学院下拉失败不阻断项目列表：两件事相互独立，下拉为空时只是少一个筛选项。
// 学院管理员默认锁定本院；统计图表下钻带来的 status/type 通过路由查询写入筛选条件。
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
