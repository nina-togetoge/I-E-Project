<!--
  审核操作面板
  从原「审核详情页」抽离，嵌入项目详情（弹窗/页面）内使用
  支持：普通审核（通过 / 驳回）、专家评审（分项加权打分）
  仅当当前用户对项目当前阶段有审核权限时渲染
-->
<template>
  <section v-if="show" class="paper-section">
    <h2 class="section-title">
      <span class="section-num">{{ sectionNum }}</span>审核操作
      <el-tag :type="stageTagType(currentReviewStage)" size="small" class="section-tag">
        {{ stageLabel(currentReviewStage) }}
      </el-tag>
    </h2>

    <!-- 专家评分（仅专家评审阶段打分，结题验收不打分） -->
    <el-form
      v-if="userStore.isExpert && currentReviewStage === 3"
      :model="scoreForm"
      label-width="140px"
    >
      <el-form-item label="加权总分">
        <span class="weighted-score">{{ weightedScore.toFixed(2) }} 分</span>
      </el-form-item>
      <el-form-item
        v-for="criterion in scoringCriteria"
        :key="criterion.key"
        :label="`${criterion.name}(${criterion.weight * 100}%)`"
      >
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
      <el-form-item label="各维度评价">
        <el-input
          v-model="scoreForm.dim_comments"
          type="textarea"
          :rows="3"
          placeholder="可填写各维度的详细评价文字（选填）"
          maxlength="1000"
          show-word-limit
        />
      </el-form-item>
    </el-form>

    <!-- 中期检查报告（仅中期检查审核阶段展示，供指导教师审阅） -->
    <el-descriptions
      v-if="currentReviewStage === 5 && midterm"
      :column="1"
      border
      size="small"
      class="midterm-report"
    >
      <el-descriptions-item label="项目进展">{{ midterm.progress_desc || '—' }}</el-descriptions-item>
      <el-descriptions-item label="已完成任务">{{ midterm.completed_tasks || '—' }}</el-descriptions-item>
      <el-descriptions-item label="未完成任务">{{ midterm.remaining_tasks || '—' }}</el-descriptions-item>
      <el-descriptions-item label="存在问题">{{ midterm.problems || '—' }}</el-descriptions-item>
      <el-descriptions-item label="下一步计划">{{ midterm.next_plan || '—' }}</el-descriptions-item>
      <el-descriptions-item label="经费使用">
        ¥ {{ Number(midterm.budget_usage || 0).toFixed(2) }}
      </el-descriptions-item>
    </el-descriptions>

    <el-form :model="reviewForm" label-width="140px">
      <el-form-item label="审核意见" prop="review_comment">
        <div class="comment-header">
          <ReviewTemplatePicker @select="handleTemplateSelect" />
        </div>
        <el-input
          v-model="reviewForm.review_comment"
          type="textarea"
          :rows="4"
          placeholder="请填写审核意见（驳回时必填）"
          maxlength="1000"
          show-word-limit
        />
      </el-form-item>
      <el-form-item label-width="0" class="review-actions">
        <el-tooltip
          v-if="passDisabled"
          :content="`评分低于及格线（${EXPERT_PASS_SCORE} 分），不能判定为通过`"
          placement="top"
        >
          <span>
            <el-button type="success" disabled>通过</el-button>
          </span>
        </el-tooltip>
        <el-button v-else type="success" :loading="submitLoading" @click="handleReview('pass')">通过</el-button>
        <el-button type="danger" :loading="submitLoading" @click="handleReview('reject')">驳回</el-button>
      </el-form-item>
    </el-form>
  </section>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import ReviewTemplatePicker from '@/components/ReviewTemplatePicker.vue'
import { useUserStore } from '@/store/user'
import { submitReview, submitExpertReview, getMidtermCheck, reviewMidtermCheck } from '@/api/review'
import { scoringCriteria, calculateWeightedScore, sliderMarks, EXPERT_PASS_SCORE, EXPERT_PASS_COMMENT_MIN, type DimScores } from '@/data/scoringCriteria'

