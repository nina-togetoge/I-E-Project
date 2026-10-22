<!--
  中期检查（独立页面）
  从项目详情页抽离，支持填写/保存/提交中期检查
-->
<template>
  <StagePageShell
    :project="project"
    title="中期检查"
    current="midterm"
    :loading="loading"
    :status-text="midterm.id ? (midterm.status_name || '草稿') : ''"
    :status-type="statusTagType"
  >
    <!-- 审核意见（退回修改 / 驳回时显示） -->
    <el-alert
      v-if="(midterm.status === 3 || midterm.status === 4) && midterm.review_comment"
      :title="`${midterm.status === 3 ? '退回修改意见' : '审核意见'}：${midterm.review_comment}`"
      :type="midterm.status === 3 ? 'warning' : 'error'"
      :closable="false"
      class="mb-16"
      show-icon
    />

    <!-- 中期报告提交截止日提示（截止日驱动锁定） -->
    <el-alert
      v-if="midtermDeadlineTip"
      :title="midtermDeadlineTip"
      :type="midtermLocked ? 'warning' : 'info'"
      :closable="false"
      class="mb-16"
      show-icon
    />

    <el-form :model="midtermForm" label-width="100px" style="max-width: 1000px; margin: 0 auto;">
      <el-form-item label="当前进展">
        <el-input v-model="midtermForm.progress_desc" type="textarea" :rows="3" placeholder="项目当前进展情况" :disabled="isReadonly" />
      </el-form-item>
      <el-form-item label="已完成任务">
        <el-input v-model="midtermForm.completed_tasks" type="textarea" :rows="3" placeholder="已完成的主要任务" :disabled="isReadonly" />
      </el-form-item>
      <el-form-item label="剩余任务">
        <el-input v-model="midtermForm.remaining_tasks" type="textarea" :rows="3" placeholder="剩余任务计划" :disabled="isReadonly" />
      </el-form-item>
      <el-form-item label="存在问题">
        <el-input v-model="midtermForm.problems" type="textarea" :rows="2" placeholder="遇到的问题" :disabled="isReadonly" />
      </el-form-item>
      <el-form-item label="下一步计划">
        <el-input v-model="midtermForm.next_plan" type="textarea" :rows="2" placeholder="下一步工作计划" :disabled="isReadonly" />
      </el-form-item>
      <el-form-item label="中期报告">
        <el-input v-model="midtermForm.report" type="textarea" :rows="6" placeholder="请填写中期报告内容" maxlength="10000" show-word-limit :disabled="isReadonly" />
      </el-form-item>
      <el-form-item label="报告附件">
        <div class="attachment-block">
          <ProjectAttachmentList
            v-if="displayAttachments.length"
            :attachments="displayAttachments"
            :deletable="!isReadonly"
            @remove="handleRemoveAttachment"
          />
          <FileUpload
            v-if="!isReadonly"
            :accept="['.pdf', '.doc', '.docx', '.zip', '.rar', '.png', '.jpg']"
            :form-data="{ biz_type: 'midterm', biz_id: 0 }"
            @success="handleMidtermFileUpload"
          />
        </div>
      </el-form-item>
      <el-form-item label="已用经费">
        <span class="budget-value">¥{{ usedAmount.toFixed(2) }}</span>
        <span class="form-tip">
          由项目经费报销自动汇总 · 总预算 ¥{{ Number(project.budget_amount || 0).toFixed(2) }} ·
          剩余 ¥{{ (Number(project.budget_amount || 0) - usedAmount).toFixed(2) }}
        </span>
      </el-form-item>
      <el-form-item v-if="!isReadonly">
        <el-button :loading="midtermLoading" @click="handleSave(false)">保存草稿</el-button>
        <el-button type="primary" :loading="midtermLoading" :disabled="midtermLocked" @click="handleSave(true)">提交审核</el-button>
      </el-form-item>
      <el-form-item v-else-if="!canReviewMidterm">
        <el-alert :title="readonlyTip" type="info" :closable="false" show-icon />
        <el-button
          v-if="canWithdrawMidterm"
          type="warning"
          :loading="midtermLoading"
          class="withdraw-btn"
          @click="handleWithdrawMidterm"
        >撤回提交</el-button>
      </el-form-item>

      <!-- 审核区：仅该项目的指导教师本人 / 超级管理员，且中期检查处于待审核(1)时显示 -->
      <template v-if="canReviewMidterm">
        <el-form-item label="审核意见">
          <el-input
            v-model="reviewComment"
            type="textarea"
            :rows="3"
            placeholder="请填写审核意见（驳回时请说明原因）"
            maxlength="1000"
            show-word-limit
          />
        </el-form-item>
        <el-form-item>
          <el-button type="success" :loading="reviewLoading" @click="handleReview(1)">通过</el-button>
          <el-button type="danger" :loading="reviewLoading" @click="handleReview(2)">驳回</el-button>
        </el-form-item>
      </template>
    </el-form>

    <!-- 中期通过后的下一步 -->
    <el-card v-if="midterm.status === 2" shadow="never" class="next-step">
      <div class="next-step-title">中期检查已通过，可继续办理：</div>
      <el-button type="primary" @click="goNext('achievements')">去登记成果</el-button>
      <el-button type="success" @click="goNext('final')">去结项验收</el-button>
    </el-card>
  </StagePageShell>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getProjectDetail } from '@/api/project'
