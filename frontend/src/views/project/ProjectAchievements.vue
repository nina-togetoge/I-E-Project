<!--
  项目成果（独立页面）
  从项目详情页抽离，支持查看/登记/删除项目成果
-->
<template>
  <div class="page-container" v-loading="loading">
    <template v-if="project">
      <div class="page-header">
        <div class="header-row">
          <div>
            <h2 class="page-title">项目成果</h2>
          </div>
          <div class="header-actions">
            <ProjectSwitcher :current-id="pid" suffix="achievements" />
            <el-button v-if="canRegister" type="primary" @click="openCreate">登记成果</el-button>
          </div>
        </div>
      </div>

      <ProjectStageSteps :project="project" current="achievements" />

      <div class="table-wrap" v-if="achievements.length > 0">
        <table class="paper-table">
          <thead>
            <tr>
              <th style="width:70px">序号</th>
              <th style="width:100px">类型</th>
              <th>标题</th>
              <th style="width:130px">作者</th>
              <th style="width:90px">级别</th>
              <th style="width:110px">获奖等级</th>
              <th style="width:110px">日期</th>
              <th style="width:90px">证明材料</th>
              <th style="width:110px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(a, i) in achievements" :key="a.id">
              <td align="center">{{ i + 1 }}</td>
              <td>{{ achievementTypeMap[a.achievement_type] }}</td>
              <td>{{ a.title }}</td>
              <td>{{ a.author }}</td>
              <td align="center">{{ achievementLevelMap[a.level] || '—' }}</td>
              <td align="center">{{ a.award_level || '—' }}</td>
              <td>{{ formatDate(a.publish_date) }}</td>
              <td align="center">
                <el-button
                  v-if="a.attachments && a.attachments.length"
                  link
                  type="primary"
                  size="small"
                  @click="viewAttachments(a)"
                >{{ a.attachments.length }} 份</el-button>
                <span v-else>—</span>
              </td>
              <td align="center">
                <el-button v-if="canRegister" link type="primary" size="small" @click="openEdit(a)">编辑</el-button>
                <el-button v-if="canDelete" link type="danger" size="small" @click="handleDelete(a)">删除</el-button>
                <span v-if="!canRegister && !canDelete">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <el-empty v-else description="暂无成果" :image-size="60" />
    </template>

    <!-- 成果登记/编辑弹窗 -->
    <el-dialog center v-model="showDialog" :title="editingId ? '编辑项目成果' : '登记项目成果'" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="成果类型" prop="achievement_type">
          <el-select v-model="form.achievement_type" placeholder="请选择" style="width: 100%" @change="onTypeChange">
            <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="成果标题/名称" maxlength="255" show-word-limit />
        </el-form-item>
        <el-form-item v-if="isFieldVisible('author')" :label="labelOf('author')">
          <el-input v-model="form.author" :placeholder="labelOf('author')" maxlength="255" />
        </el-form-item>
        <el-form-item v-if="isFieldVisible('publish_date')" :label="labelOf('publish_date')">
          <el-date-picker
            v-model="form.publish_date"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled-date="disabledPublishDate"
            :placeholder="publishDateTip"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item v-if="isFieldVisible('publisher')" :label="labelOf('publisher')">
          <el-input v-model="form.publisher" :placeholder="labelOf('publisher')" maxlength="255" />
        </el-form-item>
        <el-form-item v-if="isFieldVisible('achievement_no')" :label="labelOf('achievement_no')" prop="achievement_no">
          <el-input v-model="form.achievement_no" :placeholder="labelOf('achievement_no')" maxlength="128" />
        </el-form-item>
        <el-form-item v-if="isFieldVisible('level')" :label="labelOf('level')" prop="level">
          <el-select v-model="form.level" placeholder="请选择" clearable style="width: 100%">
            <el-option label="校级" :value="1" />
            <el-option label="省级" :value="2" />
            <el-option label="国家级" :value="3" />
            <el-option label="国际级" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isFieldVisible('award_level')" :label="labelOf('award_level')" prop="award_level">
          <el-select v-model="form.award_level" placeholder="请选择获奖等级" clearable filterable style="width: 100%">
            <el-option v-for="a in awardLevelOptions" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="成果简介">
          <el-input v-model="form.summary" type="textarea" :rows="3" placeholder="成果简介（选填）" />
        </el-form-item>
        <el-form-item label="证明材料">
          <div class="attachment-block">
            <ProjectAttachmentList
              v-if="dialogAttachments.length"
              :attachments="dialogAttachments"
              deletable
              @remove="handleRemoveAttachment"
            />
            <FileUpload
              :accept="['.pdf', '.doc', '.docx', '.zip', '.rar', '.png', '.jpg']"
              :form-data="{ biz_type: 'achievement', biz_id: 0 }"
              @success="handleFileUpload"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>

    <!-- 证明材料查看弹窗 -->
    <el-dialog center v-model="attDialog" :title="`成果证明材料 - ${attTitle}`" width="600px">
      <ProjectAttachmentList :attachments="attList" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { getProjectDetail, listAchievements, createAchievement, updateAchievement, deleteAchievement } from '@/api/project'