const props = defineProps<{
  projectId: number
  project: any
  /** 项目完整审核流程记录（父组件已加载），用于判断当前用户是否已评审过当前阶段 */
  reviewHistory?: any[]
  /** 章节序号，由父组件按详情页区块顺序传入，保证与其它区块统一编号 */
  sectionNum: number
}>()
const emit = defineEmits<{ submitted: [] }>()

const userStore = useUserStore()

const submitLoading = ref(false)

// 中期检查审核阶段（状态 7）所需的中期检查记录
const midterm = ref<any>(null)

async function loadMidterm() {
  if (!props.projectId || currentReviewStage.value !== 5) return
  try {
    const res = await getMidtermCheck(props.projectId)
    midterm.value = res.data || null
  } catch {
    midterm.value = null
  }
}

const reviewForm = reactive({ review_comment: '' })

const dimScores = reactive<DimScores>({
  innovation: 0,
  feasibility: 0,
  team: 0,
  market: 0,
})

const scoreForm = reactive({
  score: 0,
  dim_comments: '',
})

const weightedScore = computed(() => {
  const total = calculateWeightedScore(dimScores)
  scoreForm.score = total
  return total
})

// 专家评审阶段：加权总分低于及格线时禁用「通过」按钮
const passDisabled = computed(
  () => userStore.isExpert && currentReviewStage.value === 3 && weightedScore.value < EXPERT_PASS_SCORE
)

/** 根据项目状态映射到对应的审核阶段（与后端 ReviewService._get_stage_from_status 保持一致） */
const currentReviewStage = computed((): number => {
  const status = props.project?.status ?? 0
  if (status === 12) return 0  // 待指导教师确认
  if (status === 1) return 1   // 待学院初审
  if (status === 3) return 2   // 待校级复审
  if (status === 5) return 3   // 待专家评审
  if (status === 7) return 5   // 中期检查审核
  if (status === 8) return 4   // 待结题验收
  return -1
})

/** 当前用户是否可在该阶段审核 */
const canReviewCurrentStage = computed((): boolean => {
  if (!props.project) return false
  const stage = currentReviewStage.value
  if (stage < 0) return false
  // 专家评审阶段由专家操作
  if (stage === 3) return userStore.isExpert
  // 指导教师确认：仅该项目的指导教师本人（超管可代操作）
  if (stage === 0) {
    return Number(userStore.userInfo?.id) === Number(props.project.teacher_id) || userStore.isSuperAdmin
  }
  // 学院初审：仅超级管理员 / 本院学院管理员
  if (stage === 1) {
    if (userStore.isSuperAdmin) return true
    return userStore.isCollegeAdmin && Number(userStore.collegeId) === Number(props.project.college_id)
  }
  // 校级复审：仅真超级管理员
  if (stage === 2) return userStore.isSuperAdmin
  // 结题验收：超级管理员或专家
  if (stage === 4) return userStore.isSuperAdmin || userStore.isExpert
  // 中期检查审核：仅该项目的指导教师本人（超管可代操作）
  if (stage === 5) {
    return (
      Number(userStore.userInfo?.id) === Number(props.project.teacher_id) || userStore.isSuperAdmin
    )
  }
  return false
})

/** 当前用户是否已在本阶段出过审核结果（占位记录 result=99 不算）。
 *  已评审过则不再渲染操作面板，避免向后端重复提交被拒（"您已完成此项目的评审"）。 */
const alreadyReviewedCurrentStage = computed((): boolean => {
  const stage = currentReviewStage.value
  const uid = Number(userStore.userInfo?.id)
  if (stage < 0 || !uid) return false
  return (props.reviewHistory || []).some(
    (r) => Number(r.reviewer_id) === uid && Number(r.review_stage) === stage && r.review_result !== 99
  )
})

