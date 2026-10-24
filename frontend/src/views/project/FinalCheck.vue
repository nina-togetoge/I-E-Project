<!--
  页面名称：结项验收（结项工作台）
  面向角色：项目负责人（填写 / 提交 / 撤回结项报告）、评审专家（验收打分 / 投票）、
           超级管理员（代验收、导出归档）
  核心功能：结项条件检查清单、成果登记 Tab、结项报告填写与提交、专家验收进度、
           多人验收投票、已结题归档包导出。
  调用 API：getProjectDetail、submitFinal、withdrawFinal、downloadProjectArchive、submitReview。
  权限 / 状态约束：
    - 编辑报告：仅负责人 + 待结题(8) + 未提交(0) / 已驳回(3)。
    - 提交截止日后锁定，但「已驳回(3)」允许修改重提，不受截止日限制。
    - 撤回提交：报告待验收(1) + 待结题(8) + 未过截止日 + 负责人或超管。
    - 专家验收入口：后端返回 final_can_accept 且本轮未提交意见、报告待验收。
    - 多人验收时全部提交后按多数意见判定；驳回必须填写意见。
    - 归档导出只对已结题(9)开放。
  关键交互：
    - ?tab=achievements 可直达成果登记 Tab，并监听 query 变化。
    - 成果登记复用 AchievementPanel，与旧路由 /projects/:id/achievements 共用同一面板。
    - 报告状态变化后重新拉取详情，保证进度条与按钮条件同步刷新。
