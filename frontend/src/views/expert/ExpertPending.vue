<!--
  ==== 专家待评审项目 ====
  解决的问题：专家登录后只应看到被分配给自己评审的项目，并能区分「还没打分」和「已打完可回看」。
  对应角色与路由：role=3 专家，路由 /expert/pending。
  依赖 API：GET /api/reviews/expert-tasks（getExpertTasks），scope=pending 取待评，
    scope=reviewed 取已评；评分提交在项目详情弹窗内调用 POST /api/reviews/expert。
  业务规则：
    - 专家评审实行盲审：开启盲审模式后负责人姓名打码、学院名显示「学院已屏蔽」，
      专家之间互相看不到彼此评分，只能看到自己的 my_score。
    - my_review_result 为 null 表示本人尚未提交评审；后端用 99 作为「已分配未评审」占位，
      不参与票数统计，因此这里按 null 判断而不是按 99。
    - 项目状态 8=待结题，专家需进行结题验收；此时即使已给过分也仍要提供操作入口。
  关键交互流程：切换待评/已评范围 -> 检索 -> 点「评审」/「结题验收」打开详情弹窗 ->
    提交后关闭弹窗刷新列表。
-->
<template>
  <div class="page-container">
    <!-- 区块：关键词筛选，按项目名称/编号检索分配给自己的任务 -->
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 区块：待评/已评范围切换，切换后重置到第一页并重新请求 -->
    <el-radio-group v-model="scope" class="scope-switch" @change="handleScopeChange">
      <el-radio-button value="pending">待评审</el-radio-button>
      <el-radio-button value="reviewed">已评审</el-radio-button>
    </el-radio-group>

    <!-- 区块：任务列表，负责人与学院列做盲审脱敏，状态列区分待评/已评/待结题验收 -->
    <PaginationTable
      :data="sortedTableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <!-- 负责人列：盲审模式下仅保留姓氏与星号，避免专家通过身份信息判断项目来源 -->
      <template #leader_name="{ row }">
        {{ displayLeaderName(row) }}
      </template>
      <!-- 学院列：盲审模式下整体替换为「学院已屏蔽」，比部分打码更彻底 -->
      <template #college_name="{ row }">
        {{ displayCollegeName(row) }}
      </template>
      <!-- 状态列：已评范围固定显示「已评审」；待评范围内按是否已提交、是否待结题分别着色 -->
      <template #status="{ row }">
        <el-tag v-if="scope === 'reviewed'" type="info">已评审</el-tag>
        <el-tag v-else :type="row.status === 8 ? 'danger' : (row.my_review_result == null ? 'warning' : 'success')">
          {{ row.status === 8 ? '待结题验收' : (row.my_review_result == null ? '待评审' : '已评审') }}
        </el-tag>
      </template>
      <!-- 操作列：已评记录只允许回看；待评或缺结题验收结论时给出对应操作入口 -->
      <template #actions="{ row }">
        <!-- 已评审：仅提供回看入口；待评审：待打分或待结题验收均给出操作入口 -->
        <el-button
          v-if="scope === 'reviewed'"
          link
          type="primary"
          size="small"
          @click="projectDetailStore.open(row.project_id)"
        >
          查看
        </el-button>
        <el-button
          v-else-if="row.my_review_result == null || row.status === 8"
          link
          type="primary"
          size="small"
          @click="projectDetailStore.open(row.project_id)"
        >
          {{ row.status === 8 ? '结题验收' : '评审' }}
        </el-button>
      </template>
      <!-- 空状态：文案随当前范围变化，提示用户切换范围查看 -->
      <template #empty>
        <EmptyIllustration
          type="project"
          :description="scope === 'reviewed' ? '暂无已评审项目' : '暂无待评审项目'"
        />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
// ==================== 导入 ====================
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getExpertTasks } from '@/api/review'
import { formatDateTime } from '@/utils/format'
import { useAppearanceStore } from '@/store/appearance'
import { useProjectDetailStore } from '@/store/projectDetail'
import { useBlindReview } from '@/composables/useBlindReview'

