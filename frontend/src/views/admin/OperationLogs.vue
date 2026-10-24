<!--
  页面名称：操作日志查询（管理员端，只读）
  面向角色：系统管理员（全校日志）、学院管理员（仅本院用户日志）
  功能：
    1. 基础筛选：关键词（操作人/模块/描述）、时间范围
    2. 高级筛选：模块、操作类型、操作人角色、执行结果（多选）
    3. 分页浏览日志，展示操作人、角色、模块、类型、描述、IP、结果、时间
    4. 按当前筛选条件导出 Excel
  调用 API：
    - GET /api/logs：分页查询；page/page_size 与所有筛选条件均作为 Query
    - GET /api/excel/export/logs：导出，条件与列表一致
  权限 / 数据范围：
    - 后端仅管理员可访问；超级管理员看全部，学院管理员仅看本院用户日志，
      该范围由后端强制注入，前端无法通过参数绕过
    - 页面无新增/修改/删除入口，日志保持只读
  关键交互：
    - 筛选变化后自动回到第 1 页并触发防抖查询；点击「查询」会立即执行挂起的防抖请求
    - 高级筛选默认收起，减少首屏表单占用；「重置条件」只清空高级条件
    - 导出把数组条件拼成逗号分隔字符串，与后端查询参数保持一致
  分页与导出说明：
    - 列表分页由 PaginationTable 回传，翻页直接请求，不做防抖
    - 导出是全量（受数据范围与筛选限制），不受当前页码影响
-->
<template>
  <div class="page-container">
    <!--
      基础筛选区
      日期范围提交时补成「开始 00:00:00 ~ 结束 23:59:59」，否则按天比较会漏掉结束当天的日志。
      查询与导出都使用 buildFilterParams，保证两者条件完全一致。
      「高级筛选」按钮只切换下方表单显隐，不触发请求。
    -->
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="操作人/模块/描述" clearable />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker
            v-model="searchForm.dateRange"
            type="daterange"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DD"
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Download" @click="handleExport">导出</el-button>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" link @click="showAdvanced = !showAdvanced">
            {{ showAdvanced ? '收起筛选 ▲' : '高级筛选 ▼' }}
          </el-button>
        </el-form-item>
      </el-form>

      <!--
        高级筛选区（默认收起）
        四个维度均为多选，提交时用逗号拼接；下拉选项内的 tag 直接复用操作类型的颜色语义。
        「重置条件」仅把高级条件清空，关键词与时间保留，便于在同一时间窗内换维度排查。
        模块与操作类型列表全部来自前端的静态枚举，后端新增类型需要同步维护这里的选项。
      -->
      <el-form v-show="showAdvanced" :inline="true" :model="searchForm" style="margin-top: 12px; border-top: 1px solid #ebeef5; padding-top: 12px;">
        <el-form-item label="模块">
          <el-select v-model="searchForm.modules" multiple placeholder="全部模块" clearable style="width: 220px">
            <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="操作类型">
          <el-select v-model="searchForm.operation_types" multiple placeholder="全部类型" clearable style="width: 260px">
            <el-option v-for="t in operationTypeOptions" :key="t.value" :value="t.value">
              <el-tag :type="t.tagType" size="small" effect="light">{{ t.value }}</el-tag>
              <span style="margin-left: 6px;">{{ t.label }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="操作人角色">
          <el-select v-model="searchForm.user_roles" multiple placeholder="全部角色" clearable style="width: 200px">
            <el-option label="学生" :value="1" />
            <el-option label="教师" :value="2" />
            <el-option label="专家" :value="3" />
            <el-option label="管理员" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item label="结果">
          <el-select v-model="searchForm.statuses" multiple placeholder="全部结果" clearable style="width: 180px">
            <el-option :value="'success'">
              <el-tag type="success" size="small" effect="light">成功</el-tag>
            </el-option>
            <el-option :value="'fail'">
              <el-tag type="danger" size="small" effect="light">失败</el-tag>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="handleResetAdvanced">重置条件</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!--
      日志表格
      操作类型、角色、结果三列使用插槽：类型与角色映射为中文并配 tag 颜色；
      结果没有独立字段，用 response_code 的 2xx 区间判定成功/失败。
      空数据展示统一空状态，同时保留筛选条件便于用户调整。
    -->
    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <template #operation_type="{ row }">
        <el-tag :type="opTypeTag(row.operation_type)">{{ opTypeLabel(row.operation_type) }}</el-tag>
      </template>
      <template #user_role="{ row }">
        <el-tag :type="roleTagType(row.user_role)">{{ roleLabel(row.user_role) }}</el-tag>
      </template>
      <template #status="{ row }">
        <el-tag :type="isSuccess(row.response_code) ? 'success' : 'danger'" size="small">
          {{ isSuccess(row.response_code) ? '成功' : '失败' }}
        </el-tag>
      </template>
      <template #empty>
        <EmptyIllustration type="default" description="暂无操作日志" />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Download } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getOperationLogs } from '@/api/common'