-->
<template>
  <StagePageShell
    :project="project"
    title="结项验收"
    current="final"
    :loading="loading"
    :status-text="reportStatusText"
    :status-type="reportStatusTagType"
  >
    <!-- 页头操作：归档包包含报告与材料，只在已结题(9)后开放 -->
    <template #actions>
      <el-button
        v-if="project?.status === 9"
        type="success"
        :loading="archiving"
        @click="handleExportArchive"
      >导出结项归档</el-button>
    </template>

    <!-- 截止日提示：已驳回(3) 的文案会说明「修改重提不受截止日限制」，
         避免用户误以为过期后仍被永久锁定 -->
    <el-alert
      v-if="finalDeadlineText && project?.status === 8"
      :title="finalDeadlineText"
      :type="finalLocked && reportStatus !== 3 ? 'warning' : 'info'"
      :closable="false"
      class="mb-16"
      show-icon
    />

    <!-- 状态提示：按报告状态展示通过 / 驳回 / 待验收 / 未进入阶段；
         报告状态与项目状态分开判断，避免把「未结题」误显示成「未提交」 -->
    <el-alert
      v-if="reportStatus === 2"
      title="结项验收已通过，项目已完成结题"
      type="success"
      :closable="false"
      show-icon
      class="mb-16"
    />
    <el-alert
      v-else-if="reportStatus === 3"
      :title="`验收驳回：${project?.final_reject_reason || project?.reject_reason || '请修改后重新提交'}`"
      type="error"
      :closable="false"
      show-icon
      class="mb-16"
    />
    <el-alert
      v-else-if="reportStatus === 1"
      title="结项验收报告已提交，等待专家验收"
      type="success"
      :closable="false"
      show-icon
      class="mb-16"
    />
    <el-alert
      v-else-if="project && project.status !== 8"
      title="当前项目尚未进入结项验收阶段"
      type="info"
      :closable="false"
      show-icon
      class="mb-16"
    />

    <!-- 结项条件检查：清单由后端计算（成果数量、中期结论等），
         提交报告前可随时核对未通过项 -->
    <el-card v-if="checklist.length && isFinalStage" shadow="never" class="mb-16">
      <template #header><span class="card-title">结项条件检查</span></template>
      <div v-for="item in checklist" :key="item.key" class="check-item">
        <el-icon :class="item.passed ? 'check-pass' : 'check-fail'">
          <CircleCheckFilled v-if="item.passed" />
          <WarningFilled v-else />
        </el-icon>
        <span class="check-label">{{ item.label }}</span>
        <span class="check-detail">{{ item.detail }}</span>
      </div>
    </el-card>

    <!-- 双 Tab：成果登记与结项报告；成果 Tab 使用 lazy，避免未进入时提前请求成果列表 -->
    <el-tabs v-model="activeTab" class="final-tabs">
      <!-- 成果登记：与旧路由 /projects/:id/achievements 共用同一面板 -->
      <el-tab-pane label="成果登记" name="achievements" lazy>
        <AchievementPanel v-if="project" :project="project" />
      </el-tab-pane>

      <el-tab-pane label="结项报告与验收" name="final">
        <!-- 专家验收进度：仅报告待验收且存在验收人时展示，用于告知负责人还差几位专家 -->
        <el-card v-if="reportStatus === 1 && reviewTotal > 0" shadow="never" class="mb-16">
          <template #header><span class="card-title">专家验收进度</span></template>
          <div class="review-progress">
            <el-progress
              :percentage="reviewPercent"
              :status="reviewPercent === 100 ? 'success' : undefined"
              style="flex: 1"
            />
            <span class="review-count">{{ reviewDone }} / {{ reviewTotal }} 位专家已提交验收意见</span>
          </div>
        </el-card>

        <!-- 结项报告：可编辑区与只读区互斥，避免非负责人在只读区看到表单控件 -->
        <el-card shadow="never" class="mb-16">
          <template #header><span class="card-title">结项验收报告</span></template>

          <!-- 可编辑：待结题(8) + 负责人 + 未提交(0) / 已驳回(3)；
               已驳回时按钮文案改为「重新提交」，且不受截止日限制 -->
          <el-form
            v-if="canEdit"
            ref="finalFormRef"
            :model="finalForm"
            :rules="finalRules"
            label-width="100px"
          >
            <el-form-item label="结项报告" prop="final_report">
              <el-input
                v-model="finalForm.final_report"
                type="textarea"
                :rows="8"
                placeholder="请填写项目完成情况、成果总结等结项验收报告内容"
                maxlength="2000"
                show-word-limit
              />
            </el-form-item>
            <el-form-item label="验收材料">
              <FileUpload
                :accept="['.pdf', '.doc', '.docx', '.zip', '.rar', '.png', '.jpg']"
                :form-data="{ biz_type: 'project', biz_id: 0 }"
                @success="handleFinalFileUpload"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="success"
                :loading="finalLoading"
                :disabled="finalLocked && reportStatus !== 3"
                @click="handleSubmitFinal"
              >{{ reportStatus === 3 ? '重新提交结项报告' : '提交结项报告' }}</el-button>
            </el-form-item>
          </el-form>

          <!-- 只读：已提交 / 已结题 / 非负责人；非负责人且报告未提交时给出权限说明 -->
          <template v-else>
            <div v-if="project?.final_report" class="report-text">{{ project.final_report }}</div>
            <div v-else class="report-empty">
              项目进入「待结题」阶段后，由负责人填写并提交结项验收报告。
            </div>
            <el-alert
              v-if="!isLeader && project?.status === 8 && reportStatus === 0"
              title="仅项目负责人可填写并提交结项验收报告"
              type="info"
              :closable="false"
              show-icon
              class="mt-16"
            />
            <el-button
              v-if="canWithdrawFinal"
              type="warning"
              :loading="finalLoading"
              class="mt-16"
              @click="handleWithdrawFinal"
            >撤回报告提交</el-button>
          </template>
        </el-card>

        <!-- 专家验收：由后端 final_can_accept 决定是否为本轮验收人；
             多人验收时提示「全部提交后按多数意见判定」 -->
        <el-card v-if="canAcceptNow" shadow="never">
          <template #header><span class="card-title">专家验收</span></template>
          <el-alert
            v-if="reviewTotal > 1"
            :title="`该项目由 ${reviewTotal} 位专家验收，全部提交后按多数意见判定`"
            type="info"
            :closable="false"
            show-icon
            class="mb-16"
          />
          <el-form label-width="100px">
            <el-form-item label="验收意见">
              <el-input
                v-model="acceptComment"
                type="textarea"
                :rows="3"
                placeholder="请填写验收意见（驳回时请说明需要修改的内容）"
                maxlength="1000"
                show-word-limit
              />
            </el-form-item>
            <el-form-item>
              <el-button type="success" :loading="acceptLoading" @click="handleAccept('pass')">通过</el-button>
              <el-button type="danger" :loading="acceptLoading" @click="handleAccept('reject')">驳回</el-button>
            </el-form-item>
          </el-form>
        </el-card>
        <el-alert
          v-else-if="project?.final_can_accept && project?.final_reviewed_by_me && reportStatus === 1"
          title="您已提交本轮验收意见，等待其他专家验收"
          type="info"
          :closable="false"
          show-icon
          class="mb-16"
        />
      </el-tab-pane>
    </el-tabs>
  </StagePageShell>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { CircleCheckFilled, WarningFilled } from '@element-plus/icons-vue'
import { getProjectDetail, submitFinal, withdrawFinal, downloadProjectArchive } from '@/api/project'
import { submitReview } from '@/api/review'
import FileUpload from '@/components/FileUpload.vue'
import StagePageShell from '@/components/StagePageShell.vue'
import AchievementPanel from '@/components/AchievementPanel.vue'
import { useProcessStore } from '@/store/process'
import { useUserStore } from '@/store/user'

// ==================== 路由 / Store / 项目标识 ====================
// 结项页按项目 ID 独立成页；project 驱动阶段、截止日与验收人判断。
const route = useRoute()
const processStore = useProcessStore()
const userStore = useUserStore()

