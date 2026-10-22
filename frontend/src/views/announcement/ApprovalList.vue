<!--
  立项结果公示
  展示所有已立项（status=6）的项目，全校可见
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="header-card">
      <div class="header">
        <div class="title-area">
          <el-icon :size="24" color="#409EFF"><Bell /></el-icon>
          <h2>立项结果公示</h2>
        </div>
        <p class="subtitle">展示经专家评审通过、正式立项的创新创业项目</p>
      </div>
    </el-card>

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

    <el-card shadow="never" class="list-card">
      <el-table
        v-loading="loading"
        :data="list"
        stripe
        style="width: 100%"
        empty-text="暂无立项项目"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh, Bell } from '@element-plus/icons-vue'
import { getAnnouncementList, type ProjectListItem } from '@/api/project'
import { getColleges } from '@/api/auth'
import { useProjectDetailStore } from '@/store/projectDetail'

const router = useRouter()
const projectDetailStore = useProjectDetailStore()
const loading = ref(false)
const list = ref<ProjectListItem[]>([])
const total = ref(0)
const colleges = ref<any[]>([])
const years = ref<number[]>([])

const searchForm = ref({
  page: 1,
  page_size: 10,
  keyword: '',
  college_id: undefined as number | undefined,
  year: undefined as number | undefined,
})

function initYears() {
  const cur = new Date().getFullYear()
  const arr: number[] = []
  for (let y = cur; y >= cur - 5; y--) arr.push(y)
  years.value = arr
}

async function loadData() {
  loading.value = true
  try {
    const params: any = {
      page: searchForm.value.page,
      page_size: searchForm.value.page_size,
    }
    if (searchForm.value.keyword) params.keyword = searchForm.value.keyword
    if (searchForm.value.college_id) params.college_id = searchForm.value.college_id
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

function handleSearch() {
  searchForm.value.page = 1
  loadData()
}

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

function goDetail(id: number) {
  projectDetailStore.open(id)
}

function formatDate(s: string | null) {
  if (!s) return '-'
  return s.replace('T', ' ').substring(0, 16)
}

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
