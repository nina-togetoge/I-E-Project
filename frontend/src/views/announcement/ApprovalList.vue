<!--
  ==== 立项结果公示 ====

  页面职责：展示经专家评审通过、正式立项的项目（后端按状态筛选），
            全校师生可按关键词、学院、年份检索并查看项目详情。
  角色与路由：roles [1,2,3,4] 均可访问，路由 /announcement/approval
            （name: ApprovalAnnouncement，菜单标题「立项结果公示」）。
  调用接口：GET /api/projects/announcement/list   公示列表（分页，返回 items + total）
            GET /api/colleges                       学院下拉数据源
  关键交互：年份下拉转换为 start_year 与 end_year 同年查询；点击项目名通过全局
            projectDetailStore.open(id) 打开项目详情抽屉；学院字典加载失败不阻塞列表。
-->
<template>
  <div class="page-container">
    <!-- 区块：页面标题与公示说明 -->
    <el-card shadow="never" class="header-card">
      <div class="header">
        <div class="title-area">
          <el-icon :size="24" color="#409EFF"><Bell /></el-icon>
          <h2>立项结果公示</h2>
        </div>
        <p class="subtitle">展示经专家评审通过、正式立项的创新创业项目</p>
      </div>
    </el-card>

    <!-- 区块：筛选区（关键词 / 学院 / 年份；年份按 start_year 与 end_year 同年查询） -->
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input
            v-model="searchForm.keyword"
            placeholder="项目名称 / 编号 / 负责人"
            clearable
            style="width: 240px"
            @keyup.enter="handleSearch"
          />
        </el-form-item>
        <el-form-item label="学院">
          <el-select v-model="searchForm.college_id" placeholder="全部" clearable style="width: 160px">
            <el-option
              v-for="c in colleges"
              :key="c.id"
              :label="c.college_name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="年份">
          <el-select v-model="searchForm.year" placeholder="全部" clearable style="width: 120px">
            <el-option v-for="y in years" :key="y" :label="y" :value="y" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 区块：公示列表（仅展示已立项项目，项目名可点击打开详情） -->
    <el-card shadow="never" class="list-card">
      <el-table
        v-loading="loading"
        :data="list"
        stripe
        style="width: 100%"
        empty-text="暂无立项项目"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <!-- 项目名称即详情入口：点击后由全局 projectDetailStore.open(id) 打开详情抽屉 -->
        <el-table-column prop="project_name" label="项目名称" min-width="220">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDetail(row.id)">{{ row.project_name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="project_type_name" label="类别" width="120" />
        <el-table-column prop="project_level_name" label="级别" width="100" />
        <el-table-column prop="college_name" label="学院" width="160" />
        <el-table-column prop="leader_name" label="负责人" width="100" />
        <el-table-column prop="teacher_name" label="指导教师" width="100" />
        <el-table-column label="经费(元)" width="120" align="right">
          <template #default="{ row }">
            {{ Number(row.budget_amount || 0).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column prop="approval_time" label="立项时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.approval_time) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- 区块：分页区（page / page_size 变化后重新请求公示列表） -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="searchForm.page"
          v-model:page-size="searchForm.page_size"
          :page-sizes="[10, 20, 50]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
// ==================== 导入区 ====================
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh, Bell } from '@element-plus/icons-vue'
import { getAnnouncementList, type ProjectListItem } from '@/api/project'
import { getColleges } from '@/api/auth'
import { useProjectDetailStore } from '@/store/projectDetail'

// ==================== 依赖与路由 ====================
// router 当前未直接使用（详情统一交给 projectDetailStore），保留以便后续扩展页面跳转
const router = useRouter()
// 全局项目详情抽屉：open(id) 会触发外部详情组件按 id 加载并展示项目
const projectDetailStore = useProjectDetailStore()

// ==================== 响应式状态 ====================
// 公示列表加载态：控制表格 v-loading
const loading = ref(false)
// 当前页公示项目，对应 GET /api/projects/announcement/list 返回的 items
const list = ref<ProjectListItem[]>([])
// 公示项目总数，来自接口 total，供分页组件计算页数
const total = ref(0)
// 学院下拉数据源，对应 GET /api/colleges；加载失败时保持空数组，不影响列表主体
const colleges = ref<any[]>([])
// 年份下拉候选（当前年向前 5 年），由 initYears 初始化
const years = ref<number[]>([])

// ==================== 查询条件与分页 ====================
// 查询参数：page / page_size / keyword / college_id / year；
// year 在请求前会展开为 start_year 与 end_year 两个同值参数
const searchForm = ref({
  page: 1,
  page_size: 10,
  keyword: '',
  college_id: undefined as number | undefined,
  year: undefined as number | undefined,
})

// ==================== 年份选项 ====================
/**
 * 初始化年份下拉：从当前年份向前取 5 个年份，降序排列。
 * 纯前端生成，避免为年份字典额外请求接口。
 */
function initYears() {
  const cur = new Date().getFullYear()
  const arr: number[] = []
  for (let y = cur; y >= cur - 5; y--) arr.push(y)
  years.value = arr
}

// ==================== 数据加载与筛选 ====================
/**
 * 加载立项结果公示列表。
 * 仅把有值的筛选条件放入 query，避免空字符串被后端当作有效筛选；
 * 年份转换为 start_year 与 end_year 同值，实现按立项年度精确过滤。
 * 副作用：写入 loading、list、total。
 */
async function loadData() {
  loading.value = true
  try {
    const params: any = {
      page: searchForm.value.page,
      page_size: searchForm.value.page_size,
    }
    if (searchForm.value.keyword) params.keyword = searchForm.value.keyword
    if (searchForm.value.college_id) params.college_id = searchForm.value.college_id
    // 年份筛选是闭区间，开始与结束都取同一年即「该年度」
    if (searchForm.value.year) {
      params.start_year = searchForm.value.year
      params.end_year = searchForm.value.year
    }
    const res = await getAnnouncementList(params)
    list.value = res.data?.items || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

/** 点击查询：回到第 1 页后重新请求，避免筛选后页码越界 */
function handleSearch() {
  searchForm.value.page = 1
  loadData()
}

/** 重置全部筛选条件并回到第 1 页重新加载 */
function handleReset() {
  searchForm.value = {
    page: 1,
    page_size: 10,
    keyword: '',
    college_id: undefined,
    year: undefined,
  }
  loadData()
}

// ==================== 详情与展示辅助 ====================
/** 打开全局项目详情抽屉；数据由 store 内部按 id 拉取 @param id 项目 ID */
function goDetail(id: number) {
  projectDetailStore.open(id)
}

/** 把立项时间格式化为 yyyy-MM-dd HH:mm，兼容 ISO 的 T 分隔符；空值显示 '-' */
function formatDate(s: string | null) {
  if (!s) return '-'
  return s.replace('T', ' ').substring(0, 16)
}

// ==================== 生命周期 ====================
// 首次进入：生成年份选项，拉取学院字典（失败容忍），再加载第一页公示数据
onMounted(async () => {
  initYears()
  try {
    colleges.value = (await getColleges()).data || []
  } catch {}
  loadData()
})
</script>

<style scoped>
.page-container {
  padding: 16px;
}
.header-card {
  margin-bottom: 12px;
}
.header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.title-area {
  display: flex;
  align-items: center;
  gap: 10px;
}
.title-area h2 {
  margin: 0;
  font-size: 20px;
}
.subtitle {
  margin: 0;
  color: #909399;
  font-size: 13px;
}
.filter-card {
  margin-bottom: 12px;
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
