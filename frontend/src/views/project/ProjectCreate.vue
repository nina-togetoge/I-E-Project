<!--
  项目申报页面（学生端）
  分步式表单：基本信息 → 团队成员 → 指导教师 → 立项方案 → 预算编制
  支持草稿保存与正式提交
-->
<template>
  <div class="page-container">
    <ProjectTemplatePicker v-model="showTemplatePicker" @select="handleSelectTemplate" @skip="handleSkipTemplate" />

    <el-card shadow="never">
      <!-- 草稿提示条 -->
      <el-alert
        v-if="(hasDraft || savedAt) && !templateApplied"
        :title="alertTitle"
        type="info"
        :closable="false"
        show-icon
        class="draft-alert"
      >
        <template v-if="hasDraft && !isRestored" #default>
          <span>检测到上次未提交的草稿</span>
          <el-button size="small" type="primary" @click="restoreDraft">恢复草稿</el-button>
          <el-button size="small" type="danger" plain @click="discardDraft">丢弃草稿</el-button>
        </template>
      </el-alert>

      <!-- 步骤条 -->
      <el-steps :active="currentStep" finish-status="success" align-center>
        <el-step title="基本信息" icon="Document" />
        <el-step title="团队成员" icon="User" />
        <el-step title="指导教师" icon="Avatar" />
        <el-step title="立项方案" icon="EditPen" />
        <el-step title="预算编制" icon="Money" />
      </el-steps>

      <!-- Step 1: 基本信息 -->
      <div v-show="currentStep === 0" class="step-content">
        <el-form ref="form1Ref" :model="formData" :rules="form1Rules" label-width="100px" style="max-width: 1000px; margin: 0 auto;">
          <el-form-item label="项目名称" prop="project_name">
            <el-input v-model="formData.project_name" placeholder="请输入项目名称" maxlength="100" show-word-limit />
          </el-form-item>
          <el-form-item label="项目类别" prop="project_type">
            <el-select v-model="formData.project_type" placeholder="请选择类别" style="width: 100%">
              <el-option label="创新训练项目" :value="1" />
              <el-option label="创业训练项目" :value="2" />
              <el-option label="创业实践项目" :value="3" />
            </el-select>
          </el-form-item>
          <el-form-item label="项目级别" prop="project_level">
            <el-select v-model="formData.project_level" placeholder="请选择级别" style="width: 100%">
              <el-option label="院级" :value="1" />
              <el-option label="校级" :value="2" />
              <el-option label="省部级" :value="3" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属学院" prop="college_id">
            <el-select v-model="formData.college_id" filterable placeholder="请选择学院" style="width: 100%">
              <el-option v-for="c in collegeOptions" :key="c.id" :label="c.college_name" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="参赛比赛" prop="competition_id">
            <el-select v-model="formData.competition_id" filterable placeholder="请选择参加的比赛（可选）" clearable style="width: 100%">
              <el-option v-for="c in competitionOptions" :key="c.id" :label="c.title" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="摘要" prop="project_summary">
            <el-input v-model="formData.project_summary" type="textarea" :rows="3" placeholder="200字以内的项目摘要" maxlength="200" show-word-limit />
          </el-form-item>
          <el-form-item label="起止时间" prop="dateRange">
            <el-date-picker
              v-model="formData.dateRange"
              type="daterange"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              :disabled-date="disabledDate"
              style="width: 100%"
            />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 2: 团队成员 -->
      <div v-show="currentStep === 1" class="step-content">
        <div class="step-header">
          <p class="step-desc">添加团队成员，每位成员需填写学号、姓名和分工</p>
          <el-button type="primary" :icon="Plus" @click="addMember">添加成员</el-button>
        </div>
        <el-table :data="formData.teamMembers" border style="width: 100%; max-width: 1000px; margin: 0 auto;">
          <el-table-column type="index" label="序号" width="70" align="center" />
          <el-table-column label="学号" width="150">
            <template #default="{ row, $index }">
              <el-input v-model="row.student_no" placeholder="请输入学号" @blur="searchStudent(row, $index)" />
            </template>
          </el-table-column>
          <el-table-column label="姓名" width="120">
            <template #default="{ row }">
              <el-input v-model="row.student_name" placeholder="请输入姓名" />
            </template>
          </el-table-column>
          <el-table-column label="专业" width="140">
            <template #default="{ row }">
              <el-input v-model="row.major" placeholder="请输入专业" />
            </template>
          </el-table-column>
          <el-table-column label="年级" width="100">
            <template #default="{ row }">
              <el-input v-model="row.grade" placeholder="如:2023级" />
            </template>
          </el-table-column>
          <el-table-column label="团队角色">
            <template #default="{ row }">
              <el-input v-model="row.role_in_team" placeholder="如:技术研发" />
            </template>
          </el-table-column>
          <el-table-column label="任务分工">
            <template #default="{ row }">
              <el-input v-model="row.task_desc" placeholder="具体任务描述" maxlength="255" show-word-limit />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" :icon="Delete" @click="removeMember($index)" />
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- Step 3: 指导教师 -->
      <div v-show="currentStep === 2" class="step-content">
        <el-form label-width="100px" style="max-width: 1000px; margin: 0 auto;">
          <el-form-item label="指导教师">
            <el-select
              v-model="formData.teacher_id"
              filterable
              remote
              :remote-method="searchTeacher"
              :loading="teacherLoading"
              placeholder="输入教师姓名搜索"
              style="width: 100%"
            >
              <el-option
                v-for="t in teacherOptions"
                :key="t.id"
                :label="`${t.real_name}（${t.college_name || ''}）`"
                :value="t.id"
              />
            </el-select>
          </el-form-item>
          <el-alert type="info" :closable="false" show-icon>
            指导教师绑定后需等待教师确认，确认后项目方可提交审核
          </el-alert>
        </el-form>
      </div>

      <!-- Step 4: 立项方案 -->
      <div v-show="currentStep === 3" class="step-content">
        <el-form ref="form2Ref" :model="formData" :rules="form2Rules" label-width="100px" style="max-width: 1000px; margin: 0 auto;">
          <el-form-item label="创新点" prop="innovation_points">
            <RichEditor v-model="formData.innovation_points" min-height="300px" placeholder="请描述项目创新点" />
          </el-form-item>
          <el-form-item label="预期成果" prop="expected_results">
            <RichEditor v-model="formData.expected_results" min-height="250px" placeholder="请描述预期产出成果" />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 5: 预算编制 -->
      <div v-show="currentStep === 4" class="step-content">
        <div class="step-header">
          <p class="step-desc">编制项目预算，各科目金额合计为项目总预算</p>
          <el-button type="primary" :icon="Plus" @click="addBudget">添加科目</el-button>
        </div>
        <el-table :data="formData.budgets" border show-summary :summary-method="getBudgetSummary" style="width: 100%; max-width: 1000px; margin: 0 auto;">
          <el-table-column type="index" label="序号" width="70" align="center" />
          <el-table-column label="预算科目" width="200">
            <template #default="{ row }">
              <el-select v-model="row.budget_item" placeholder="选择科目" style="width: 100%">
                <el-option label="材料费" value="材料费" />
                <el-option label="测试化验加工费" value="测试化验加工费" />
                <el-option label="差旅费" value="差旅费" />
                <el-option label="会议费" value="会议费" />
                <el-option label="出版/文献/信息传播费" value="出版/文献/信息传播费" />
                <el-option label="劳务费" value="劳务费" />
                <el-option label="专家咨询费" value="专家咨询费" />
                <el-option label="其他" value="其他" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="金额(元)" width="150">
            <template #default="{ row }">
              <el-input-number v-model="row.budget_amount" :min="0" :precision="2" controls-position="right" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="备注">
            <template #default="{ row }">
              <el-input v-model="row.remark" placeholder="用途说明" maxlength="255" show-word-limit />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" :icon="Delete" @click="removeBudget($index)" />
            </template>
          </el-table-column>
        </el-table>

        <!-- 附件上传 -->
        <el-form label-width="100px" style="max-width: 1000px; margin: 20px auto 0;">
          <el-form-item label="已有附件" v-if="isEditMode && formData.attachments.length > 0">
            <ProjectAttachmentList :attachments="formData.attachments" />
          </el-form-item>
          <el-form-item label="新增材料">
            <FileUpload
              drag
              :accept="['.pdf', '.doc', '.docx', '.zip', '.rar']"
              :form-data="{ biz_type: 'project', biz_id: 0 }"
              @success="handleFileUpload"
            />
          </el-form-item>
        </el-form>
      </div>

      <!-- 按钮区 -->
      <div class="step-actions">
        <el-button v-if="currentStep > 0" @click="prevStep">上一步</el-button>
        <el-button v-if="currentStep < 4" type="primary" @click="nextStep">下一步</el-button>
        <el-button v-if="currentStep === 4" type="warning" :loading="draftLoading" @click="handleSaveDraft">保存草稿</el-button>
        <el-button v-if="currentStep === 4" type="success" :loading="submitLoading" @click="handleSubmit">正式提交</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import FileUpload from '@/components/FileUpload.vue'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import { createProject, createAndSubmitProject, updateProject, getProjectDetail } from '@/api/project'