import { getMidtermCheck, saveMidtermDraft, submitMidtermCheck, reviewMidtermCheck, withdrawMidtermCheck } from '@/api/review'
import { deleteAttachment } from '@/api/common'
import FileUpload from '@/components/FileUpload.vue'
import StagePageShell from '@/components/StagePageShell.vue'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import { useProcessStore } from '@/store/process'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const processStore = useProcessStore()
const userStore = useUserStore()
const pid = computed(() => Number(route.params.id))

const project = ref<any>(null)
const midterm = ref<any>({})
const loading = ref(true)
const midtermLoading = ref(false)
const midtermForm = reactive({
  progress_desc: '',
  completed_tasks: '',
  remaining_tasks: '',
  problems: '',
  next_plan: '',
  report: '',
  budget_usage: 0,
})
const midtermAttachmentIds = ref<number[]>([])
/** 已保存的中期报告附件（后端返回，用于回显） */
const midtermAttachments = ref<any[]>([])
/** 本次新上传、尚未保存的附件 */
const newMidtermAttachments = ref<any[]>([])
const displayAttachments = computed(() => [...midtermAttachments.value, ...newMidtermAttachments.value])

const statusTagType = computed<'primary' | 'success' | 'info' | 'warning' | 'danger'>(() => {
  const s = midterm.value.status
  if (s === 2) return 'success'
  if (s === 4) return 'danger'
  if (s === 0) return 'info'
  return 'warning'
})

/** 仅已立项(6)/中期检查中(7)可填写提交中期检查（与后端校验一致） */
const midtermStage = computed(() => [6, 7].includes(Number(project.value?.status)))

/** 当前用户是否为项目负责人（后端 save/submit 仅允许负责人） */
const isLeader = computed(() => !!project.value && Number(project.value.leader_id) === Number(userStore.userInfo?.id))

/** 已用经费：由项目经费报销自动汇总（不再手工填写） */
const usedAmount = computed(() => Number(project.value?.used_amount || 0))

// 审核中(1)/已通过(2)/已作废(5)、未进入中期阶段、或非项目负责人时只读
const isReadonly = computed(() =>
  !midtermStage.value || [1, 2, 5].includes(midterm.value.status) || !isLeader.value
)

/** 跳转到成果登记 / 结项验收 */
function goNext(suffix: 'achievements' | 'final') {
  router.push(`/projects/${pid.value}/${suffix}`)
}
const readonlyTip = computed(() => {
  if (midterm.value.status === 1) return '中期检查正在审核中，暂不可修改，请等待审核结果'
  if (midterm.value.status === 2) return '中期检查已审核通过，不可再修改'
  if (!midtermStage.value) return '项目尚未进入中期检查阶段，待项目立项后可填写并提交中期报告'
  if (!isLeader.value) return '仅项目负责人可填写并提交中期检查'
  return ''
})

// 中期报告提交截止日（截止日驱动锁定）：过截止日不可提交审核（草稿保存不受限）
const midtermDeadline = computed(() => project.value?.midterm_deadline as string | null | undefined)
const midtermLocked = computed(() => {
  const d = midtermDeadline.value
  if (!d) return false
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const t = new Date(`${String(d).slice(0, 10)}T00:00:00`)
  return Math.round((t.getTime() - today.getTime()) / 86400000) < 0
})
const midtermDeadlineTip = computed(() => {
  const d = midtermDeadline.value
  if (!d) return ''
  const ds = String(d).slice(0, 10)
  return midtermLocked.value ? `已超过中期报告提交截止日（${ds}），无法提交审核` : `中期报告提交截止日：${ds}`
})

// ==================== 中期检查审核（指导教师 / 超级管理员） ====================
const reviewComment = ref('')
const reviewLoading = ref(false)
/** 仅待审核(1) 且当前用户为该项目指导教师本人或超管时可审核（与后端 MidtermService.review 一致） */
const canReviewMidterm = computed(() => {
  if (midterm.value.status !== 1 || !project.value) return false
  if (userStore.isSuperAdmin) return true
  return userStore.isTeacher && Number(project.value.teacher_id) === Number(userStore.userInfo?.id)
})

