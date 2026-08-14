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
          <el-form-item label="项目名称" prop="title">
            <el-input v-model="formData.title" placeholder="请输入项目名称" maxlength="100" show-word-limit />
          </el-form-item>
          <el-form-item label="项目类别" prop="category">
            <el-select v-model="formData.category" placeholder="请选择类别" style="width: 100%">
              <el-option label="创新训练项目" :value="1" />
              <el-option label="创业训练项目" :value="2" />
              <el-option label="创业实践项目" :value="3" />
              <el-option label="创新竞赛项目" :value="4" />
            </el-select>
          </el-form-item>
          <el-form-item label="摘要" prop="abstract">
            <el-input v-model="formData.abstract" type="textarea" :rows="3" placeholder="200字以内的项目摘要" maxlength="200" show-word-limit />
          </el-form-item>
          <el-form-item label="关键词" prop="keywords">
            <el-input v-model="formData.keywords" placeholder="多个关键词用逗号分隔" />
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
      <div v-show="currentStep === 2" class="step-content">
        <div class="step-header">
          <p class="step-desc">添加团队成员，每位成员需填写学号、姓名和分工</p>
          <el-button type="primary" :icon="Plus" @click="addMember">添加成员</el-button>
        </div>
        <el-table :data="formData.teamMembers" border style="width: 100%; max-width: 700px; margin: 0 auto;">
          <el-table-column type="index" label="序号" width="70" align="center" />
          <el-table-column label="学号" width="150">
            <template #default="{ row, $index }">
              <el-input v-model="row.student_id" placeholder="请输入学号" @blur="searchStudent(row, $index)" />
            </template>
          </el-table-column>
          <el-table-column label="姓名" width="120">
            <template #default="{ row }">
              <el-input v-model="row.student_name" placeholder="请输入姓名" />
            </template>
          </el-table-column>
          <el-table-column label="角色/分工">
            <template #default="{ row }">
              <el-input v-model="row.role" placeholder="如：技术研发、市场调研" />
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
      <div v-show="currentStep === 3" class="step-content">
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
      <div v-show="currentStep === 4" class="step-content">
        <el-form ref="form2Ref" :model="formData" :rules="form2Rules" label-width="100px" style="max-width: 700px; margin: 0 auto;">
          <el-form-item label="项目背景" prop="background">
            <el-input v-model="formData.background" type="textarea" :rows="4" placeholder="说明项目背景和意义" />
          </el-form-item>
          <el-form-item label="研究目标" prop="objectives">
            <el-input v-model="formData.objectives" type="textarea" :rows="4" placeholder="明确项目目标" />
          </el-form-item>
          <el-form-item label="技术路线" prop="methodology">
            <el-input v-model="formData.methodology" type="textarea" :rows="4" placeholder="说明研究方法和技术路线" />
          </el-form-item>
          <el-form-item label="预期成果" prop="expected_outcomes">
            <el-input v-model="formData.expected_outcomes" type="textarea" :rows="4" placeholder="预期产出成果" />
          </el-form-item>
        </el-form>
      </div>

      <!-- Step 5: 预算编制 -->
      <div v-show="currentStep === 5" class="step-content">
        <div class="step-header">
          <p class="step-desc">编制项目预算，各科目金额合计为项目总预算</p>
          <el-button type="primary" :icon="Plus" @click="addBudget">添加科目</el-button>
        </div>
        <el-table :data="formData.budgets" border show-summary :summary-method="getBudgetSummary" style="width: 100%; max-width: 700px; margin: 0 auto;">
          <el-table-column type="index" label="序号" width="70" align="center" />
          <el-table-column label="预算科目" width="200">
            <template #default="{ row }">
              <el-select v-model="row.subject" placeholder="选择科目" style="width: 100%">
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
              <el-input-number v-model="row.amount" :min="0" :precision="2" controls-position="right" style="width: 100%" />
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
        <el-button v-if="currentStep < 5" type="primary" @click="nextStep">下一步</el-button>
        <el-button v-if="currentStep === 5" type="warning" :loading="draftLoading" @click="handleSaveDraft">保存草稿</el-button>
        <el-button v-if="currentStep === 5" type="success" :loading="submitLoading" @click="handleSubmit">正式提交</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import FileUpload from '@/components/FileUpload.vue'
