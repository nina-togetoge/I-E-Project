<!--
  结项验收（结项工作台）
  顶部固定「结项条件检查」，下方 Tab 分为「成果登记」与「结项报告与验收」。
  待结题(8)：负责人填写结项验收报告并提交，等待专家验收；驳回后可直接修改重提（不受截止日限制）
  已结题(9)：展示验收结果与报告正文
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
    <template #actions>
      <el-button
        v-if="project?.status === 9"
        type="success"
        :loading="archiving"
        @click="handleExportArchive"
      >导出结项归档</el-button>
    </template>

    <!-- 截止日提示（已驳回时不受截止日限制） -->
    <el-alert
      v-if="finalDeadlineText && project?.status === 8"
      :title="finalDeadlineText"
      :type="finalLocked && reportStatus !== 3 ? 'warning' : 'info'"
      :closable="false"
      class="mb-16"
      show-icon
    />

    <!-- 状态提示 -->
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

    <!-- 结项条件检查（固定在 Tab 上方，提交报告前可随时核对） -->
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

    <el-tabs v-model="activeTab" class="final-tabs">
      <!-- 成果登记：与旧路由 /projects/:id/achievements 共用同一面板 -->
      <el-tab-pane label="成果登记" name="achievements" lazy>
        <AchievementPanel v-if="project" :project="project" />
      </el-tab-pane>

      <el-tab-pane label="结项报告与验收" name="final">
        <!-- 专家验收进度 -->
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

        <!-- 结项报告 -->
        <el-card shadow="never" class="mb-16">
          <template #header><span class="card-title">结项验收报告</span></template>

          <!-- 可编辑：待结题 + 负责人 + 未提交/已驳回 -->
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

          <!-- 只读：已提交/已结题/非负责人 -->
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

        <!-- 专家验收区：被分配到该项目的专家 / 超级管理员，且报告待验收 -->
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

const route = useRoute()
const processStore = useProcessStore()
const userStore = useUserStore()

const pid = computed(() => Number(route.params.id))
const project = ref<any>(null)
const loading = ref(true)
const finalLoading = ref(false)
const acceptLoading = ref(false)
const archiving = ref(false)
const finalFormRef = ref<FormInstance>()
const finalForm = reactive({ final_report: '' })
const acceptComment = ref('')
const finalAttachmentIds = ref<number[]>([])
const finalRules: FormRules = {
  final_report: [{ required: true, message: '请填写结项验收报告', trigger: 'blur' }],
}

/** 当前 Tab：默认结项报告，支持 ?tab=achievements 直达成果登记 */
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
/** 是否已进入结项验收阶段（待结题8 / 已结题9） */
const isFinalStage = computed(() => [8, 9].includes(Number(project.value?.status)))
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

/** 结项条件检查清单 */
const checklist = computed(() => project.value?.final_checklist || [])
const reviewTotal = computed(() => Number(project.value?.final_review_total || 0))
const reviewDone = computed(() => Number(project.value?.final_review_done || 0))
const reviewPercent = computed(() =>
  reviewTotal.value ? Math.round((reviewDone.value / reviewTotal.value) * 100) : 0
)

/** 结项验收截止日（截止日驱动锁定） */
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
/** 专家验收入口：后端返回可验收 + 本轮未提交意见 + 报告待验收 */
const canAcceptNow = computed(() =>
  !!project.value?.final_can_accept
  && !project.value?.final_reviewed_by_me
  && reportStatus.value === 1
  && project.value?.status === 8
)

function handleFinalFileUpload(file: any) {
  if (file?.id && !finalAttachmentIds.value.includes(file.id)) {
    finalAttachmentIds.value.push(file.id)
  }
}

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