import { deleteAttachment } from '@/api/common'
import ProjectSwitcher from '@/components/ProjectSwitcher.vue'
import ProjectStageSteps from '@/components/ProjectStageSteps.vue'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import FileUpload from '@/components/FileUpload.vue'
import { formatDate } from '@/utils/format'
import { useProcessStore } from '@/store/process'
import { useUserStore } from '@/store/user'

const route = useRoute()
const processStore = useProcessStore()
const userStore = useUserStore()
const pid = computed(() => Number(route.params.id))

const project = ref<any>(null)

// 权限判定（与后端 AchievementService.create/delete 保持一致）
const isLeader = computed(() => !!project.value && Number(project.value.leader_id) === Number(userStore.userInfo?.id))
const isProjectTeacher = computed(() => userStore.isTeacher && !!project.value && Number(project.value.teacher_id) === Number(userStore.userInfo?.id))
const isProjectAdmin = computed(() => {
  if (userStore.isSuperAdmin) return true
  if (userStore.isCollegeAdmin) return !!project.value && Number(project.value.college_id) === Number(userStore.collegeId)
  return false
})

// 成果登记仅在「已立项及之后」阶段（6/7/8/9）且具备权限时可用
const REGISTER_STATUS = [6, 7, 8, 9]
const canRegister = computed(() => !!project.value && REGISTER_STATUS.includes(Number(project.value.status))
  && (isLeader.value || isProjectTeacher.value || isProjectAdmin.value))