const pid = computed(() => Number(route.params.id))
/** 项目详情：包含结项报告状态、条件清单、验收进度等后端计算字段 */
const project = ref<any>(null)
/** 首屏加载态 */
const loading = ref(true)
/** 报告提交 / 撤回按钮 loading */
const finalLoading = ref(false)
/** 专家验收提交按钮 loading */
const acceptLoading = ref(false)
/** 归档包导出按钮 loading */
const archiving = ref(false)
const finalFormRef = ref<FormInstance>()
/** 结项报告表单：仅负责人可编辑，其余角色只读展示 project.final_report */
const finalForm = reactive({ final_report: '' })
/** 专家验收意见：驳回时必填 */
const acceptComment = ref('')
/** 本次新上传的验收材料 id，提交时随报告一起下发 */
const finalAttachmentIds = ref<number[]>([])
const finalRules: FormRules = {
  final_report: [{ required: true, message: '请填写结项验收报告', trigger: 'blur' }],
}

/** 当前 Tab：默认结项报告；?tab=achievements 可直达成果登记，并随 query 变化同步 */
type FinalTab = 'achievements' | 'final'
const activeTab = ref<FinalTab>(route.query.tab === 'achievements' ? 'achievements' : 'final')
watch(
  () => route.query.tab,
  (tab) => { activeTab.value = tab === 'achievements' ? 'achievements' : 'final' },
)

/** 是否为项目负责人（后端 submit 仅允许负责人） */
const isLeader = computed(() =>
  !!project.value && Number(userStore.userInfo?.id) === Number(project.value.leader_id)
)

/** 结项报告状态：0未提交 1待验收 2已通过 3已驳回 */
const reportStatus = computed(() => Number(project.value?.final_report_status ?? 0))
/** 项目状态是否已进入结项阶段（待结题 8 / 已结题 9） */
const isFinalStage = computed(() => [8, 9].includes(Number(project.value?.status)))
/** 页头状态文案：未进入结项阶段时统一显示「未开始」，避免误报为「未提交」 */
const reportStatusText = computed(() => {
  const map: Record<number, string> = { 0: '未提交', 1: '待专家验收', 2: '验收通过', 3: '验收驳回' }
  if (reportStatus.value === 0 && !isFinalStage.value) return '未开始'
  return map[reportStatus.value] || '未提交'
})
const reportStatusTagType = computed<'primary' | 'success' | 'info' | 'warning' | 'danger'>(() => {
  const map: Record<number, 'primary' | 'success' | 'info' | 'warning' | 'danger'> = {
    0: 'info', 1: 'warning', 2: 'success', 3: 'danger',
  }
  return map[reportStatus.value] || 'info'
})

/** 结项条件检查清单：由后端统一计算，前端只负责展示通过 / 未通过 */
const checklist = computed(() => project.value?.final_checklist || [])
/** 验收专家总数与已提交数，用于计算进度百分比 */
const reviewTotal = computed(() => Number(project.value?.final_review_total || 0))
const reviewDone = computed(() => Number(project.value?.final_review_done || 0))
const reviewPercent = computed(() =>
  reviewTotal.value ? Math.round((reviewDone.value / reviewTotal.value) * 100) : 0
)

/** 结项验收截止日（截止日驱动锁定）；只比较日期，忽略时分秒 */
const finalLocked = computed(() => {
  const d = project.value?.final_deadline
  if (!d) return false
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const t = new Date(`${String(d).slice(0, 10)}T00:00:00`)
  return Math.round((t.getTime() - today.getTime()) / 86400000) < 0
})
const finalDeadlineText = computed(() => {
  const d = project.value?.final_deadline
  if (!d) return ''
  const ds = String(d).slice(0, 10)
  if (reportStatus.value === 3) return `结题截止日：${ds}（已驳回，修改重提不受截止日限制）`
  return finalLocked.value ? `已超过结题截止日（${ds}），无法提交报告` : `结题截止日：${ds}`
})

/** 负责人可编辑：待结题 + 未提交/已驳回 */
const canEdit = computed(() =>
  isLeader.value && project.value?.status === 8 && (reportStatus.value === 0 || reportStatus.value === 3)
)
/** 撤回提交：已提交待验收 + 未过截止日 + 负责人/超管 */
const canWithdrawFinal = computed(() =>
  reportStatus.value === 1
  && project.value?.status === 8
  && !finalLocked.value
  && (isLeader.value || userStore.isSuperAdmin)
)
/** 专家验收入口：后端返回可验收 + 本轮未提交意见 + 报告待验收 + 项目待结题 */
const canAcceptNow = computed(() =>
  !!project.value?.final_can_accept
  && !project.value?.final_reviewed_by_me
  && reportStatus.value === 1
  && project.value?.status === 8
)

