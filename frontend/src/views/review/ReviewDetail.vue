<!--
  审核详情页
  展示项目信息 + 审核操作（通过/驳回 + 意见）
  专家端额外支持分项打分
-->
<template>
  <div class="page-container" v-loading="loading">
    <el-page-header @back="router.back()">
      <template #content>
        <span class="header-title">审核详情</span>
      </template>
    </el-page-header>

    <template v-if="project">
      <!-- 项目信息概览 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>项目信息</span></template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="项目编号">{{ project.project_code }}</el-descriptions-item>
          <el-descriptions-item label="项目名称">{{ project.title }}</el-descriptions-item>
          <el-descriptions-item label="类别">{{ project.category_name }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ project.leader_name }}</el-descriptions-item>
          <el-descriptions-item label="指导教师">{{ project.teacher_name }}</el-descriptions-item>
          <el-descriptions-item label="学院">{{ project.college_name }}</el-descriptions-item>
          <el-descriptions-item label="预算">¥ {{ project.total_budget?.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ project.submitted_at }}</el-descriptions-item>
          <el-descriptions-item label="状态"><StatusTag :status="project.status" /></el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 项目方案 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>项目方案</span></template>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="摘要">{{ project.abstract }}</el-descriptions-item>
          <el-descriptions-item label="背景">{{ project.background }}</el-descriptions-item>
          <el-descriptions-item label="目标">{{ project.objectives }}</el-descriptions-item>
          <el-descriptions-item label="技术路线">{{ project.methodology }}</el-descriptions-item>
          <el-descriptions-item label="预期成果">{{ project.expected_outcomes }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 审核操作区 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>审核操作</span></template>

        <!-- 专家评分（仅专家角色） -->
        <el-form v-if="userStore.isExpert" ref="scoreFormRef" :model="scoreForm" :rules="scoreRules" label-width="120px">
          <el-form-item label="创新性评分" prop="innovation_score">
            <el-rate v-model="scoreForm.innovation_score" :max="100" show-score />
          </el-form-item>
          <el-form-item label="可行性评分" prop="feasibility_score">
            <el-rate v-model="scoreForm.feasibility_score" :max="100" show-score />
          </el-form-item>
          <el-form-item label="实用性评分" prop="practical_score">
            <el-rate v-model="scoreForm.practical_score" :max="100" show-score />
          </el-form-item>
        </el-form>

        <el-form ref="reviewFormRef" :model="reviewForm" :rules="reviewRules" label-width="120px">
          <el-form-item label="审核意见" prop="opinion">
            <el-input
              v-model="reviewForm.opinion"
              type="textarea"
              :rows="4"
              placeholder="请填写审核意见（驳回时必填）"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
          <el-form-item>
            <el-button type="success" :loading="submitLoading" @click="handleReview('pass')">通过</el-button>
            <el-button type="danger" :loading="submitLoading" @click="handleReview('reject')">驳回</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import StatusTag from '@/components/StatusTag.vue'
import { useUserStore } from '@/store/user'
import { getProjectDetail } from '@/api/project'
import { getReviewHistory, submitReview, submitExpertReview } from '@/api/review'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const project = ref<any>(null)
const reviewHistory = ref<any[]>([])
const loading = ref(true)
const submitLoading = ref(false)

const reviewFormRef = ref<FormInstance>()
const scoreFormRef = ref<FormInstance>()

const reviewForm = reactive({
  opinion: '',
})

const scoreForm = reactive({
  innovation_score: 0,
  feasibility_score: 0,
  practical_score: 0,
})

const reviewRules: FormRules = {}
const scoreRules: FormRules = {
  innovation_score: [{ required: true, message: '请评分', trigger: 'change' }],
  feasibility_score: [{ required: true, message: '请评分', trigger: 'change' }],
  practical_score: [{ required: true, message: '请评分', trigger: 'change' }],
}

async function loadData() {
  const id = Number(route.params.id)
  loading.value = true
  try {
    const [detailRes, reviewRes] = await Promise.all([
      getProjectDetail(id),
      getReviewHistory(id).catch(() => ({ data: [] })),
    ])
    project.value = detailRes.data
    reviewHistory.value = reviewRes.data
  } finally {
    loading.value = false
  }
}

async function handleReview(type: 'pass' | 'reject') {
  if (type === 'reject' && !reviewForm.opinion.trim()) {
    ElMessage.warning('驳回时必须填写审核意见')
    return
  }

  submitLoading.value = true
  try {
    if (userStore.isExpert) {
      // 专家评分提交
      await submitExpertReview({
        project_id: Number(route.params.id),
        score: Math.round((scoreForm.innovation_score + scoreForm.feasibility_score + scoreForm.practical_score) / 3),
        innovation_score: scoreForm.innovation_score,
        feasibility_score: scoreForm.feasibility_score,
        practical_score: scoreForm.practical_score,
        opinion: reviewForm.opinion,
      })
    } else {
      // 普通审核
      await submitReview({
        project_id: Number(route.params.id),
        review_type: type,
        opinion: reviewForm.opinion,
      })
    }
    ElMessage.success(type === 'pass' ? '已通过' : '已驳回')
    router.back()
  } finally {
    submitLoading.value = false
  }
}

onMounted(() => loadData())
</script>

<style scoped>
.header-title { font-size: 18px; }
.section-card { margin-top: 16px; }
</style>