// 删除成果：仅项目负责人或管理员（后端 delete 不允许指导教师删除）
const canDelete = computed(() => isLeader.value || isProjectAdmin.value)
const achievements = ref<any[]>([])
const loading = ref(true)
const showDialog = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const existingAttachments = ref<any[]>([])
const newAttachments = ref<any[]>([])
const attDialog = ref(false)
const attTitle = ref('')
const attList = ref<any[]>([])
const formRef = ref<FormInstance>()
const form = reactive({
  achievement_type: undefined as number | undefined,
  title: '',
  author: '',
  publish_date: '',
  publisher: '',
  achievement_no: '',
  level: undefined as number | undefined,
  award_level: '',
  summary: '',
})
const achievementTypeMap: Record<number, string> = {
  1: '论文', 2: '专利', 3: '软件著作权', 4: '竞赛获奖', 5: '创业成果', 6: '其他',
}
// 获奖级别（与成果登记弹窗、后端 AchievementCreate.level 保持一致）
const achievementLevelMap: Record<number, string> = {
  1: '校级', 2: '省级', 3: '国家级', 4: '国际级',
}
const typeOptions = Object.entries(achievementTypeMap).map(([key, label]) => ({
  value: Number(key), label,
}))
interface TypeFieldConfig {
  fields: string[]
  required: string[]
  labels: Record<string, string>
}
// 成果类型 → 字段显隐 + 文案 + 必填规则（让表单随类型自适应，避免平铺无关注字段）
const ACHIEVEMENT_TYPE_CONFIG: Record<number, TypeFieldConfig> = {
  1: { // 论文
    fields: ['author', 'publish_date', 'publisher', 'achievement_no', 'level'],
    required: [],
    labels: { publisher: '发表刊物', achievement_no: '论文编号/DOI', publish_date: '发表日期' },
  },
  2: { // 专利
    fields: ['author', 'publish_date', 'publisher', 'achievement_no', 'level'],
    required: ['achievement_no'],
    labels: { author: '发明人', publisher: '授权机构', achievement_no: '专利号', publish_date: '授权日期' },
  },
  3: { // 软件著作权
    fields: ['author', 'publish_date', 'publisher', 'achievement_no', 'level'],
    required: ['achievement_no'],
    labels: { author: '著作权人', publisher: '登记机构', achievement_no: '登记号', publish_date: '登记日期' },
  },
  4: { // 竞赛获奖
    fields: ['author', 'publish_date', 'level', 'award_level'],
    required: ['level', 'award_level'],
    labels: { author: '参赛团队', publish_date: '获奖日期', level: '竞赛级别' },
  },
  5: { // 创业成果
    fields: ['author', 'publish_date', 'achievement_no', 'level'],
    required: [],
    labels: { author: '负责人', achievement_no: '注册/登记号' },
  },
  6: { // 其他
    fields: ['author', 'publish_date', 'level'],
    required: [],
    labels: {},
  },
}
const DEFAULT_FIELD_LABELS: Record<string, string> = {
  author: '作者', publish_date: '日期', publisher: '发表刊物',
  achievement_no: '编号', level: '级别', award_level: '获奖等级',
}
const awardLevelOptions = ['特等奖', '一等奖', '二等奖', '三等奖', '优秀奖'].map((v) => ({ value: v, label: v }))
const currentTypeConfig = computed<TypeFieldConfig>(() => {
  const t = form.achievement_type
  if (t == null) return { fields: [], required: [], labels: {} }
  return ACHIEVEMENT_TYPE_CONFIG[t] || { fields: [], required: [], labels: {} }
})
function isFieldVisible(key: string) {
  return currentTypeConfig.value.fields.includes(key)
}
function labelOf(key: string) {
  return currentTypeConfig.value.labels[key] || DEFAULT_FIELD_LABELS[key] || ''
}
function onTypeChange() {
  const cfg = currentTypeConfig.value
  if (!cfg.fields.includes('author')) form.author = ''
  if (!cfg.fields.includes('publish_date')) form.publish_date = ''
  if (!cfg.fields.includes('publisher')) form.publisher = ''
  if (!cfg.fields.includes('achievement_no')) form.achievement_no = ''
  if (!cfg.fields.includes('level')) form.level = undefined
  if (!cfg.fields.includes('award_level')) form.award_level = ''
  formRef.value?.clearValidate()
}
const rules = computed<FormRules>(() => {
  const cfg = currentTypeConfig.value
  const r: FormRules = {
    achievement_type: [{ required: true, message: '请选择成果类型', trigger: 'change' }],
    title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  }
  if (cfg.required.includes('achievement_no')) r.achievement_no = [{ required: true, message: '请输入编号', trigger: 'blur' }]
  if (cfg.required.includes('level')) r.level = [{ required: true, message: '请选择级别', trigger: 'change' }]
  if (cfg.required.includes('award_level')) r.award_level = [{ required: true, message: '请选择获奖等级', trigger: 'change' }]
  return r
})

