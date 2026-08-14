<!--
  项目申报页面（学生端）
  分步式表单：基本信息 → 团队成员 → 指导教师 → 立项方案 → 预算编制
  支持草稿保存与正式提交
-->
<template>
  <div class="page-container">
    <el-card shadow="never">
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
        <el-form ref="form1Ref" :model="formData" :rules="form1Rules" label-width="100px" style="max-width: 700px; margin: 0 auto;">
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
        <el-table :data="formData.teamMembers" border style="width: 100%; max-width: 700px; margin: 0 auto;">
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
              <el-input v-model="row.task_desc" placeholder="具体任务描述" />
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
        <el-form label-width="100px" style="max-width: 700px; margin: 0 auto;">
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
        <el-form ref="form2Ref" :model="formData" :rules="form2Rules" label-width="100px" style="max-width: 700px; margin: 0 auto;">
          <el-form-item label="创新点" prop="innovation_points">
            <el-input v-model="formData.innovation_points" type="textarea" :rows="4" placeholder="描述项目创新点" />
          </el-form-item>
          <el-form-item label="预期成果" prop="expected_results">
            <el-input v-model="formData.expected_results" type="textarea" :rows="4" placeholder="预期产出成果" />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 5: 预算编制 -->
      <div v-show="currentStep === 4" class="step-content">
        <div class="step-header">
          <p class="step-desc">编制项目预算，各科目金额合计为项目总预算</p>
          <el-button type="primary" :icon="Plus" @click="addBudget">添加科目</el-button>
        </div>
        <el-table :data="formData.budgets" border show-summary :summary-method="getBudgetSummary" style="width: 100%; max-width: 700px; margin: 0 auto;">
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
              <el-input v-model="row.remark" placeholder="用途说明" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" :icon="Delete" @click="removeBudget($index)" />
            </template>
          </el-table-column>
        </el-table>

        <!-- 附件上传 -->
        <el-form label-width="100px" style="max-width: 700px; margin: 20px auto 0;">
          <el-form-item label="申报材料">
            <FileUpload drag :accept="['.pdf', '.doc', '.docx', '.zip', '.rar']" @success="handleFileUpload" />
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
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import FileUpload from '@/components/FileUpload.vue'
import { createProject, createAndSubmitProject } from '@/api/project'
import { getUserList } from '@/api/user'
import { getColleges } from '@/api/auth'

const router = useRouter()
const currentStep = ref(0)

// ==================== 表单数据 ====================
const formData = reactive({
  project_name: '',
  project_type: undefined as number | undefined,
  project_level: 1 as number,
  college_id: undefined as number | undefined,
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
  // 步骤 2 直接前进
  if (currentStep.value === 1) {
    if (formData.teamMembers.length === 0) {
      ElMessage.warning('请至少添加一名团队成员')
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

// 学院下拉选项（实际环境中从后端加载）
const collegeOptions = ref<any[]>([])
onMounted(async () => {
  try {
    const res = await getColleges()
    collegeOptions.value = res.data || []
  } catch (_) {}
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
      const total = data.reduce((sum, item) => sum + (item.budget_amount || 0), 0)
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
    project_summary: formData.project_summary,
    innovation_points: formData.innovation_points,
    expected_results: formData.expected_results,
    start_date: formData.dateRange[0],
    end_date: formData.dateRange[1],
    team_members: formData.teamMembers,
    teacher_id: formData.teacher_id,
    budgets: formData.budgets,
  }
}

async function handleSaveDraft() {
  draftLoading.value = true
  try {
    const res = await createProject(buildPayload())
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

  // 检查团队成员是否都已通过学号搜索关联到学生
  const invalidMember = formData.teamMembers.find(m => !m.student_id)
  if (invalidMember) {
    ElMessage.warning(`团队成员 "${invalidMember.student_no || ''}" 未关联到有效学生，请检查学号`)
    return
  }

  submitLoading.value = true
  try {
    // 直接创建并提交（后端 POST /api/projects/submit-draft）
    await createAndSubmitProject(buildPayload())
    ElMessage.success('项目已提交，等待审核')
    router.push('/projects')
  } finally {
    submitLoading.value = false
  }
}
</script>

<style scoped>
.step-content {
  padding: 30px 0;
  min-height: 300px;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 700px;
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