import { getUserList } from '@/api/user'
import { getColleges } from '@/api/auth'
import { getCompetitionList } from '@/api/competition'
import { useAutoSaveDraft } from '@/composables/useAutoSaveDraft'
import ProjectTemplatePicker from '@/components/ProjectTemplatePicker.vue'
import RichEditor from '@/components/RichEditor.vue'
import type { ProjectTemplate } from '@/data/projectTemplates'

// 禁用今天之前的日期
const disabledDate = (date: Date) => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date.getTime() < today.getTime()
}

const router = useRouter()
const route = useRoute()
const currentStep = ref(0)
const isEditMode = computed(() => !!route.query.id)
const editingId = computed(() => Number(route.query.id))
const isRestored = ref(false)
const showTemplatePicker = ref(false)
const templateApplied = ref(false)

// ==================== 表单数据 ====================
const formData = reactive({
  project_name: '',
  project_type: undefined as number | undefined,
  project_level: 1 as number,
  college_id: undefined as number | undefined,
  competition_id: undefined as number | undefined,
  project_summary: '',
  innovation_points: '',
  expected_results: '',
  dateRange: [] as string[],
  teamMembers: [] as {
    student_id: number
    student_no: string
    student_name: string
    major?: string
    grade?: string
    role_in_team?: string
    task_desc?: string
  }[],
  teacher_id: undefined as number | undefined,
  budgets: [] as { budget_item: string; budget_amount: number; remark?: string }[],
  attachments: [] as any[],
})

