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

    <el-radio-group v-model="scope" class="scope-switch" @change="handleScopeChange">
      <el-radio-button value="pending">待评审</el-radio-button>
      <el-radio-button value="reviewed">已评审</el-radio-button>
    </el-radio-group>

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
        <el-tag v-if="scope === 'reviewed'" type="info">已评审</el-tag>
        <el-tag v-else :type="row.status === 8 ? 'danger' : (row.my_review_result == null ? 'warning' : 'success')">
          {{ row.status === 8 ? '待结题验收' : (row.my_review_result == null ? '待评审' : '已评审') }}
        </el-tag>
      </template>
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

const appearanceStore = useAppearanceStore()
const projectDetailStore = useProjectDetailStore()

// 评审在项目详情弹窗内完成，弹窗关闭后刷新列表状态
watch(() => projectDetailStore.visible, (v) => {
  if (!v) loadData()
})
const { maskName, maskCollege } = useBlindReview(() => appearanceStore.isBlindMode)
const searchForm = reactive({ keyword: '' })
const scope = ref<'pending' | 'reviewed'>('pending')
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
    const res = await getExpertTasks({
      page: page.value, page_size: pageSize.value, scope: scope.value, ...searchForm
    })
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handleScopeChange() { page.value = 1; loadData() }
function handleSearch() { page.value = 1; loadData() }
function handlePageChange(p: number, ps: number) { page.value = p; pageSize.value = ps; loadData() }

onMounted(() => loadData())
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
.scope-switch { margin-bottom: 12px; }
</style>