// ==================== 全局状态 ====================
/** 外观设置 Store：isBlindMode 控制是否开启盲审脱敏 */
const appearanceStore = useAppearanceStore()
/** 项目详情弹窗 Store：open(project_id) 打开评审弹窗 */
const projectDetailStore = useProjectDetailStore()

// ==================== 详情弹窗关闭回调 ====================
/**
 * 触发时机：评审弹窗由打开变为关闭。
 * 目的：评分已提交，重新拉取列表以更新「我的评分」「已评审」状态；
 * 副作用：发起一次 getExpertTasks 请求。
 */
watch(() => projectDetailStore.visible, (v) => {
  if (!v) loadData()
})
// ==================== 盲审脱敏工具 ====================
/**
 * 以回调方式传入 isBlindMode，使开关实时生效：
 * maskName 保留姓氏其余打码，maskCollege 直接返回「学院已屏蔽」。
 */
const { maskName, maskCollege } = useBlindReview(() => appearanceStore.isBlindMode)
// ==================== 查询条件与范围 ====================
/** 检索表单：keyword 命中项目名称或编号 */
const searchForm = reactive({ keyword: '' })
/** 任务范围：pending=待我评审，reviewed=我已评审（只读回看） */
const scope = ref<'pending' | 'reviewed'>('pending')
// ==================== 列表状态 ====================
/** 当前页专家评审任务，含项目信息、我的评分与我的评审结果 */
const tableData = ref<any[]>([])
/** 任务总数，供分页组件计算页数 */
const total = ref(0)
/** 列表请求进行中标记 */
const loading = ref(false)
/** 当前页码 */
const page = ref(1)
/** 每页条数 */
const pageSize = ref(10)

// ==================== 表格列定义 ====================
/**
 * 负责人、学院两列走插槽以支持盲审脱敏；分配时间即任务下发时间，
 * 统一经 formatDateTime 格式化；不展示其他专家评分，保证盲审公平。
 */
const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'leader_name', label: '负责人', slot: 'leader_name', width: 100 },
  { prop: 'college_name', label: '学院', slot: 'college_name', width: 140 },
  { prop: 'my_score', label: '我的评分', width: 100 },
  { prop: 'submit_time', label: '分配时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

// ==================== 计算属性 ====================
/**
 * 依赖 tableData，输出其浅拷贝。
 * 目的：让表格拿到独立数组，避免后续需要本地排序/编辑时直接改动接口返回的原始数据；
 * 当前未做排序，保留结构以便扩展。
 */
const sortedTableData = computed(() => {
  return [...tableData.value]
})

// ==================== 脱敏展示 ====================
/**
 * 根据盲审开关决定负责人展示值。
 * @param row 任务行，读取 leader_name
 * @returns 盲审开启时为打码姓名，否则为原名
 */
function displayLeaderName(row: any) {
  return appearanceStore.isBlindMode ? maskName(row.leader_name) : row.leader_name
}
/**
 * 根据盲审开关决定学院展示值。
 * @param row 任务行，读取 college_name
 * @returns 盲审开启时为「学院已屏蔽」，否则为原学院名
 */
function displayCollegeName(row: any) {
  return appearanceStore.isBlindMode ? maskCollege(row.college_name) : row.college_name
}

// ==================== 数据加载 ====================
/**
 * 按范围与关键词拉取当前专家的评审任务。
 * scope=pending 时后端返回待评分或待结题验收的项目，scope=reviewed 时返回已提交评分的项目。
 * 副作用：更新 tableData / total 与 loading 状态。
 */
async function loadData() {
  loading.value = true
  try {
    const res = await getExpertTasks({
      page: page.value, page_size: pageSize.value, scope: scope.value, ...searchForm
    })
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

// ==================== 事件处理 ====================
/** 切换待评/已评范围：回到第一页并重新请求，避免页码溢出 */
function handleScopeChange() { page.value = 1; loadData() }
/** 关键词查询：回到第一页并重新请求 */
function handleSearch() { page.value = 1; loadData() }
/**
 * 分页变化：同步页码与每页条数后重新加载。
 * @param p 新页码
 * @param ps 新每页条数
 */
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

// ==================== 生命周期 ====================
/** 进入页面默认加载待评审任务 */
onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
.scope-switch { margin-bottom: 12px; }
</style>