// ==================== 自动保存草稿 ====================
const draftKey = computed(() => (isEditMode.value ? `edit_${editingId.value}` : 'create'))
const { savedAt, saveDraft, loadDraft, clearDraft, hasDraft } = useAutoSaveDraft(draftKey.value, formData, 30000)

const alertTitle = computed(() => {
  if (savedAt.value) {
    const d = new Date(savedAt.value)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `草稿已自动保存于 ${hh}:${mm}:${ss}`
  }
  return ''
})

function restoreDraft() {
  const draft = loadDraft()
  if (draft) {
    Object.assign(formData, draft)
    isRestored.value = true
    ElMessage.success('已恢复上次草稿')
  }
}

function discardDraft() {
  clearDraft()
  isRestored.value = true
  ElMessage.info('已丢弃草稿')
}

// ==================== Step 1 表单校验 ====================
const form1Ref = ref<FormInstance>()
const form1Rules: FormRules = {
  project_name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  project_type: [{ required: true, message: '请选择项目类别', trigger: 'change' }],
  project_level: [{ required: true, message: '请选择项目级别', trigger: 'change' }],
  college_id: [{ required: true, message: '请选择所属学院', trigger: 'change' }],
  project_summary: [{ required: true, message: '请输入项目摘要', trigger: 'blur' }],
  dateRange: [{ required: true, message: '请选择起止时间', trigger: 'change' }],
}

// ==================== Step 3 表单校验 ====================
const form2Ref = ref<FormInstance>()
const form2Rules: FormRules = {
  innovation_points: [{ required: true, message: '请输入创新点', trigger: 'blur' }],
  expected_results: [{ required: true, message: '请输入预期成果', trigger: 'blur' }],
}

