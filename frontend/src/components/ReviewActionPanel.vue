<!--
  审核操作面板（ReviewActionPanel）
  来源：从原「审核详情页」抽离，现嵌入项目详情（弹窗或独立页面）内使用。

  面向角色：指导教师、学院管理员、超级管理员、评审专家。
  核心功能：根据项目状态换算审核阶段，仅向「有权限 + 本阶段未评审」的用户渲染表单；
           支持普通审核（通过 / 驳回）、专家评审（分项加权打分）、中期检查审核。

  调用 API：
    - submitReview：指导教师确认、学院初审、校级复审、结题验收等普通阶段；
    - submitExpertReview：专家评审阶段，提交加权总分与各维度分数；
    - getMidtermCheck / reviewMidtermCheck：中期检查报告的读取与审核。

  关键权限 / 状态约束：
    1. 状态到阶段的映射必须与后端 ReviewService._get_stage_from_status 保持一致，
       否则会出现「前端能点、后端拒审」的阶段错位；
    2. 同一 reviewer_id + review_stage 已存在有效结果（review_result !== 99）即视为已评审，
       面板直接隐藏，避免重复提交触发后端「您已完成此项目的评审」；
    3. 专家判定通过需同时满足：加权总分达到及格线、审核意见不少于最低字数；
    4. 中期检查仅在报告状态为待审核(1)时开放审核，报告未提交则无可审内容。

  特别注意的交互：中期报告由本组件按需拉取（仅阶段 5），父组件只负责传项目与审核历史；
                   提交成功后不自行刷新详情，仅 emit('submitted') 交给父组件统一处理。
-->
<template>
  <section v-if="show" class="paper-section">
    <h2 class="section-title">
      <span class="section-num">{{ sectionNum }}</span>审核操作
      <el-tag :type="stageTagType(currentReviewStage)" size="small" class="section-tag">
        {{ stageLabel(currentReviewStage) }}
      </el-tag>
    </h2>

    <!-- 专家评分区：仅「专家 + 专家评审阶段(3)」渲染。
         结题验收阶段(4)虽然专家也可操作，但验收是对成果的确认，不再重复打分。 -->
    <el-form
      v-if="userStore.isExpert && currentReviewStage === 3"
      :model="scoreForm"
      label-width="140px"
    >
      <!-- 加权总分由下方各维度滑杆实时计算，只读展示，提交时随 review 一起上送 -->
      <el-form-item label="加权总分">
        <span class="weighted-score">{{ weightedScore.toFixed(2) }} 分</span>
      </el-form-item>
      <!-- 维度滑杆：0~100 分，标签中直接标出该维度权重，便于专家理解总分构成 -->
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
      <!-- 各维度评价：选填，仅作文字补充，不影响加权总分计算 -->
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

    <!-- 中期检查报告区：阶段 5 时展示，让指导教师在同一面板内先读报告再写审核意见；
         数据由 loadMidterm 单独拉取，未加载到报告时整块不渲染。 -->
    <el-descriptions
      v-if="currentReviewStage === 5 && midterm"
      :column="1"
      border
      size="small"
      class="midterm-report"
    >
      <!-- 报告字段均可能为空，统一用「—」占位，避免出现空白行难以判断是否漏填 -->
      <el-descriptions-item label="项目进展">{{ midterm.progress_desc || '—' }}</el-descriptions-item>
      <el-descriptions-item label="已完成任务">{{ midterm.completed_tasks || '—' }}</el-descriptions-item>
      <el-descriptions-item label="未完成任务">{{ midterm.remaining_tasks || '—' }}</el-descriptions-item>
      <el-descriptions-item label="存在问题">{{ midterm.problems || '—' }}</el-descriptions-item>
      <el-descriptions-item label="下一步计划">{{ midterm.next_plan || '—' }}</el-descriptions-item>
      <el-descriptions-item label="经费使用">
        ¥ {{ Number(midterm.budget_usage || 0).toFixed(2) }}
      </el-descriptions-item>
    </el-descriptions>

    <!-- 审核表单：所有可审核阶段共用；意见文本框保留 1000 字上限，与服务端字段长度对齐 -->
    <el-form :model="reviewForm" label-width="140px">
      <el-form-item label="审核意见" prop="review_comment">
        <!-- 意见模板：选择后会把模板文字追加到现有内容，不清空已手写部分 -->
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
        <!-- 专家评分未达及格线时「通过」置灰：禁用按钮不触发鼠标事件，
             因此外包一层 span 让 tooltip 仍能解释禁用原因，而不是让用户无从下手。 -->
        <el-tooltip
          v-if="passDisabled"
          :content="`评分低于及格线（${EXPERT_PASS_SCORE} 分），不能判定为通过`"
          placement="top"
        >
          <span>
            <el-button type="success" disabled>通过</el-button>
          </span>
        </el-tooltip>
        <!-- 驳回不校验分数，但仍需填写意见（在 handleReview 内兜底校验） -->
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