import { download } from '@/utils/request'
import { formatDateTime } from '@/utils/format'
import { useDebounce } from '@/composables/useDebounce'

// ==================== 高级筛选选项 ====================
// 高级筛选区折叠状态，默认收起
const showAdvanced = ref(false)

// 模块选项与后端 module_name 的取值对应；新增模块时需同步补充
const moduleOptions = [
  '项目管理', '成果管理', '审核管理', '报销管理', '用户管理', '学院管理',
  '大赛管理', '公告管理', '数据看板', '文件管理', '认证模块', '系统管理',
  '数据导出', '站内通知', 'AI助手',
]
// 操作类型选项：value 为后端大写枚举，label 用于展示，tagType 控制下拉中的标签颜色
const operationTypeOptions: { value: string; label: string; tagType: string }[] = [
  { value: 'CREATE', label: '新增', tagType: 'success' },
  { value: 'UPDATE', label: '更新', tagType: 'warning' },
  { value: 'DELETE', label: '删除', tagType: 'danger' },
  { value: 'LOGIN', label: '登录', tagType: 'info' },
  { value: 'EXPORT', label: '导出', tagType: 'primary' },
  { value: 'IMPORT', label: '导入', tagType: '' },
]

// ==================== 筛选与列表状态 ====================
// 所有筛选条件；多选维度以数组保存，构建参数时再拼接
const searchForm = reactive({
  keyword: '',
  dateRange: [] as string[],
  modules: [] as string[],
  operation_types: [] as string[],
  user_roles: [] as number[],
  statuses: [] as string[],
})

// 当前页日志
const tableData = ref<any[]>([])
// 服务端总数
const total = ref(0)
// 加载状态
const loading = ref(false)
// 当前页码
const page = ref(1)
// 每页条数
const pageSize = ref(10)