// ==================== 步骤导航 ====================
async function nextStep() {
  if (currentStep.value === 0) {
    if (!form1Ref.value) return
    await form1Ref.value.validate((valid) => {
      if (valid) currentStep.value++
    })
    return
  }
  if (currentStep.value === 3) {
    if (!form2Ref.value) return
    await form2Ref.value.validate((valid) => {
      if (valid) currentStep.value++
    })
    return
  }
  // 步骤 2：团队成员至少 1 人
  if (currentStep.value === 1) {
    if (formData.teamMembers.length === 0) {
      ElMessage.warning('请至少添加一名团队成员')
      return
    }
  }
  // 步骤 3：必须选择指导教师
  if (currentStep.value === 2) {
    if (!formData.teacher_id) {
      ElMessage.warning('请选择指导教师')
      return
    }
  }
  currentStep.value++
}

function prevStep() {
  if (currentStep.value > 0) currentStep.value--
}

// ==================== 团队成员 ====================
function addMember() {
  formData.teamMembers.push({
    student_id: 0,
    student_no: '',
    student_name: '',
    major: '',
    grade: '',
    role_in_team: '',
    task_desc: '',
  })
}

function removeMember(index: number) {
  formData.teamMembers.splice(index, 1)
}

/** 根据学号搜索学生并自动填充信息 */
async function searchStudent(row: any, _index: number) {
  const no = row.student_no?.trim()
  if (!no || no.length < 3) {
    row.student_id = 0
    row.student_name = ''
    row.major = ''
    return
  }
  try {
    const res: any = await getUserList({ keyword: no, role: 1, page: 1, page_size: 10 })
    const items = res.data?.items || []
    if (items.length === 1) {
      const s = items[0]
      row.student_id = s.id
      row.student_name = s.real_name || s.username
      row.major = s.college_name || ''
      ElMessage.success(`已自动填充：${row.student_name}`)
    } else if (items.length > 1) {
      ElMessage.warning(`找到 ${items.length} 个匹配学生，请精确输入学号`)
    } else {
      ElMessage.warning('未找到该学号的学生，请手动填写')
      row.student_id = 0
    }
  } catch (_) {
    ElMessage.error('学生搜索失败，请手动填写')
  }
}

// ==================== 指导教师 ====================
const teacherOptions = ref<any[]>([])
const teacherLoading = ref(false)

function handleSelectTemplate(tpl: ProjectTemplate) {
  formData.project_type = tpl.category
  formData.project_level = tpl.level
  formData.project_summary = tpl.summary
  formData.innovation_points = tpl.innovation_points
  formData.expected_results = tpl.expected_results
  formData.budgets = tpl.budgets.map((b) => ({ ...b }))
  templateApplied.value = true
  ElMessage.success(`已应用模板：${tpl.name}`)
}

function handleSkipTemplate() {
  templateApplied.value = true
}

// 学院下拉选项
const collegeOptions = ref<any[]>([])
// 比赛下拉选项
const competitionOptions = ref<any[]>([])
onMounted(async () => {
  // 新建模式下立即弹出模板选择对话框，避免等待接口时页面空白
  if (!isEditMode.value) {
    showTemplatePicker.value = true
  }

  try {
    const res = await getColleges()
    collegeOptions.value = res.data || []
  } catch (_) {}
  // 加载可报名的比赛（状态为报名中/进行中）
  try {
    const compRes = await getCompetitionList({ page: 1, page_size: 100 })
    competitionOptions.value = (compRes.data.items || []).filter((c: any) => [1, 2].includes(c.status))
  } catch (_) {}

  if (isEditMode.value) {
    templateApplied.value = true
    try {
      const detail = await getProjectDetail(editingId.value)
      const p = detail.data
      formData.project_name = p.project_name || ''
      formData.project_type = p.project_type
      formData.project_level = p.project_level || 1
      formData.college_id = p.college_id
      formData.competition_id = p.competition_id ?? undefined
      formData.project_summary = p.project_summary || ''
      formData.innovation_points = p.innovation_points || ''
      formData.expected_results = p.expected_results || ''
      if (p.start_date && p.end_date) {
        formData.dateRange = [p.start_date, p.end_date]
      }
      formData.teamMembers = (p.team_members || []).map((m: any) => ({
        student_id: m.student_id || 0,
        student_no: m.student_no || '',
        student_name: m.student_name || '',
        major: m.major || '',
        grade: m.grade || '',
        role_in_team: m.role_in_team || m.role || '',
        task_desc: m.task_desc || '',
      }))
      formData.teacher_id = p.teacher_id ?? undefined
      formData.budgets = (p.budgets || []).map((b: any) => ({
        budget_item: b.budget_item || b.subject || '',
        budget_amount: b.budget_amount || b.amount || 0,
        remark: b.remark || '',
      }))
      formData.attachments = p.attachments || []
    } catch (e) {
      ElMessage.error('加载项目数据失败')
    }
  }
})

