<!--
  结项验收（独立页面）
  项目处于待结题(8)时，负责人可填写结项验收报告并提交，等待专家验收；
  提交后展示状态，可撤回重新修改提交。
-->
<template>
  <div class="page-container" v-loading="loading">
    <template v-if="project">
      <div class="page-header">
        <div class="header-row">
          <div>
            <h2 class="page-title">结项验收</h2>
          </div>
          <ProjectSwitcher :current-id="pid" suffix="final" />
        </div>
      </div>

      <!-- 截止日提示（截止日驱动锁定） -->
      <el-alert
        v-if="finalDeadlineText"
        :title="finalDeadlineText"
        :type="finalLocked ? 'warning' : 'info'"
        :closable="false"
        class="mb-16"
        show-icon
      />

      <!-- 已提交：展示状态 + 撤回 -->
      <template v-if="finalSubmitted">
        <el-alert
          title="结项验收报告已提交，等待专家验收"
          type="success"
          :closable="false"
          show-icon
          class="mb-16"
        />
        <el-button
          v-if="canWithdrawFinal"
          type="warning"
          :loading="finalLoading"
          @click="handleWithdrawFinal"
        >撤回报告提交</el-button>
      </template>

      <!-- 未提交：填写报告 -->
      <template v-else>
        <el-form ref="finalFormRef" :model="finalForm" :rules="finalRules" label-width="120px" style="max-width: 900px;">
          <el-form-item label="结项报告" prop="final_report">
            <el-input
              v-model="finalForm.final_report"
              type="textarea"
              :rows="8"
              placeholder="请填写项目完成情况、成果总结等结项验收报告内容"
              maxlength="2000"
              show-word-limit
              :disabled="!isLeader"
            />
          </el-form-item>
          <el-form-item v-if="isLeader" label="验收材料">
            <FileUpload
              :accept="['.pdf', '.doc', '.docx', '.zip', '.rar', '.png', '.jpg']"
              :form-data="{ biz_type: 'project', biz_id: 0 }"
              @success="handleFinalFileUpload"
            />
          </el-form-item>
          <el-form-item v-if="isLeader">
            <el-button type="success" :loading="finalLoading" :disabled="finalLocked" @click="handleSubmitFinal">提交结项报告</el-button>
          </el-form-item>
          <el-form-item v-else>
            <el-alert title="仅项目负责人可填写并提交结项验收报告" type="info" :closable="false" show-icon />
          </el-form-item>
        </el-form>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { getProjectDetail, submitFinal, withdrawFinal } from '@/api/project'
import FileUpload from '@/components/FileUpload.vue'
import ProjectSwitcher from '@/components/ProjectSwitcher.vue'
import { useProcessStore } from '@/store/process'
import { useUserStore } from '@/store/user'

const route = useRoute()
const processStore = useProcessStore()
const userStore = useUserStore()

const pid = computed(() => Number(route.params.id))
const project = ref<any>(null)
const loading = ref(true)
const finalLoading = ref(false)
const finalFormRef = ref<FormInstance>()
const finalForm = reactive({ final_report: '' })
const finalAttachmentIds = ref<number[]>([])
const finalRules: FormRules = {
  final_report: [{ required: true, message: '请填写结项验收报告', trigger: 'blur' }],
}

/** 是否为项目负责人（后端 submit 仅允许负责人） */
const isLeader = computed(() =>
  !!project.value && Number(userStore.userInfo?.id) === Number(project.value.leader_id)
)

/** 结项验收报告是否已提交（后端字段：待结题阶段提交报告后为 True） */
const finalSubmitted = computed(() => !!project.value?.final_report_submitted)

/** 结项验收截止日（截止日驱动锁定） */
const finalLocked = computed(() => {
  const d = project.value?.final_deadline
  if (!d) return false
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const t = new Date(`${String(d).slice(0, 10)}T00:00:00`)
  return Math.round((t.getTime() - today.getTime()) / 86400000) < 0
})
/** 撤回结项报告提交：仅项目负责人本人（或超管），报告已提交且未过截止日 */
const canWithdrawFinal = computed(() =>
  finalSubmitted.value && !finalLocked.value && (isLeader.value || userStore.isSuperAdmin)
)
const finalDeadlineText = computed(() => {
  const d = project.value?.final_deadline
  if (!d) return ''
  const ds = String(d).slice(0, 10)
  return finalLocked.value ? `已超过结题截止日（${ds}），无法提交报告` : `结题截止日：${ds}`
})

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
    finalForm.final_report = ''
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

async function loadData() {
  loading.value = true
  try {
    const res = await getProjectDetail(pid.value)
    project.value = res.data
    processStore.setStatus(res.data.status)
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
.page-header { margin-bottom: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.page-title { font-size: 20px; font-weight: 600; margin: 0; white-space: nowrap; }
.mb-16 { margin-bottom: 16px; }
</style>