// ==================== 表格列 ====================
// 操作人、角色、模块、类型、描述、IP、结果、时间；角色/类型/结果使用插槽渲染
const columns: TableColumn[] = [
  { prop: 'real_name', label: '操作人', width: 100 },
  { prop: 'user_role', label: '角色', slot: 'user_role', width: 100 },
  { prop: 'module_name', label: '模块', width: 120 },
  { prop: 'operation_type', label: '操作类型', slot: 'operation_type', width: 100 },
  { prop: 'operation_desc', label: '描述', minWidth: 200 },
  { prop: 'ip_address', label: 'IP', width: 130 },
  { prop: 'response_code', label: '结果', slot: 'status', width: 80 },
  { prop: 'operation_time', label: '操作时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

// ==================== 查询参数构造 ====================
/**
 * 把页面筛选状态转成后端查询参数
 * @returns 仅包含非空条件的普通对象
 * 数组条件用英文逗号拼接，与后端 OperationLogQueryParams 的字符串入参一致；
 * 时间范围补足到当天首尾，避免只按日期比较时漏掉结束日当天的记录。
 */
function buildFilterParams(): any {
  const params: any = {}
  if (searchForm.keyword) params.keyword = searchForm.keyword
  if (searchForm.dateRange && searchForm.dateRange.length === 2) {
    params.start_time = `${searchForm.dateRange[0]} 00:00:00`
    // 结束日期补足到当天 23:59:59，否则会漏掉当天的日志
    params.end_time = `${searchForm.dateRange[1]} 23:59:59`
  }
  if (searchForm.modules.length > 0) params.modules = searchForm.modules.join(',')
  if (searchForm.operation_types.length > 0) params.operation_types = searchForm.operation_types.join(',')
  if (searchForm.user_roles.length > 0) params.user_roles = searchForm.user_roles.join(',')
  if (searchForm.statuses.length > 0) params.statuses = searchForm.statuses.join(',')
  return params
}

// ==================== 数据加载 ====================
/**
 * 加载当前页日志
 * 参数 = 分页 + buildFilterParams()，全部走 Query；
 * 学院管理员的可见范围由后端按当前用户学院强制过滤。
 * 失败处理：不在此捕获，由全局拦截器提示；finally 复位 loading。
 */
async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value, ...buildFilterParams() }
    const res = await getOperationLogs(params)
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

// ==================== 筛选联动（防抖） ====================
// 连续修改筛选时合并请求，400ms 内的多次变化只发最后一次，减轻日志表压力
const debouncedLoadData = useDebounce(loadData, 400)

// 监听筛选维度：关键词、日期两端、四个多选数组的长度。
// 变化后先回到第 1 页再防抖请求，防止旧页码下没有结果。
// 注意：这里监听数组长度而非内容，同一长度内替换选项（如直接换一个模块）不会自动触发，
// 需要点击「查询」或先清空再选。
watch(
  () => [
    searchForm.keyword,
    searchForm.dateRange?.[0],
    searchForm.dateRange?.[1],
    searchForm.modules.length,
    searchForm.operation_types.length,
    searchForm.user_roles.length,
    searchForm.statuses.length,
  ],
  () => {
    page.value = 1
    debouncedLoadData()
  }
)

/**
 * 点击查询
 * 重置页码后调用 debounce.flush()：若存在等待中的防抖请求立即执行；
 * 若没有挂起请求则保持当前结果（不会额外发一次重复请求）。
 */
function handleSearch() { page.value = 1; debouncedLoadData.flush() }

/**
 * 分页回调
 * @param p 页码
 * @param ps 每页条数
 * 翻页直接请求，不经过防抖：分页是明确的一次操作，延迟会带来卡顿感。
 */
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

/**
 * 重置高级筛选
 * 只清空模块/类型/角色/结果四个多选条件；关键词与时间保留。
 * 清空会触发 watch，从而自动回到第 1 页并重新查询。
 */
function handleResetAdvanced() {
  searchForm.modules = []
  searchForm.operation_types = []
  searchForm.user_roles = []
  searchForm.statuses = []
}

/**
 * 导出操作日志
 * 复用 buildFilterParams，保证导出与当前列表筛选一致；不含页码，导出为全量结果。
 * 后端会再次按角色注入数据范围（超管全部、学院管理员本院），前端无需也无法指定。
 * 失败处理：接口异常由全局拦截器提示；成功后才提示「导出成功」。
 */
async function handleExport() {
  await download('/api/excel/export/logs', buildFilterParams(), '操作日志.xlsx')
  ElMessage.success('导出成功')
}

// ==================== 展示映射 ====================
/**
 * 判断日志是否成功
 * 后端没有 status 布尔字段，以 response_code 判定：200~299 视为成功，其余（含空值）失败。
 */
function isSuccess(code: number | null | undefined): boolean {
  return typeof code === 'number' && code >= 200 && code < 300
}

// 后端 operation_type 为大写枚举，页面统一展示中文
const OP_TYPE_LABEL: Record<string, string> = {
  QUERY: '查询', CREATE: '新增', UPDATE: '更新', DELETE: '删除',
  LOGIN: '登录', EXPORT: '导出', IMPORT: '导入',
}
/**
 * 操作类型 → 中文
 * 先转大写再查表，兼容后端大小写差异；未知类型原样展示，空值显示「-」。
 */
function opTypeLabel(type: string): string {
  return OP_TYPE_LABEL[String(type || '').toUpperCase()] || type || '-'
}

/** 操作类型 → el-tag 颜色；未知类型回退 info，避免标签无样式 */
function opTypeTag(type: string): string {
  const map: Record<string, string> = {
    QUERY: 'info', CREATE: 'success', UPDATE: 'warning', DELETE: 'danger',
    LOGIN: 'info', EXPORT: 'primary', IMPORT: '',
  }
  return map[String(type || '').toUpperCase()] || 'info'
}

/** 操作人角色 → 中文；未知角色显示「-」 */
function roleLabel(role: number) {
  const map: Record<number, string> = { 1: '学生', 2: '教师', 3: '专家', 4: '管理员' }
  return map[role] || '-'
}

/** 操作人角色 → el-tag 颜色：学生默认、教师成功、专家警告、管理员危险 */
function roleTagType(role: number): string {
  const map: Record<number, string> = { 1: '', 2: 'success', 3: 'warning', 4: 'danger' }
  return map[role] || 'info'
}

// ==================== 初始化 ====================
// 首屏加载第 1 页；后续筛选变化由 watch 自动刷新
onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
