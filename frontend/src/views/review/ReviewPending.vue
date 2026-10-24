<!--
  ==== 待审核列表 ====
  解决的问题：让教师 / 管理员在各自权限范围内看到「轮到自己审」的项目，避免全校项目混排。
  对应角色与路由：role=2 教师、role=4 管理员；路由 /review/pending（审核工作台内以 Tab 呈现，
    也可直接访问该隐藏路由）。
  依赖 API：GET /api/reviews（getReviewList），后端按登录角色与学院范围过滤出待办；
    具体审核动作由项目详情弹窗调用 /api/reviews、/api/reviews/expert 完成。
  关键交互流程：进入页面按角色拉取待办 -> 关键词检索 -> 点「审核」打开项目详情弹窗，
    审核完成后关闭弹窗触发列表刷新，使已处理项目从待办中消失。
-->
<template>
  <div class="page-container">
    <!-- 区块：筛选条件，仅支持按项目名称/编号模糊检索 -->
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号" clearable style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 区块：待审核项目表格，列与分页由 PaginationTable 统一渲染 -->
    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <!-- 状态列：展示后端返回的状态名称，并按审核阶段着色（12 教师确认 / 1 学院初审 / 3 校级复审） -->
      <template #status="{ row }">
        <el-tag :type="statusTagType(row.status)">{{ row.status_name }}</el-tag>
      </template>
      <!-- 操作列：不在此页直接审，统一打开项目详情弹窗查看材料并提交审核结论 -->
      <template #actions="{ row }">
        <el-button
          link
          type="primary"
          size="small"
          @click="projectDetailStore.open(row.id)"
        >
          审核
        </el-button>
      </template>
      <!-- 空状态：无待办时给出插画提示，避免空白表格造成误解 -->
      <template #empty>
        <EmptyIllustration type="project" description="暂无待审核项目" />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
// ==================== 导入 ====================
import { ref, reactive, onMounted, watch } from 'vue'
import { Search, Refresh } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getReviewList } from '@/api/review'
import { useProjectDetailStore } from '@/store/projectDetail'

// ==================== 全局状态 ====================
/** 项目详情弹窗 Store：open(id) 打开弹窗，visible 变化用于感知审核是否结束 */
const projectDetailStore = useProjectDetailStore()

// ==================== 详情弹窗关闭回调 ====================
/**
 * 触发时机：项目详情弹窗由打开变为关闭。
 * 目的：审核结果已写入后端，此时重新拉取列表，让刚处理完的项目从待办中移除；
 * 副作用：发起一次 getReviewList 请求。
 */
watch(() => projectDetailStore.visible, (v) => {
  if (!v) loadData()
})

// ==================== 查询条件 ====================
/** 检索表单：keyword 命中项目名称或项目编号，交由后端模糊匹配 */
const searchForm = reactive({
  keyword: '',
})

// ==================== 列表状态 ====================
/** 当前页待审核项目，元素字段与 ReviewRecord/项目列表接口返回一致 */
const tableData = ref<any[]>([])
/** 待审核项目总数，由接口 total 字段回填，供分页组件计算页数 */
const total = ref(0)
/** 列表请求进行中标记，驱动表格 loading 遮罩 */
const loading = ref(false)
/** 当前页码，从 1 开始 */
const page = ref(1)
/** 每页条数，默认 10，可通过分页组件切换 */
const pageSize = ref(10)

// ==================== 表格列定义 ====================
/**
 * 列配置：项目名称/类别/学院/负责人/指导教师/预算用于快速识别项目归属，
 * 状态列走自定义插槽渲染为彩色标签；状态列放在最后便于扫读。
 */
const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 220 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'college_name', label: '学院', width: 160 },
  { prop: 'leader_name', label: '负责人', width: 100 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'budget_amount', label: '预算(元)', width: 120 },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
]

// ==================== 数据加载 ====================
/**
 * 拉取当前用户角色对应的待审核项目。
 * 后端依据 role 与 college_id 过滤：教师只看自己指导的项目，学院管理员只看本学院，
 * 超管看全校待校级复审项目，因此前端无需再传角色参数。
 * 副作用：更新 tableData / total，并切换 loading 状态。
 */
async function loadData() {
  loading.value = true
  try {
    const res = await getReviewList({
      page: page.value,
      page_size: pageSize.value,
      keyword: searchForm.keyword,
    } as any)
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

// ==================== 事件处理 ====================
/**
 * 点击查询：重置到第一页再请求，避免关键词变化后停留在越界页码。
 */
function handleSearch() {
  page.value = 1
  loadData()
}

/**
 * 点击重置：清空关键词并复用查询逻辑，等价于恢复默认列表。
 */
function handleReset() {
  searchForm.keyword = ''
  handleSearch()
}

/**
 * 分页变化：同步页码/每页条数后重新请求。
 * @param p 新的页码
 * @param ps 新的每页条数
 */
function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

/**
 * 项目状态到标签颜色的映射，仅覆盖本页可能出现的待审状态：
 * 12=待指导教师确认，1=待学院初审，3=待校级复审；其余状态兜底为灰色。
 */
function statusTagType(status: number): string {
  const map: Record<number, string> = {
    12: 'warning', // 待指导教师确认
    1: 'primary',  // 待学院初审
    3: 'success',  // 待校级复审
  }
  return map[status] || 'info'
}

// ==================== 生命周期 ====================
/** 页面挂载即加载第一页待办，保证进入即可看到待处理项目 */
onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