// ==================== 依赖与页面状态 ====================

const userStore = useUserStore()

/** 审核提交中：防止连点重复提交，也用于按钮 loading 反馈 */
const submitLoading = ref(false)

/** 中期检查审核阶段（状态 7）所需的中期检查记录；非该阶段保持 null */
const midterm = ref<any>(null)

/**
 * 拉取中期检查报告，仅在中期审核阶段(5)执行，其他阶段直接跳过以省去无效请求。
 * 失败处理：接口异常或数据缺失都置 null，让报告区自然隐藏，不阻塞审核面板的其它阶段。
 */
async function loadMidterm() {
  if (!props.projectId || currentReviewStage.value !== 5) return
  try {
    const res = await getMidtermCheck(props.projectId)
    midterm.value = res.data || null
  } catch {
    midterm.value = null
  }
}

/** 审核意见表单：通过时可空，驳回时必填；提交成功后清空 */
const reviewForm = reactive({ review_comment: '' })

// ==================== 专家评分状态 ====================

/** 各维度原始分（0~100），键与 scoringCriteria 的 key 对应 */
const dimScores = reactive<DimScores>({
  innovation: 0,
  feasibility: 0,
  team: 0,
  market: 0,
})

/** 专家评分提交体：score 由 weightedScore 回写，dim_comments 为选填文字评价 */
const scoreForm = reactive({
  score: 0,
  dim_comments: '',
})

/**
 * 加权总分。
 * 副作用：计算之余把结果回写到 scoreForm.score，保证提交体与界面展示一致。
 * 说明：使用计算属性而非 watch，避免滑杆拖动时出现一次额外渲染延迟。
 */
const weightedScore = computed(() => {
  const total = calculateWeightedScore(dimScores)
  scoreForm.score = total
  return total
})

/** 专家评审阶段加权总分低于及格线时禁用「通过」；其他阶段/角色不受影响 */
const passDisabled = computed(
  () => userStore.isExpert && currentReviewStage.value === 3 && weightedScore.value < EXPERT_PASS_SCORE
)

// ==================== 阶段映射与权限判断 ====================

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

/**
 * 当前用户是否可在该阶段审核。
 * 规则按阶段区分角色，且学院初审额外校验 college_id，避免跨学院越权。
 * 返回 false 时整个面板不渲染，而不是渲染后禁用。
 */
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

// ==================== 已评审去重与显示条件 ====================

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

/** 面板总开关：有权限、未评审、且中期阶段确有「待审核(1)」的报告时才展示。
 *  三条件缺一不可，避免出现空表单或提交后被后端拒绝的无效操作。 */
const show = computed(
  () =>
    canReviewCurrentStage.value &&
    !alreadyReviewedCurrentStage.value &&
    (currentReviewStage.value !== 5 || midterm.value?.status === 1)
)

// ==================== 展示辅助 ====================

/**
 * 审核阶段的中文名称，用于标题右侧标签。
 * @param stage 阶段编号，-1 或未知值显示「无审核阶段」
 */
function stageLabel(stage: number) {
  const map: Record<number, string> = {
    0: '指导教师确认', 1: '学院初审', 2: '校级复审', 3: '专家评审', 4: '结题验收', 5: '中期检查审核',
  }
  return map[stage] || '无审核阶段'
}

/**
 * 阶段标签的 Element Plus 颜色类型，用于区分不同审核环节。
 * @param stage 阶段编号，未知值回退为 info
 */
function stageTagType(stage: number): string {
  const map: Record<number, string> = { 0: 'warning', 1: 'primary', 2: 'success', 3: 'warning', 4: 'danger', 5: 'primary' }
  return map[stage] || 'info'
}

/**
 * 追加常用审核意见模板。
 * 副作用：直接修改 reviewForm.review_comment，已有内容会保留并在前置换行。
 * @param text 模板文字
 */
function handleTemplateSelect(text: string) {
  reviewForm.review_comment += (reviewForm.review_comment ? '\n' : '') + text
}

// ==================== 审核提交 ====================

/**
 * 提交审核结果。
 * 功能：按当前阶段分流到专家评审 / 中期审核 / 普通审核三套接口。
 * 校验：驳回必须填意见；专家判定通过还需达到及格线与最小意见字数，与后端校验保持一致。
 * 副作用：提交成功后清空意见、emit('submitted') 通知父组件刷新；失败时不清理输入，便于用户重试。
 * 失败处理：请求异常由全局拦截器提示；本函数仅通过 finally 复位 loading。
 * @param type 'pass' 通过，'reject' 驳回
 */
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

  // 结果码与后端约定：1=通过，2=驳回；99 为占位记录，表示尚未真正评审
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

// ==================== 生命周期 ====================

// 首次挂载即判断是否需要中期报告；项目切换时重新拉取，避免沿用上一个项目的报告。
// 注意：父组件只传 projectId 与审核历史，报告数据完全由本组件自取。
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