async function loadData() {
  loading.value = true
  try {
    const [detailRes, achRes] = await Promise.all([
      getProjectDetail(pid.value),
      listAchievements(pid.value).catch(() => ({ data: [] })),
    ])
    project.value = detailRes.data
    processStore.setStatus(detailRes.data.status)
    achievements.value = achRes.data || []
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

/** 弹窗内展示的证明材料 = 已保存的 + 本次新上传的 */
const dialogAttachments = computed(() => [...existingAttachments.value, ...newAttachments.value])

/** 成果日期下限：项目开始日期；上限：今天 */
function disabledPublishDate(d: Date) {
  const today = new Date()
  today.setHours(23, 59, 59, 999)
  if (d.getTime() > today.getTime()) return true
  const start = project.value?.start_date
  if (start) {
    const s = new Date(`${String(start).slice(0, 10)}T00:00:00`)
    if (d.getTime() < s.getTime()) return true
  }
  return false
}
const publishDateTip = computed(() => {
  const start = project.value?.start_date ? String(project.value.start_date).slice(0, 10) : ''
  return start ? `不早于项目开始日期（${start}），不晚于今天` : '不晚于今天'
})

function resetDialogForm() {
  editingId.value = null
  existingAttachments.value = []
  newAttachments.value = []
  form.achievement_type = undefined
  form.title = ''
  form.author = ''
  form.publish_date = ''
  form.publisher = ''
  form.achievement_no = ''
  form.level = undefined
  form.award_level = ''
  form.summary = ''
  formRef.value?.clearValidate()
}

function openCreate() {
  resetDialogForm()
  showDialog.value = true
}

function openEdit(row: any) {
  resetDialogForm()
  editingId.value = row.id
  form.achievement_type = row.achievement_type
  form.title = row.title || ''
  form.author = row.author || ''
  form.publish_date = row.publish_date ? String(row.publish_date).slice(0, 10) : ''
  form.publisher = row.publisher || ''
  form.achievement_no = row.achievement_no || ''
  form.level = row.level
  form.award_level = row.award_level || ''
  form.summary = row.summary || ''
  existingAttachments.value = row.attachments || []
  showDialog.value = true
}

function handleFileUpload(file: any) {
  if (!file?.id) return
  newAttachments.value.push({
    ...file,
    uploader_name: userStore.userInfo?.real_name || '本人',
    download_url: file.file_url,
    preview_url: `/api/files/preview/${file.id}`,
  })
}

async function handleRemoveAttachment(att: any) {
  const isNew = newAttachments.value.some((a) => a.id === att.id)
  if (!isNew) {
    try {
      await ElMessageBox.confirm(`确定删除证明材料「${att.file_name}」？`, '提示', { type: 'warning' })
    } catch {
      return
    }
  }
  try {
    await deleteAttachment(att.id)
  } catch {
    // 临时附件删除失败不影响表单，后续保存时仍会绑定
  }
  existingAttachments.value = existingAttachments.value.filter((a) => a.id !== att.id)
  newAttachments.value = newAttachments.value.filter((a) => a.id !== att.id)
}

function viewAttachments(row: any) {
  attTitle.value = row.title
  attList.value = row.attachments || []
  attDialog.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const payload = {
      achievement_type: form.achievement_type!,
      title: form.title,
      author: form.author || undefined,
      publish_date: form.publish_date || undefined,
      publisher: form.publisher || undefined,
      achievement_no: form.achievement_no || undefined,
      level: form.level,
      award_level: form.award_level || undefined,
      summary: form.summary || undefined,
      attachment_ids: newAttachments.value.map((a) => a.id),
    }
    if (editingId.value) {
      await updateAchievement(editingId.value, payload)
      ElMessage.success('成果已更新')
    } else {
      await createAchievement({ ...payload, project_id: pid.value })
      ElMessage.success('成果登记成功')
    }
    showDialog.value = false
    resetDialogForm()
    loadData()
  } catch {
    // 错误已由全局请求拦截器统一提示，此处仅兜底避免未捕获异常
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确认删除成果「${row.title}」？`, '提示', { type: 'warning' })
  await deleteAchievement(row.id)
  ElMessage.success('已删除')
  loadData()
}

onMounted(() => loadData())
onBeforeUnmount(() => processStore.reset())
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  white-space: nowrap;
}
.table-wrap {
  overflow-x: auto;
}
.paper-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.paper-table th,
.paper-table td {
  border: 1px solid #ebeef5;
  padding: 10px 12px;
  text-align: left;
}
.paper-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #606266;
}
.paper-table tbody tr:hover {
  background: #fafafa;
}
.attachment-block {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