import { createProject, submitProject } from '@/api/project'

const router = useRouter()
const currentStep = ref(0)

// ==================== 表单数据 ====================
const formData = reactive({
  title: '',
  category: undefined as number | undefined,
  abstract: '',
  keywords: '',
  dateRange: [] as string[],
  teamMembers: [] as { student_id: string; student_name: string; role: string }[],
  teacher_id: undefined as number | undefined,
  background: '',
  objectives: '',
  methodology: '',
  expected_outcomes: '',
  budgets: [] as { subject: string; amount: number; remark: string }[],
  attachments: [] as any[],
})

// ==================== Step 1 表单校验 ====================
const form1Ref = ref<FormInstance>()
const form1Rules: FormRules = {
  title: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择项目类别', trigger: 'change' }],
  abstract: [{ required: true, message: '请输入项目摘要', trigger: 'blur' }],
  keywords: [{ required: true, message: '请输入关键词', trigger: 'blur' }],
  dateRange: [{ required: true, message: '请选择起止时间', trigger: 'change' }],
}

// ==================== Step 4 表单校验 ====================
const form2Ref = ref<FormInstance>()
const form2Rules: FormRules = {
  background: [{ required: true, message: '请输入项目背景', trigger: 'blur' }],
  objectives: [{ required: true, message: '请输入研究目标', trigger: 'blur' }],
  methodology: [{ required: true, message: '请输入技术路线', trigger: 'blur' }],
  expected_outcomes: [{ required: true, message: '请输入预期成果', trigger: 'blur' }],
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
  // 步骤 2 和 5 直接前进
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
  formData.teamMembers.push({ student_id: '', student_name: '', role: '' })
}

function removeMember(index: number) {
  formData.teamMembers.splice(index, 1)
}

/** 学号搜索自动填充姓名（模拟） */
function searchStudent(row: any, _index: number) {
  // 实际场景可调用后端接口根据学号查询学生信息
  if (row.student_id.length >= 6) {
    ElMessage.info('学号搜索功能：实际环境中会调用后端接口自动填充姓名')
  }
}

// ==================== 指导教师 ====================
const teacherOptions = ref<any[]>([])
const teacherLoading = ref(false)

async function searchTeacher(query: string) {
  if (!query) {
    teacherOptions.value = []
    return
  }
  teacherLoading.value = true
  try {
    // 实际调用后端搜索教师
    // const res = await getUserList({ keyword: query, role: 2, page: 1, page_size: 20 })
    // teacherOptions.value = res.data.items
    ElMessage.info('教师搜索功能：实际环境中会调用后端接口搜索教师')
  } finally {
    teacherLoading.value = false
  }
}

// ==================== 预算 ====================
function addBudget() {
  formData.budgets.push({ subject: '', amount: 0, remark: '' })
}

function removeBudget(index: number) {
  formData.budgets.splice(index, 1)
}

function getBudgetSummary({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col, index) => {
    if (index === 0) {
      sums[index] = '合计'
    } else if (col.property === 'amount' || index === 2) {
      const total = data.reduce((sum, item) => sum + (item.amount || 0), 0)
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
    title: formData.title,
    category: formData.category,
    abstract: formData.abstract,
    keywords: formData.keywords,
    start_date: formData.dateRange[0],
    end_date: formData.dateRange[1],
    team_members: formData.teamMembers,
    teacher_id: formData.teacher_id,
    background: formData.background,
    objectives: formData.objectives,
    methodology: formData.methodology,
    expected_outcomes: formData.expected_outcomes,
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
  // 校验预算
  if (formData.budgets.length === 0) {
    ElMessage.warning('请至少添加一项预算')
    return
  }
  if (!formData.teacher_id) {
    ElMessage.warning('请选择指导教师')
    return
  }

  submitLoading.value = true
  try {
    // 1. 先创建项目
    const res = await createProject(buildPayload())
    const projectId = res.data.id || res.data
    // 2. 提交审核
    if (projectId) {
      await submitProject(projectId)
    }
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
