<!--
  中期检查（独立页面）
  从项目详情页抽离，支持填写/保存/提交中期检查
-->
<template>
  <div class="page-container" v-loading="loading">
    <div class="back-bar">
      <el-button text @click="goBack">
        <el-icon><ArrowLeft /></el-icon> 返回项目详情
      </el-button>
    </div>

    <template v-if="project">
      <div class="page-header">
        <h2 class="page-title">中期检查</h2>
        <div class="page-subtitle">
          {{ project.project_name }}
          <el-tag v-if="midterm.status" :type="statusTagType" size="small" class="ml-8">
            {{ midterm.status_name || '未提交' }}
          </el-tag>
        </div>
      </div>

      <!-- 审核意见（驳回时显示） -->
      <el-alert
        v-if="midterm.status === 4 && midterm.review_comment"
        :title="`审核意见：${midterm.review_comment}`"
        type="error"
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
        <el-form-item label="已用经费">
          <el-input-number v-model="midtermForm.budget_usage" :min="0" :precision="2" :max="project.budget_amount" style="width: 200px" :disabled="isReadonly" />
          <span class="form-tip">总预算 ¥{{ Number(project.budget_amount || 0).toFixed(2) }}</span>
        </el-form-item>
        <el-form-item v-if="!isReadonly">
          <el-button :loading="midtermLoading" @click="handleSave(false)">保存草稿</el-button>
          <el-button type="primary" :loading="midtermLoading" @click="handleSave(true)">提交审核</el-button>
        </el-form-item>
        <el-form-item v-else>
          <el-alert :title="readonlyTip" type="info" :closable="false" show-icon />
        </el-form-item>
      </el-form>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getProjectDetail } from '@/api/project'
import { getMidtermCheck, saveMidtermDraft, submitMidtermCheck } from '@/api/review'
import { useProcessStore } from '@/store/process'

const route = useRoute()
const router = useRouter()
const processStore = useProcessStore()
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
  budget_usage: 0,
})

const statusTagType = computed(() => {
  const s = midterm.value.status
  if (s === 2) return 'success'
  if (s === 4) return 'danger'
  return 'warning'
})

// 审核中(1)或已通过(2)时只读
const isReadonly = computed(() => midterm.value.status === 1 || midterm.value.status === 2)
const readonlyTip = computed(() => {
  if (midterm.value.status === 1) return '中期检查正在审核中，暂不可修改，请等待审核结果'
  if (midterm.value.status === 2) return '中期检查已审核通过，不可再修改'
  return ''
})

function goBack() {
  router.push(`/projects/${pid.value}`)
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
    midterm.value = midRes.data || {}
    if (midRes.data) {
      const md: any = midRes.data
      midtermForm.progress_desc = md.progress_desc || ''
      midtermForm.completed_tasks = md.completed_tasks || ''
      midtermForm.remaining_tasks = md.remaining_tasks || ''
      midtermForm.problems = md.problems || ''
      midtermForm.next_plan = md.next_plan || ''
      midtermForm.budget_usage = md.budget_usage || 0
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleSave(submit: boolean) {
  midtermLoading.value = true
  try {
    const payload = { project_id: pid.value, ...midtermForm }
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
</script>

<style scoped>
.back-bar {
  margin-bottom: 12px;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 6px 0;
}
.page-subtitle {
  color: #909399;
  font-size: 13px;
  display: flex;
  align-items: center;
}
.ml-8 {
  margin-left: 8px;
}
.mb-16 {
  margin-bottom: 16px;
}
.form-tip {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
</style>
