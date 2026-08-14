<!--
  归档项目库
  历史项目检索、详情查看、成果预览
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="项目名称/编号/成果" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="年份">
          <el-select v-model="searchForm.year" placeholder="全部" clearable style="width: 100px">
            <el-option v-for="y in years" :key="y" :label="y" :value="y" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <template #actions="{ row }">
        <el-button link type="primary" size="small" @click="router.push(`/projects/${row.id}`)">查看</el-button>
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList } from '@/api/project'

const router = useRouter()

const searchForm = reactive({ keyword: '', year: undefined as number | undefined })
const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const currentYear = new Date().getFullYear()
const years = computed(() => Array.from({ length: 5 }, (_, i) => currentYear - i))

const columns: TableColumn[] = [
  { prop: 'project_no', label: '项目编号', minWidth: 140 },
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'leader_name', label: '负责人', width: 100 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'college_name', label: '学院', width: 120 },
  { prop: 'budget_amount', label: '预算(¥)', width: 100, formatter: (v: number) => Number(v || 0).toFixed(2) },
  { prop: 'created_at', label: '结题时间', minWidth: 160 },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getProjectList({ page: page.value, page_size: pageSize.value, status: 9, ...searchForm })
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; loadData() }
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
</style>