// 中期检查阶段需要存在「待审核(1)」的记录才能操作
const show = computed(
  () =>
    canReviewCurrentStage.value &&
    !alreadyReviewedCurrentStage.value &&
    (currentReviewStage.value !== 5 || midterm.value?.status === 1)
)

function stageLabel(stage: number) {
  const map: Record<number, string> = {
    0: '指导教师确认', 1: '学院初审', 2: '校级复审', 3: '专家评审', 4: '结题验收', 5: '中期检查审核',
  }
  return map[stage] || '无审核阶段'
}

function stageTagType(stage: number): string {
  const map: Record<number, string> = { 0: 'warning', 1: 'primary', 2: 'success', 3: 'warning', 4: 'danger', 5: 'primary' }
  return map[stage] || 'info'
}

function handleTemplateSelect(text: string) {
  reviewForm.review_comment += (reviewForm.review_comment ? '\n' : '') + text
}

async function handleReview(type: 'pass' | 'reject') {
  if (type === 'reject' && !reviewForm.review_comment.trim()) {
    ElMessage.warning('驳回时必须填写审核意见')
    return
  }
  const stage = currentReviewStage.value
  if (stage < 0) {
    ElMessage.warning('当前项目不在可审核状态')
    return
  }
  // 专家评审判定通过：评分须达到及格线，且评审意见不少于规定字数（与后端 ExpertReviewCreateRequest 校验一致）
  if (type === 'pass' && stage === 3 && userStore.isExpert) {
    if (weightedScore.value < EXPERT_PASS_SCORE) {
      ElMessage.warning(`当前评分 ${weightedScore.value} 分低于及格线 ${EXPERT_PASS_SCORE} 分，不能判定为通过`)
      return
    }
    if (reviewForm.review_comment.trim().length < EXPERT_PASS_COMMENT_MIN) {
      ElMessage.warning(`判定为通过时，评审意见不得少于 ${EXPERT_PASS_COMMENT_MIN} 个字符`)
      return
    }
  }

  const resultMap: Record<string, number> = { pass: 1, reject: 2 }
  const result = resultMap[type]

  submitLoading.value = true
  try {
    if (userStore.isExpert && stage === 3) {
      // 专家评审：提交分项加权打分
      await submitExpertReview({
        project_id: props.projectId,
        score: weightedScore.value,
        review_result: result,
        review_comment: reviewForm.review_comment,
        dim_scores: { ...dimScores },
      })
    } else if (stage === 5) {
      // 中期检查审核：通过 / 驳回
      await reviewMidtermCheck({
        check_id: midterm.value.id,
        result,
        review_comment: reviewForm.review_comment,
      })
    } else {
      // 普通审核：按当前阶段提交
      await submitReview({
        project_id: props.projectId,
        review_stage: stage,
        review_result: result,
        review_comment: reviewForm.review_comment,
      })
    }
    const msgMap: Record<string, string> = { pass: '已通过', reject: '已驳回' }
    ElMessage.success(stage === 5 ? `中期检查${msgMap[type]}` : msgMap[type])
    reviewForm.review_comment = ''
    emit('submitted')
  } finally {
    submitLoading.value = false
  }
}

onMounted(loadMidterm)
watch(() => props.projectId, () => loadMidterm())
</script>

<style scoped>
/* 与项目详情页其它区块（论文章节）保持一致的卡片样式 */
.paper-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px 28px;
  margin-bottom: 16px;
}
.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 16px;
  padding: 6px 0 6px 12px;
  border-left: 4px solid #409eff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: #409eff;
  color: #fff;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 600;
  margin-right: 4px;
}
.section-tag {
  margin-left: auto;
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
.midterm-report {
  margin-bottom: 16px;
}
.midterm-report :deep(.el-descriptions__label) {
  width: 110px;
}

.comment-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.review-actions :deep(.el-form-item__content) {
  justify-content: center;
  gap: 16px;
}
</style>