/**
 * 验收材料上传成功：按 id 去重后暂存，提交报告时一并绑定。
 * 参数 file：FileUpload 返回的文件对象。
 */
function handleFinalFileUpload(file: any) {
  if (file?.id && !finalAttachmentIds.value.includes(file.id)) {
    finalAttachmentIds.value.push(file.id)
  }
}

/**
 * 提交结项报告：先做表单校验，再携带本次新增附件 id 一起提交。
 * 失败处理：校验失败由 el-form 提示并中止；接口异常由全局拦截器提示，
 *           finally 复位 loading，成功后清空附件缓存并刷新详情。
 */
async function handleSubmitFinal() {
  await finalFormRef.value?.validate()
  finalLoading.value = true
  try {
    await submitFinal(pid.value, {
      final_report: finalForm.final_report,
      attachment_ids: finalAttachmentIds.value,
    })
    ElMessage.success('结项验收报告已提交，等待专家验收')
    finalAttachmentIds.value = []
    loadData()
  } finally {
    finalLoading.value = false
  }
}

/**
 * 撤回结项报告：报告退回未提交状态，项目仍为待结题。
 * 失败处理：取消确认直接返回；接口异常由全局拦截器提示。
 */
async function handleWithdrawFinal() {
  try {
    await ElMessageBox.confirm(
      '撤回后本次结项验收报告将作废，项目仍处于待结题，可修改后重新提交。确定撤回？',
      '撤回报告提交',
      { type: 'warning', confirmButtonText: '确定撤回', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  finalLoading.value = true
  try {
    await withdrawFinal(pid.value)
    ElMessage.success('结项验收报告已撤回，可修改后重新提交')
    loadData()
  } finally {
    finalLoading.value = false
  }
}

/**
 * 导出结项归档包（报告 + 材料），文件名带项目编号便于归档。
 * 失败处理：捕获异常并提示「导出失败，请稍后重试」，避免下载失败时无反馈。
 */
async function handleExportArchive() {
  archiving.value = true
  try {
    const name = `项目归档_${project.value?.project_no || pid.value}.zip`
    await downloadProjectArchive(pid.value, name)
    ElMessage.success('归档包已开始下载')
  } catch {
    ElMessage.error('导出失败，请稍后重试')
  } finally {
    archiving.value = false
  }
}

/**
 * 专家提交验收意见。
 * 参数 type：pass 通过、reject 驳回；驳回必须填写意见。
 * 说明：多人验收时按多数意见判定，因此提示文案会区分「等待其他专家」与「最终结果」。
 * 失败处理：意见缺失仅提示；接口异常由全局拦截器提示，成功后刷新详情。
 */
async function handleAccept(type: 'pass' | 'reject') {
  if (type === 'reject' && !acceptComment.value.trim()) {
    ElMessage.warning('驳回时必须填写验收意见')
    return
  }
  acceptLoading.value = true
  try {
    await submitReview({
      project_id: pid.value,
      review_stage: 4,
      review_result: type === 'pass' ? 1 : 2,
      review_comment: acceptComment.value.trim(),
    })
    ElMessage.success(
      reviewTotal.value > 1
        ? '验收意见已提交，等待其他专家验收'
        : (type === 'pass' ? '结项验收已通过' : '结项验收已驳回')
    )
    acceptComment.value = ''
    loadData()
  } finally {
    acceptLoading.value = false
  }
}

/**
 * 加载项目详情并同步侧边栏阶段。
 * 说明：仅在可编辑时回填报告正文，避免覆盖只读态下展示的后端最终文本。
 * 失败处理：提示「加载失败」，finally 复位 loading。
 */
async function loadData() {
  loading.value = true
  try {
    const res = await getProjectDetail(pid.value)
    project.value = res.data
    processStore.setStatus(res.data.status)
    if (canEdit.value) {
      finalForm.final_report = res.data.final_report || ''
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => loadData())
onBeforeUnmount(() => processStore.reset())
</script>

<style scoped>
.mb-16 { margin-bottom: 16px; }
.mt-16 { margin-top: 16px; }
.card-title { font-weight: 600; }
.final-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
.check-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  font-size: 14px;
}
.check-pass { color: #67c23a; font-size: 18px; }
.check-fail { color: #e6a23c; font-size: 18px; }
.check-label { min-width: 140px; color: #303133; }
.check-detail { color: #909399; font-size: 13px; }
.report-text {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #303133;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 16px;
  min-height: 120px;
}
.report-empty {
  padding: 24px 16px;
  text-align: center;
  color: #909399;
  font-size: 13px;
  background: #fafafa;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
}
.review-progress { display: flex; align-items: center; gap: 16px; }
.review-count { color: #606266; font-size: 13px; white-space: nowrap; }
</style>
