<!--
  项目详情页
  展示项目完整信息、审核流程进度、团队成员、预算、成果
-->
<template>
  <div class="page-container" v-loading="loading">
    <el-page-header @back="router.back()">
      <template #content>
        <span class="header-title">{{ project?.project_name || '项目详情' }}</span>
        <StatusTag v-if="project" :status="project.status" />
      </template>
    </el-page-header>

    <template v-if="project">
      <!-- 审核流程 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>审核流程</span></template>
        <el-timeline>
          <el-timeline-item
            v-for="(review, idx) in reviewHistory"
            :key="idx"
            :timestamp="review.review_time || review.created_at"
            placement="top"
            :type="review.review_result === 1 ? 'success' : 'danger'"
          >
            <h4>{{ review.review_stage_name }}</h4>
            <p>审核人：{{ review.reviewer_name || '待分配' }}</p>
            <p v-if="review.review_comment">意见：{{ review.review_comment }}</p>
            <p v-if="review.score">评分：{{ review.score }}</p>
            <el-tag size="small" :type="review.review_result === 1 ? 'success' : 'danger'">
              {{ review.review_result_name || (review.review_result === 1 ? '通过' : '驳回') }}
            </el-tag>
          </el-timeline-item>
        </el-timeline>
      </el-card>

      <!-- 基本信息 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>基本信息</span></template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="项目编号">{{ project.project_no }}</el-descriptions-item>
          <el-descriptions-item label="项目名称">{{ project.project_name }}</el-descriptions-item>
          <el-descriptions-item label="项目类别">{{ project.project_type_name }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ project.leader_name }}</el-descriptions-item>
          <el-descriptions-item label="指导教师">{{ project.teacher_name || '未绑定' }}</el-descriptions-item>
          <el-descriptions-item label="所属学院">{{ project.college_name }}</el-descriptions-item>
          <el-descriptions-item label="开始日期">{{ project.start_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="结束日期">{{ project.end_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="总预算">¥ {{ Number(project.budget_amount || 0).toFixed(2) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 项目摘要 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>项目摘要</span></template>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="摘要">{{ project.project_summary }}</el-descriptions-item>
          <el-descriptions-item label="创新点">{{ project.innovation_points }}</el-descriptions-item>
          <el-descriptions-item label="预期成果">{{ project.expected_results }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 团队成员 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>团队成员</span></template>
        <el-table :data="project.team_members" border>
          <el-table-column type="index" label="序号" width="70" align="center" />
          <el-table-column prop="student_id" label="学号" />
          <el-table-column prop="student_name" label="姓名" />
          <el-table-column prop="role" label="分工" />
        </el-table>
      </el-card>

      <!-- 预算明细 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>预算明细</span></template>
        <el-table :data="project.budgets" border show-summary :summary-method="getSummary">
          <el-table-column type="index" label="序号" width="70" align="center" />
          <el-table-column prop="subject" label="科目" />
          <el-table-column prop="amount" label="金额(元)" :formatter="(r: any) => `¥ ${r.amount.toFixed(2)}`" />
          <el-table-column prop="remark" label="备注" />
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import StatusTag from '@/components/StatusTag.vue'
import { getProjectDetail } from '@/api/project'
import { getReviewHistory } from '@/api/review'

const route = useRoute()
const router = useRouter()

const project = ref<any>(null)
const reviewHistory = ref<any[]>([])
const loading = ref(true)

async function loadData() {
  const id = Number(route.params.id)
  loading.value = true
  try {
    const [detailRes, reviewRes] = await Promise.all([
      getProjectDetail(id),
      getReviewHistory(id).catch(() => ({ data: { records: [] } })),
    ])
    project.value = detailRes.data
    reviewHistory.value = reviewRes.data?.records || []
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function getSummary({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col, index) => {
    if (index === 0) sums[index] = '合计'
    else if (col.property === 'amount') {
      const total = data.reduce((s, i) => s + (i.amount || 0), 0)
      sums[index] = `¥ ${total.toFixed(2)}`
    } else sums[index] = ''
  })
  return sums
}

onMounted(() => loadData())
</script>

<style scoped>
.header-title {
  margin-right: 12px;
  font-size: 18px;
}
.section-card {
  margin-top: 16px;
}
</style>
