<!--
  页面名称：中期检查（独立页面）
  面向角色：项目负责人（填写 / 保存 / 提交 / 撤回）、该项目指导教师与超管（审核）
  核心功能：展示项目进展、完成任务、剩余任务、问题与下一步计划，上传中期报告附件，
           保存草稿、提交审核、教师审核通过 / 驳回，以及通过后的成果 / 结项快捷入口。
  调用 API：getProjectDetail、getMidtermCheck、saveMidtermDraft、submitMidtermCheck、
           reviewMidtermCheck、withdrawMidtermCheck、deleteAttachment。
  权限 / 状态约束：
    - 仅已立项(6) / 中期检查中(7)可填写，且仅项目负责人本人可保存与提交。
    - 审核中(1)、已通过(2)、已作废(5) 一律只读；非负责人同样只读。
    - 审核：仅待审核(1) + 该项目指导教师本人或超管，与后端 MidtermService.review 一致。
    - 撤回提交：待审核(1) + 未过截止日 + 负责人或超管。
    - 截止日过期后仍可保存草稿，但不可提交审核。
  关键交互：
    - 已用经费来自项目经费报销汇总，提交时强制覆盖表单值，避免手工填写与账目不一致。
    - 新增附件先记 id 暂存，保存 / 提交时随 attachment_ids 一起绑定。
    - 审核意见必填；通过后展示「去登记成果 / 去结项验收」下一步入口。
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
    <!-- 审核意见：退回修改(3) 用 warning、驳回(4) 用 error，直接把教师意见展示给负责人 -->
    <el-alert
      v-if="(midterm.status === 3 || midterm.status === 4) && midterm.review_comment"
      :title="`${midterm.status === 3 ? '退回修改意见' : '审核意见'}：${midterm.review_comment}`"
      :type="midterm.status === 3 ? 'warning' : 'error'"
      :closable="false"
      class="mb-16"
      show-icon
    />

    <!-- 截止日提示：由后端回填 midterm_deadline 驱动；过期后仅锁定「提交审核」，草稿保存不受影响 -->
    <el-alert
      v-if="midtermDeadlineTip"
      :title="midtermDeadlineTip"
      :type="midtermLocked ? 'warning' : 'info'"
      :closable="false"
      class="mb-16"
      show-icon
    />

    <!-- 中期报告表单：全部字段在只读态下禁用；只读原因由 readonlyTip 给出 -->
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
        <!-- 附件：已有附件需二次确认后删除；新上传附件直接移除；只读态不展示上传入口 -->
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
        <!-- 经费只展示不编辑：由报销流水汇总，避免与财务数据不一致 -->
        <span class="budget-value">¥{{ usedAmount.toFixed(2) }}</span>
        <span class="form-tip">
          由项目经费报销自动汇总 · 总预算 ¥{{ Number(project.budget_amount || 0).toFixed(2) }} ·
          剩余 ¥{{ (Number(project.budget_amount || 0) - usedAmount).toFixed(2) }}
        </span>
      </el-form-item>
      <el-form-item v-if="!isReadonly">
        <!-- 保存草稿不受截止日限制；提交审核在过截止日后禁用 -->
        <el-button :loading="midtermLoading" @click="handleSave(false)">保存草稿</el-button>
        <el-button type="primary" :loading="midtermLoading" :disabled="midtermLocked" @click="handleSave(true)">提交审核</el-button>
      </el-form-item>
      <el-form-item v-else-if="!canReviewMidterm">
        <!-- 只读态给出具体原因；待审核且未过截止日时，负责人 / 超管可撤回后重新编辑 -->
        <el-alert :title="readonlyTip" type="info" :closable="false" show-icon />
        <el-button
          v-if="canWithdrawMidterm"
          type="warning"
          :loading="midtermLoading"
          class="withdraw-btn"
          @click="handleWithdrawMidterm"
        >撤回提交</el-button>
      </el-form-item>

      <!-- 审核区：仅该项目指导教师本人 / 超管，且中期检查待审核(1) 时展示；
           驳回必须填写意见，通过后由后端推进项目状态 -->
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

    <!-- 中期通过后的下一步：登记成果与结项验收均要求项目已进入对应阶段，
         页面内只做跳转，具体权限由目标页再校验 -->
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

// ==================== 路由 / Store / 项目标识 ====================
// 中期检查按项目 ID 独立成页；project 提供状态、截止日、预算与负责人信息。
const route = useRoute()
const router = useRouter()
const processStore = useProcessStore()
const userStore = useUserStore()
const pid = computed(() => Number(route.params.id))

