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
      <!-- 审核流程进度 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>审核流程</span></template>
        <ProjectTimeline :project="project" :review-history="reviewHistory" />
      </el-card>

      <!-- 项目信息概览 -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <span>项目信息</span>
          <el-tag v-if="appearanceStore.isBlindMode && userStore.isExpert" type="warning" size="small" effect="light" class="blind-tag">
            🔒 盲审模式已启用，个人信息已脱敏
          </el-tag>
        </template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="项目编号">{{ project.project_no }}</el-descriptions-item>
          <el-descriptions-item label="项目名称" :span="2">{{ project.project_name }}</el-descriptions-item>
          <el-descriptions-item label="项目类别">{{ project.project_type_name }}</el-descriptions-item>
          <el-descriptions-item label="项目级别">{{ project.project_level_name }}</el-descriptions-item>
          <el-descriptions-item label="所属学院">{{ displayCollegeName }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ displayLeaderName }}</el-descriptions-item>
          <el-descriptions-item label="指导教师">{{ displayTeacherName }}</el-descriptions-item>
          <el-descriptions-item label="总预算">¥ {{ Number(project.budget_amount || 0).toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="开始日期">{{ project.start_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="结束日期">{{ project.end_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ project.submit_time || '-' }}</el-descriptions-item>
          <el-descriptions-item label="当前状态"><StatusTag :status="project.status" /></el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 项目方案 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>项目方案</span></template>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="项目摘要">
            <div class="plan-text">{{ project.project_summary || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="创新点">
            <div class="plan-text">{{ project.innovation_points || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="预期成果">
            <div class="plan-text">{{ project.expected_results || '-' }}</div>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 团队成员 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>团队成员</span></template>
        <el-table :data="project.team_members || []" border size="small">
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="student_no" label="学号" width="120" />
          <el-table-column prop="student_name" label="姓名" width="100" />
          <el-table-column prop="major" label="专业" minWidth="140" />
          <el-table-column prop="grade" label="年级" width="100" />
          <el-table-column prop="role_in_team" label="团队角色" width="120" />
          <el-table-column prop="task_desc" label="分工任务" min-width="180" />
        </el-table>
        <el-empty v-if="!project.team_members || project.team_members.length === 0" description="暂无团队成员" :image-size="60" />
      </el-card>

      <!-- 预算明细 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>预算明细</span></template>
        <el-table :data="project.budgets || []" border size="small" show-summary :summary-method="getBudgetSummary">
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="budget_item" label="预算科目" min-width="160" />
          <el-table-column prop="budget_amount" label="预算金额(元)" width="140" align="right">
            <template #default="{ row }">¥ {{ Number(row.budget_amount || 0).toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="200" />
        </el-table>
        <el-empty v-if="!project.budgets || project.budgets.length === 0" description="暂无预算明细" :image-size="60" />
      </el-card>

      <!-- 申报附件 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>申报附件</span></template>
        <ProjectAttachmentList :attachments="project.attachments" />
      </el-card>

      <!-- 审核操作区 -->
      <el-card shadow="never" class="section-card">
        <template #header><span>审核操作</span></template>

        <!-- 专家评分（仅专家角色） -->
        <el-form v-if="userStore.isExpert" ref="scoreFormRef" :model="scoreForm" :rules="scoreRules" label-width="120px">
          <el-form-item label="加权总分">
            <span class="weighted-score">{{ weightedScore.toFixed(2) }} 分</span>
          </el-form-item>
          <template v-for="criterion in scoringCriteria" :key="criterion.key">
            <el-form-item :label="`${criterion.name}(${criterion.weight * 100}%)`">
              <div class="scoring-row">
                <el-slider
                  v-model="dimScores[criterion.key]"
                  :min="0"
                  :max="100"
                  show-input
                  :marks="sliderMarks"
                  style="flex: 1; margin-right: 20px;"
                />
                <span class="dim-desc">{{ criterion.desc }}</span>
              </div>
            </el-form-item>
          </template>
          <el-form-item label="各维度评价">
            <el-input
              v-model="scoreForm.dim_comments"
              type="textarea"
              :rows="3"
              placeholder="可填写各维度的详细评价文字（选填）"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
        </el-form>

        <el-form ref="reviewFormRef" :model="reviewForm" :rules="reviewRules" label-width="120px">
          <el-form-item label="当前阶段">
            <el-tag :type="stageTagType(currentReviewStage)">
              {{ stageLabel(currentReviewStage) }}
            </el-tag>
          </el-form-item>
          <el-alert
            v-if="!canReviewCurrentStage && !userStore.isExpert"
            type="warning"
            :closable="false"
            show-icon
            title="您当前无此阶段的审核权限"
            style="margin-bottom: 16px;"
          />
          <el-form-item label="审核意见" prop="review_comment">
            <div class="comment-header">
              <ReviewTemplatePicker @select="handleTemplateSelect" />
            </div>
            <el-input
              v-model="reviewForm.review_comment"
              type="textarea"
              :rows="4"
              placeholder="请填写审核意见（驳回时必填）"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
          <el-form-item
            v-if="canReviewCurrentStage || (currentReviewStage === 3 && userStore.isExpert)"
            label-width="0"
            class="review-actions"
          >
            <el-button type="success" :loading="submitLoading" @click="handleReview('pass')">通过</el-button>
            <el-button type="warning" :loading="submitLoading" @click="handleReview('modify')">退回修改</el-button>
            <el-button type="danger" :loading="submitLoading" @click="handleReview('reject')">驳回</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import StatusTag from '@/components/StatusTag.vue'
import ReviewTemplatePicker from '@/components/ReviewTemplatePicker.vue'
import ProjectTimeline from '@/components/ProjectTimeline.vue'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import { useUserStore } from '@/store/user'
import { useAppearanceStore } from '@/store/appearance'
import { useProcessStore } from '@/store/process'
import { getProjectDetail } from '@/api/project'
import { getReviewHistory, submitReview, submitExpertReview } from '@/api/review'
import { scoringCriteria, calculateWeightedScore, sliderMarks, type DimScores } from '@/data/scoringCriteria'
import { useBlindReview } from '@/composables/useBlindReview'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appearanceStore = useAppearanceStore()
const processStore = useProcessStore()
const { maskName, maskCollege, maskIdNumber } = useBlindReview(() => appearanceStore.isBlindMode)

const project = ref<any>(null)
const reviewHistory = ref<any[]>([])
const loading = ref(true)
const submitLoading = ref(false)

const reviewFormRef = ref<FormInstance>()
const scoreFormRef = ref<FormInstance>()

const reviewForm = reactive({
  review_comment: '',
})

const dimScores = reactive<DimScores>({
  innovation: 0,
  feasibility: 0,
  team: 0,
  market: 0,
})

const scoreForm = reactive({
  score: 0,
  dim_comments: '',
  dimScores: {} as DimScores,
})

const weightedScore = computed(() => {
  const total = calculateWeightedScore(dimScores)
  scoreForm.score = total
  scoreForm.dimScores = { ...dimScores }
  return total
})

/** 根据项目状态映射到对应的审核阶段（与后端 ReviewService._get_stage_from_status 保持一致） */
const currentReviewStage = computed((): number => {
  const status = project.value?.status ?? 0
  if (status === 12) return 0  // 待指导教师确认 -> REVIEW_STAGE_TEACHER
  if (status === 1) return 1  // 待学院初审 -> REVIEW_STAGE_COLLEGE
  if (status === 3) return 2  // 待校级复审 -> REVIEW_STAGE_UNIVERSITY
  if (status === 5) return 3  // 待专家评审 -> REVIEW_STAGE_EXPERT
  if (status === 8) return 4  // 待结题 -> REVIEW_STAGE_FINAL
  return -1  // 不在审核流程中
})

/** 是否允许当前用户在该阶段进行普通审核（排除专家评审分支） */
const canReviewCurrentStage = computed((): boolean => {
  if (!project.value) return false
  const stage = currentReviewStage.value
  if (stage < 0) return false
  // 专家评审阶段，专家走单独表单
  if (stage === 3) return userStore.isExpert
  // 指导教师确认：仅该项目的指导教师本人
  if (stage === 0) {
    return Number(userStore.userInfo?.id) === Number(project.value.teacher_id) || userStore.isSuperAdmin
  }
  // 学院初审：学院管理员 / 超级管理员
  if (stage === 1) {
    if (userStore.isSuperAdmin) return true
    if (userStore.isCollegeAdmin && Number(userStore.collegeId) === Number(project.value.college_id)) return true
    return false
  }
  // 校级复审：仅真超级管理员
  if (stage === 2) return userStore.isSuperAdmin
  // 结题验收：仅真超级管理员或专家
  if (stage === 4) return userStore.isSuperAdmin || userStore.isExpert
  return false
})

const displayLeaderName = computed(() =>
  appearanceStore.isBlindMode && userStore.isExpert ? maskName(project.value?.leader_name) : project.value?.leader_name
)
const displayTeacherName = computed(() =>
  appearanceStore.isBlindMode && userStore.isExpert ? maskName(project.value?.teacher_name) : project.value?.teacher_name
)
const displayCollegeName = computed(() =>
  appearanceStore.isBlindMode && userStore.isExpert ? maskCollege(project.value?.college_name) : project.value?.college_name
)

const reviewRules: FormRules = {}
const scoreRules: FormRules = {}

async function loadData() {
  const id = Number(route.params.id)
  loading.value = true
  try {
    const [detailRes, reviewRes] = await Promise.all([
      getProjectDetail(id),
      getReviewHistory(id).catch(() => ({ data: { records: [] } })),
    ])
    project.value = detailRes.data
    // 将项目状态同步到主侧边栏的"过程管理"菜单
    processStore.setStatus(detailRes.data.status)
    reviewHistory.value = reviewRes.data?.records || []
  } finally {
    loading.value = false
  }
}

function handleTemplateSelect(text: string) {
  reviewForm.review_comment += (reviewForm.review_comment ? '\n' : '') + text
}

function getBudgetSummary({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col, index) => {
    if (index === 0) {
      sums[index] = '合计'
      return
    }
    if (col.property === 'budget_amount') {
      const total = data.reduce((sum: number, row: any) => sum + Number(row.budget_amount || 0), 0)
      sums[index] = `¥ ${total.toFixed(2)}`
      return
    }
    sums[index] = ''
  })
  return sums
}

async function handleReview(type: 'pass' | 'reject' | 'modify') {
  if ((type === 'reject' || type === 'modify') && !reviewForm.review_comment.trim()) {
    ElMessage.warning(type === 'reject' ? '驳回时必须填写审核意见' : '退回修改时必须填写修改意见')
    return
  }
  const stage = currentReviewStage.value
  if (stage < 0) {
    ElMessage.warning('当前项目不在可审核状态')
    return
  }

  const resultMap: Record<string, number> = { pass: 1, reject: 2, modify: 3 }
  const result = resultMap[type]

  submitLoading.value = true
  try {
    if (userStore.isExpert && stage === 3) {
      // 专家评审（待专家评审阶段 + 当前是专家账号）
      await submitExpertReview({
        project_id: Number(route.params.id),
        score: weightedScore.value,
        review_result: result,
        review_comment: reviewForm.review_comment,
        dimScores: { ...dimScores },
      } as any)
    } else if (stage === 3 && !userStore.isExpert) {
      // 非专家走到这里，属于无权限
      ElMessage.error('仅专家可执行专家评审')
      return
    } else {
      // 普通审核：根据 currentReviewStage 动态传递阶段
      await submitReview({
        project_id: Number(route.params.id),
        review_stage: stage,
        review_result: result,
        review_comment: reviewForm.review_comment,
      })
    }
    const msgMap: Record<string, string> = { pass: '已通过', reject: '已驳回', modify: '已退回修改' }
    ElMessage.success(msgMap[type])
    router.back()
  } finally {
    submitLoading.value = false
  }
}

function stageLabel(stage: number) {
  const map: Record<number, string> = {
    0: '指导教师确认',
    1: '学院初审',
    2: '校级复审',
    3: '专家评审',
    4: '结题验收',
  }
  return map[stage] || '无审核阶段'
}

function stageTagType(stage: number): string {
  const map: Record<number, string> = { 0: 'warning', 1: '', 2: 'success', 3: 'warning', 4: 'danger' }
  return map[stage] || 'info'
}

// 监听主侧边栏的阶段点击，滚动到对应区域
function scrollToSection(key: string) {
  const sectionMap: Record<string, string> = {
    declare: '项目信息',
    teacher: '审核流程',
    college: '审核流程',
    university: '审核流程',
    expert: '审核流程',
    approved: '审核流程',
    midterm: '审核流程',
    achievement: '项目方案',
    final: '审核操作',
  }
  const target = sectionMap[key]
  if (!target) return
  const cards = document.querySelectorAll('.section-card')
  for (const card of cards) {
    const header = card.querySelector('.el-card__header')
    if (header && header.textContent?.includes(target)) {
      card.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
  }
}
watch(() => processStore.scrollToStage, (val) => {
  if (!val) return
  const k = val.split(':')[0]
  scrollToSection(k)
})

onMounted(() => loadData())
onBeforeUnmount(() => processStore.reset())
</script>

<style scoped>
.header-title { font-size: 18px; }
.section-card { margin-top: 16px; }
.plan-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
  color: #303133;
}
.review-actions :deep(.el-form-item__content) {
  justify-content: center;
  gap: 16px;
}
.weighted-score {
  font-size: 22px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.scoring-row {
  display: flex;
  align-items: center;
  width: 100%;
}
.dim-desc {
  color: #909399;
  font-size: 13px;
  width: 260px;
  flex-shrink: 0;
}
.comment-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.blind-tag {
  margin-left: 12px;
}
:deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
