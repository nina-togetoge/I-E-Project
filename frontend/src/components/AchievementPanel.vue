<!--
  项目成果面板
  结项工作台 Tab 与「项目成果」旧路由共用，只负责成果列表与登记/认定弹窗，
  项目详情与页头由外层页面（StagePageShell）提供。
-->
<template>
  <div v-loading="loading">
    <div class="achievement-toolbar">
      <span class="achievement-count">共 {{ achievements.length }} 项成果</span>
      <el-button v-if="canRegister" type="primary" @click="openCreate">登记成果</el-button>
    </div>

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
            <th style="width:100px">认定状态</th>
            <th style="width:240px">操作</th>
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
              <el-tooltip
                v-if="a.review_status === 2 && a.review_comment"
                :content="a.review_comment"
                placement="top"
              >
                <el-tag size="small" type="danger">{{ reviewStatusLabel(a.review_status) }}</el-tag>
              </el-tooltip>
              <el-tag
                v-else
                size="small"
                :type="reviewStatusTagType(a.review_status)"
              >{{ reviewStatusLabel(a.review_status) }}</el-tag>
            </td>
            <td align="center">
              <el-button link type="primary" size="small" @click="openDetail(a)">查看</el-button>
              <el-button
                v-if="canReview && reviewStatusOf(a) !== 1"
                link type="warning" size="small" @click="openReview(a)"
              >认定</el-button>
              <el-button
                v-if="canReview && reviewStatusOf(a) === 1"
                link type="danger" size="small" @click="handleRevoke(a)"
              >撤销认定</el-button>
              <el-button v-if="canEditRow(a)" link type="primary" size="small" @click="openEdit(a)">编辑</el-button>
              <el-button v-if="canDeleteRow(a)" link type="danger" size="small" @click="handleDelete(a)">删除</el-button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <el-empty v-else description="暂无成果" :image-size="60" />

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

    <!-- 成果认定弹窗 -->
    <el-dialog center v-model="reviewDialog" title="成果认定" width="480px">
      <div class="review-target">成果：{{ reviewTarget?.title }}</div>
      <el-form label-width="88px">
        <el-form-item label="认定结果">
          <el-radio-group v-model="reviewForm.result">
            <el-radio :value="1">通过</el-radio>
            <el-radio :value="2">不通过</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="认定意见">
          <el-input
            v-model="reviewForm.comment"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            :placeholder="reviewForm.result === 2 ? '不通过时必填，请说明原因' : '选填'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialog = false">取消</el-button>
        <el-button type="primary" :loading="reviewing" @click="handleReviewSubmit">提交认定</el-button>
      </template>
    </el-dialog>

    <!-- 证明材料查看弹窗 -->
    <el-dialog center v-model="attDialog" :title="`成果证明材料 - ${attTitle}`" width="600px">
      <ProjectAttachmentList :attachments="attList" />
    </el-dialog>

    <!-- 成果详情查看弹窗 -->
    <el-dialog center v-model="detailDialog" :title="detailRow?.title || '成果详情'" width="640px">
      <template v-if="detailRow">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="成果类型">{{ achievementTypeMap[detailRow.achievement_type] || '—' }}</el-descriptions-item>
          <el-descriptions-item label="级别">{{ achievementLevelMap[detailRow.level] || '—' }}</el-descriptions-item>
          <el-descriptions-item label="作者">{{ detailRow.author || '—' }}</el-descriptions-item>
          <el-descriptions-item label="日期">{{ formatDate(detailRow.publish_date) }}</el-descriptions-item>
          <el-descriptions-item label="发表刊物/机构">{{ detailRow.publisher || '—' }}</el-descriptions-item>
          <el-descriptions-item label="编号">{{ detailRow.achievement_no || '—' }}</el-descriptions-item>
          <el-descriptions-item label="获奖等级">{{ detailRow.award_level || '—' }}</el-descriptions-item>
          <el-descriptions-item label="认定状态">
            <el-tag size="small" :type="reviewStatusTagType(detailRow.review_status)">
              {{ reviewStatusLabel(detailRow.review_status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="成果简介" :span="2">{{ detailRow.summary || '—' }}</el-descriptions-item>
          <el-descriptions-item label="认定人">{{ detailRow.reviewer_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="认定时间">{{ detailRow.review_time ? formatDate(detailRow.review_time) : '—' }}</el-descriptions-item>
          <el-descriptions-item label="认定意见" :span="2">{{ detailRow.review_comment || '—' }}</el-descriptions-item>
        </el-descriptions>
        <div class="detail-attachments">
          <div class="detail-attachments__title">证明材料</div>
          <ProjectAttachmentList v-if="detailRow.attachments?.length" :attachments="detailRow.attachments" />
          <span v-else class="detail-attachments__empty">暂无证明材料</span>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { listAchievements, createAchievement, updateAchievement, deleteAchievement, reviewAchievement, revokeAchievement } from '@/api/project'
import { deleteAttachment } from '@/api/common'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import FileUpload from '@/components/FileUpload.vue'
import { formatDate } from '@/utils/format'
import { useUserStore } from '@/store/user'

const props = defineProps<{ project: any }>()

const userStore = useUserStore()
const pid = computed(() => Number(props.project?.id))

// 权限判定（与后端 AchievementService.create/delete 保持一致）
const isLeader = computed(() => !!props.project && Number(props.project.leader_id) === Number(userStore.userInfo?.id))
const isProjectTeacher = computed(() => userStore.isTeacher && !!props.project && Number(props.project.teacher_id) === Number(userStore.userInfo?.id))
const isProjectAdmin = computed(() => {
  if (userStore.isSuperAdmin) return true
  if (userStore.isCollegeAdmin) return !!props.project && Number(props.project.college_id) === Number(userStore.collegeId)
  return false
})

// 成果登记仅在「已立项及之后」阶段（6/7/8/9）且具备权限时可用
const REGISTER_STATUS = [6, 7, 8, 9]
const canRegister = computed(() => !!props.project && REGISTER_STATUS.includes(Number(props.project.status))
  && (isLeader.value || isProjectTeacher.value || isProjectAdmin.value))
// 删除成果：仅项目负责人或管理员（后端 delete 不允许指导教师删除）
const canDelete = computed(() => isLeader.value || isProjectAdmin.value)
// 成果认定：项目指导教师 / 学院管理员 / 超级管理员（负责人不可自认）
const canReview = computed(() => !!props.project && REGISTER_STATUS.includes(Number(props.project.status))
  && (isProjectTeacher.value || isProjectAdmin.value))
const achievements = ref<any[]>([])
const loading = ref(false)
const showDialog = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const existingAttachments = ref<any[]>([])
const newAttachments = ref<any[]>([])
const attDialog = ref(false)
const attTitle = ref('')
const attList = ref<any[]>([])
const detailDialog = ref(false)
const detailRow = ref<any>(null)
const reviewDialog = ref(false)
const reviewing = ref(false)
const reviewTarget = ref<any>(null)
const reviewForm = reactive({ result: 1, comment: '' })
const REVIEW_STATUS_LABEL: Record<number, string> = { 0: '待认定', 1: '已认定', 2: '不通过' }
function reviewStatusLabel(status?: number): string {
  return REVIEW_STATUS_LABEL[Number(status ?? 1)] || '已认定'
}
function reviewStatusTagType(status?: number): string {
  switch (Number(status ?? 1)) {
    case 0: return 'warning'
    case 2: return 'danger'
    default: return 'success'
  }
}
/** 与后端一致：无认定记录的历史成果按「已认定」处理 */
function reviewStatusOf(row: any): number {
  return Number(row.review_status ?? 1)
}
// 已认定成果锁定负责人：仅认定人（指导教师/管理员）仍可编辑
function canEditRow(row: any): boolean {
  return canRegister.value && (reviewStatusOf(row) !== 1 || canReview.value)
}
// 已认定成果负责人不可删除，管理员不受限
function canDeleteRow(row: any): boolean {
  if (!canDelete.value) return false
  if (isProjectAdmin.value) return true
  return reviewStatusOf(row) !== 1
}
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
  1: '校级', 2: '省级', 3: '国家级',
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

async function loadAchievements() {
  if (!pid.value) return
  loading.value = true
  try {
    const res = await listAchievements(pid.value)
    achievements.value = res.data || []
  } catch {
    achievements.value = []
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
  const start = props.project?.start_date
  if (start) {
    const s = new Date(`${String(start).slice(0, 10)}T00:00:00`)
    if (d.getTime() < s.getTime()) return true
  }
  return false
}
const publishDateTip = computed(() => {
  const start = props.project?.start_date ? String(props.project.start_date).slice(0, 10) : ''
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

async function openEdit(row: any) {
  // 认定人修改已认定成果时，修改后认定将失效并需重新认定
  if (reviewStatusOf(row) === 1) {
    try {
      await ElMessageBox.confirm(
        '该成果已认定，修改后将失效并需重新认定，是否继续？',
        '提示', { type: 'warning' },
      )
    } catch {
      return
    }
  }
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
    loadAchievements()
  } catch {
    // 错误已由全局请求拦截器统一提示，此处仅兜底避免未捕获异常
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确认删除成果「${row.title}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteAchievement(row.id)
    ElMessage.success('已删除')
    loadAchievements()
  } catch {
    // 错误已由全局请求拦截器统一提示
  }
}

function openDetail(row: any) {
  detailRow.value = row
  detailDialog.value = true
}

async function handleRevoke(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认撤销成果「${row.title}」的认定？撤销后需重新认定。`,
      '提示', { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await revokeAchievement(row.id)
    ElMessage.success('已撤销认定')
    loadAchievements()
  } catch {
    // 错误已由全局请求拦截器统一提示
  }
}

function openReview(row: any) {
  reviewTarget.value = row
  reviewForm.result = 1
  reviewForm.comment = ''
  reviewDialog.value = true
}

async function handleReviewSubmit() {
  if (!reviewTarget.value) return
  if (reviewForm.result === 2 && !reviewForm.comment.trim()) {
    ElMessage.warning('认定不通过时请填写认定意见')
    return
  }
  reviewing.value = true
  try {
    await reviewAchievement(reviewTarget.value.id, {
      result: reviewForm.result,
      comment: reviewForm.comment.trim() || undefined,
    })
    ElMessage.success('认定完成')
    reviewDialog.value = false
    loadAchievements()
  } catch {
    // 错误已由全局请求拦截器统一提示
  } finally {
    reviewing.value = false
  }
}

watch(() => props.project?.id, (id) => {
  if (id) loadAchievements()
}, { immediate: true })
</script>

<style scoped>
.achievement-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.achievement-count {
  color: #909399;
  font-size: 13px;
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
.review-target {
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  color: #606266;
}
.detail-attachments {
  margin-top: 16px;
}
.detail-attachments__title {
  margin-bottom: 8px;
  font-weight: 600;
  color: #303133;
}
.detail-attachments__empty {
  color: #909399;
  font-size: 13px;
}
</style>