/** 项目详情：驱动阶段判断、预算展示与权限判定 */
const project = ref<any>(null)
/** 当前中期检查记录；为空对象表示尚未创建 */
const midterm = ref<any>({})
/** 页面首屏加载态 */
const loading = ref(true)
/** 保存 / 提交 / 撤回 / 审核共用的按钮 loading */
const midtermLoading = ref(false)
/** 中期报告表单；budget_usage 仅保留字段，提交时会被自动汇总值覆盖 */
const midtermForm = reactive({
  progress_desc: '',
  completed_tasks: '',
  remaining_tasks: '',
  problems: '',
  next_plan: '',
  report: '',
  budget_usage: 0,
})
/** 本次新上传附件的 id 集合，保存 / 提交时作为 attachment_ids 下发 */
const midtermAttachmentIds = ref<number[]>([])
/** 已保存的中期报告附件（后端返回，用于回显） */
const midtermAttachments = ref<any[]>([])
/** 本次新上传、尚未保存的附件 */
const newMidtermAttachments = ref<any[]>([])
/** 展示用附件 = 已保存 + 本次新增，删除时需同时清理两处 */
const displayAttachments = computed(() => [...midtermAttachments.value, ...newMidtermAttachments.value])

/** 状态标签颜色：通过成功、驳回危险、草稿灰色，其余（待审核 / 退回）用警告色 */
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

// 审核中(1)/已通过(2)/已作废(5)、未进入中期阶段、或非项目负责人时只读；
// 这里同时覆盖「管理员 / 教师查看非本人项目」的情况，避免出现可编辑但保存失败的按钮
const isReadonly = computed(() =>
  !midtermStage.value || [1, 2, 5].includes(midterm.value.status) || !isLeader.value
)

/** 跳转到成果登记 / 结项验收 */
function goNext(suffix: 'achievements' | 'final') {
  router.push(`/projects/${pid.value}/${suffix}`)
}
/** 只读原因文案：按状态优先级给出最贴近当前处境的提示，便于用户知道下一步该做什么 */
const readonlyTip = computed(() => {
  if (midterm.value.status === 1) return '中期检查正在审核中，暂不可修改，请等待审核结果'
  if (midterm.value.status === 2) return '中期检查已审核通过，不可再修改'
  if (!midtermStage.value) return '项目尚未进入中期检查阶段，待项目立项后可填写并提交中期报告'
  if (!isLeader.value) return '仅项目负责人可填写并提交中期检查'
  return ''
})

// 中期报告提交截止日（截止日驱动锁定）：过截止日不可提交审核（草稿保存不受限）；
// 只比较到日期，避免用户当天提交时因时分秒被误判为过期
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
/** 审核意见输入；驳回时必填，通过时选填 */
const reviewComment = ref('')
/** 审核按钮 loading，防止重复提交 */
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

/**
 * 撤回已提交的中期报告：退回草稿态并保留原内容，可修改后重新提交。
 * 失败处理：取消确认直接返回；接口异常由全局拦截器提示，结束后刷新页面数据。
 */
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

/**
 * 教师审核中期检查。
 * 参数 result：1 通过、2 驳回。
 * 说明：审核意见必填，驳回时用于指导负责人修改；通过后后端会推进项目阶段。
 * 失败处理：意见为空仅提示不请求；接口异常由全局拦截器提示。
 */
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

/**
 * 并行加载项目详情与中期检查记录，并回填表单。
 * 说明：中期记录可能尚不存在，接口失败按空对象降级，不影响页面展示与首次填写。
 * 失败处理：详情失败提示「加载失败」；finally 复位 loading。
 */
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

/**
 * 新附件上传成功：记录 id 并补充预览 / 下载地址与上传人。
 * 参数 file：FileUpload 返回的文件对象。
 * 说明：同一文件重复回调会被 id 去重，避免 attachment_ids 重复下发。
 */
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

/**
 * 删除报告附件。
 * 参数 att：附件对象。
 * 说明：已保存附件需二次确认并调用后端删除；本次新上传附件直接本地移除即可。
 * 失败处理：取消确认直接返回；接口异常由全局拦截器提示。
 */
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

/**
 * 保存 / 提交中期检查。
 * 参数 submit：true 提交审核，false 仅保存草稿。
 * 说明：budget_usage 强制使用报销汇总值，忽略表单中的历史值；
 * 附件只下发本次新增的 id，已保存附件由后端保持绑定。
 * 失败处理：接口异常由全局拦截器提示，finally 复位 loading 并刷新数据。
 */
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