/** 「撤回提交」仅对项目负责人本人（或超管）开放，中期检查待审核(1) 且未过截止日 */
const canWithdrawMidterm = computed(() => {
  if (midterm.value.status !== 1 || !project.value || midtermLocked.value) return false
  return isLeader.value || userStore.isSuperAdmin
})

async function handleWithdrawMidterm() {
  try {
    await ElMessageBox.confirm(
      '撤回后本次提交将退回草稿，项目仍处于中期检查中，可修改后重新提交。确定撤回？',
      '撤回提交',
      { type: 'warning', confirmButtonText: '确定撤回', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  midtermLoading.value = true
  try {
    await withdrawMidtermCheck(midterm.value.id)
    ElMessage.success('已撤回提交，可修改后重新提交')
    loadData()
  } finally {
    midtermLoading.value = false
  }
}

async function handleReview(result: number) {
  if (!reviewComment.value.trim()) {
    ElMessage.warning('请填写审核意见')
    return
  }
  reviewLoading.value = true
  try {
    await reviewMidtermCheck({
      check_id: midterm.value.id,
      result,
      review_comment: reviewComment.value.trim(),
    })
    ElMessage.success(result === 1 ? '中期检查已通过' : '审核已完成')
    reviewComment.value = ''
    loadData()
  } finally {
    reviewLoading.value = false
  }
}

async function loadData() {
  loading.value = true
  try {
    const [detailRes, midRes] = await Promise.all([
      getProjectDetail(pid.value),
      getMidtermCheck(pid.value).catch(() => ({ data: {} })),
    ])
    project.value = detailRes.data
    processStore.setStatus(detailRes.data.status)
    const md: any = midRes.data || {}
    midterm.value = md
    midtermAttachments.value = md.attachments || []
    newMidtermAttachments.value = []
    midtermAttachmentIds.value = []
    if (midRes.data) {
      midtermForm.progress_desc = md.progress_desc || ''
      midtermForm.completed_tasks = md.completed_tasks || ''
      midtermForm.remaining_tasks = md.remaining_tasks || ''
      midtermForm.problems = md.problems || ''
      midtermForm.next_plan = md.next_plan || ''
      midtermForm.report = md.report || ''
      midtermForm.budget_usage = md.budget_usage || 0
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function handleMidtermFileUpload(file: any) {
  if (file?.id && !midtermAttachmentIds.value.includes(file.id)) {
    midtermAttachmentIds.value.push(file.id)
    newMidtermAttachments.value.push({
      ...file,
      uploader_name: userStore.userInfo?.real_name || '本人',
      download_url: file.file_url,
      preview_url: `/api/files/preview/${file.id}`,
    })
  }
}

async function handleRemoveAttachment(att: any) {
  const isNew = newMidtermAttachments.value.some((a) => a.id === att.id)
  if (!isNew) {
    try {
      await ElMessageBox.confirm(`确定删除报告附件「${att.file_name}」？`, '提示', { type: 'warning' })
    } catch {
      return
    }
  }
  await deleteAttachment(att.id)
  midtermAttachments.value = midtermAttachments.value.filter((a) => a.id !== att.id)
  newMidtermAttachments.value = newMidtermAttachments.value.filter((a) => a.id !== att.id)
  midtermAttachmentIds.value = midtermAttachmentIds.value.filter((id) => id !== att.id)
}

async function handleSave(submit: boolean) {
  midtermLoading.value = true
  try {
    // 已用经费以项目经费报销汇总为准，避免手工填写与账目不一致
    const payload = {
      project_id: pid.value,
      ...midtermForm,
      budget_usage: usedAmount.value,
      attachment_ids: midtermAttachmentIds.value,
    }
    if (submit) {
      await submitMidtermCheck(payload)
      ElMessage.success('中期检查已提交审核')
    } else {
      await saveMidtermDraft(payload)
      ElMessage.success('草稿已保存')
    }
    loadData()
  } finally {
    midtermLoading.value = false
  }
}

onMounted(() => loadData())
onBeforeUnmount(() => processStore.reset())
</script>

<style scoped>
.mb-16 {
  margin-bottom: 16px;
}
.form-tip {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
.withdraw-btn {
  margin-top: 12px;
}
.budget-value {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.next-step {
  max-width: 1000px;
  margin: 16px auto 0;
}
.next-step-title {
  font-weight: 600;
  margin-bottom: 12px;
}
.attachment-block {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
