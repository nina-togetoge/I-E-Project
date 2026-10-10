<!--
  专家端 - 待评审项目列表
-->
<template>
  <div class="page-container">
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

    <PaginationTable
      :data="sortedTableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      @page-change="handlePageChange"
    >
      <template #leader_name="{ row }">
        {{ displayLeaderName(row) }}
      </template>
      <template #college_name="{ row }">
        {{ displayCollegeName(row) }}
      </template>
      <template #status="{ row }">
        <el-tag :type="row.my_review_result == null ? 'warning' : 'success'">
          {{ row.my_review_result == null ? '待评审' : '已评审' }}
        </el-tag>
      </template>
      <template #actions="{ row }">
        <el-button
          v-if="row.my_review_result == null"
          link
          type="primary"
          size="small"
          @click="router.push(`/review/${row.project_id}`)"
        >
          评审
        </el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="project" description="暂无待评审项目" />
      </template>
    </PaginationTable>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getExpertTasks } from '@/api/review'
import { formatDateTime } from '@/utils/format'
import { useAppearanceStore } from '@/store/appearance'
import { useBlindReview } from '@/composables/useBlindReview'

const router = useRouter()
const appearanceStore = useAppearanceStore()
const { maskName, maskCollege } = useBlindReview(() => appearanceStore.isBlindMode)
const searchForm = reactive({ keyword: '' })
const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'leader_name', label: '负责人', slot: 'leader_name', width: 100 },
  { prop: 'college_name', label: '学院', slot: 'college_name', width: 140 },
  { prop: 'my_score', label: '我的评分', width: 100 },
  { prop: 'submit_time', label: '分配时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

const sortedTableData = computed(() => {
  return [...tableData.value]
})

function displayLeaderName(row: any) {
  return appearanceStore.isBlindMode ? maskName(row.leader_name) : row.leader_name
}
function displayCollegeName(row: any) {
  return appearanceStore.isBlindMode ? maskCollege(row.college_name) : row.college_name
}

async function loadData() {
  loading.value = true
  try {
    const res = await getExpertTasks({ page: page.value, page_size: pageSize.value, ...searchForm })
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