async function searchTeacher(query: string) {
  if (!query) {
    teacherOptions.value = []
    return
  }
  teacherLoading.value = true
  try {
    const res: any = await getUserList({ keyword: query, role: 2, page: 1, page_size: 20 })
    teacherOptions.value = res.data?.items || []
  } catch (_) {
    ElMessage.error('教师搜索失败')
  } finally {
    teacherLoading.value = false
  }
}

// ==================== 预算 ====================
function addBudget() {
  formData.budgets.push({ budget_item: '', budget_amount: 0, remark: '' })
}

function removeBudget(index: number) {
  formData.budgets.splice(index, 1)
}

function getBudgetSummary({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col, index) => {
    if (index === 0) {
      sums[index] = '合计'
    } else if (col.property === 'budget_amount' || index === 2) {
      const total = data.reduce((sum, item) => sum + Number(item.budget_amount || 0), 0)
      sums[index] = `¥ ${total.toFixed(2)}`
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// ==================== 附件上传 ====================
function handleFileUpload(file: any) {
  formData.attachments.push(file)
}

// ==================== 保存/提交 ====================
const draftLoading = ref(false)
const submitLoading = ref(false)

function buildPayload() {
  return {
    project_name: formData.project_name,
    project_type: formData.project_type,
    project_level: formData.project_level,
    college_id: formData.college_id,
    competition_id: formData.competition_id || null,
    project_summary: formData.project_summary,
    innovation_points: formData.innovation_points,
    expected_results: formData.expected_results,
    start_date: formData.dateRange[0],
    end_date: formData.dateRange[1],
    team_members: formData.teamMembers,
    teacher_id: formData.teacher_id,
    budgets: formData.budgets,
    attachment_ids: formData.attachments.map((a: any) => a.id),
  }
}

async function handleSaveDraft() {
  draftLoading.value = true
  try {
    if (isEditMode.value) {
      await updateProject(editingId.value, buildPayload())
    } else {
      await createProject(buildPayload())
    }
    saveDraft()
    clearDraft()
    ElMessage.success('草稿保存成功')
    router.push('/projects')
  } finally {
    draftLoading.value = false
  }
}

async function handleSubmit() {
  if (formData.budgets.length === 0) {
    ElMessage.warning('请至少添加一项预算')
    return
  }
  if (!formData.teacher_id) {
    ElMessage.warning('请选择指导教师')
    return
  }
  if (formData.teamMembers.length === 0) {
    ElMessage.warning('请至少添加一名团队成员')
    return
  }

  const invalidMember = formData.teamMembers.find(m => !m.student_id)
  if (invalidMember) {
    ElMessage.warning(`团队成员 "${invalidMember.student_no || ''}" 未关联到有效学生，请检查学号`)
    return
  }

  submitLoading.value = true
  try {
    if (isEditMode.value) {
      await updateProject(editingId.value, buildPayload())
      const { submitProject } = await import('@/api/project')
      await submitProject(editingId.value)
    } else {
      await createAndSubmitProject(buildPayload())
    }
    clearDraft()
    ElMessage.success('项目已提交，等待审核')
    router.push('/projects')
  } finally {
    submitLoading.value = false
  }
}
</script>

<style scoped>
.draft-alert {
  margin-bottom: 20px;
}

.draft-alert :deep(.el-alert__description) {
  display: flex;
  align-items: center;
  gap: 10px;
}

.step-content {
  padding: 30px 0;
  min-height: 300px;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1000px;
  margin: 0 auto 20px;
}

.step-desc {
  color: #909399;
  font-size: 14px;
}

.step-actions {
  text-align: center;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}
</style>
