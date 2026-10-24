<!--
  组件名称：项目成果面板
  面向角色：项目负责人（登记 / 编辑 / 删除未认定成果）、项目指导教师（认定 / 撤销认定）、
           学院管理员与超级管理员（管理本院 / 全校成果）
  核心功能：成果列表、按类型自适应的登记 / 编辑弹窗、证明材料上传与查看、
           成果认定 / 撤销认定、成果详情查看。
  调用 API：listAchievements、createAchievement、updateAchievement、deleteAchievement、
           reviewAchievement、revokeAchievement、deleteAttachment。
  权限 / 状态约束：
    - 登记：项目处于已立项及之后（6/7/8/9），且为负责人、指导教师或管理员。
    - 删除：负责人或管理员；教师不可删除（与后端 delete 一致）。
    - 认定：指导教师、学院管理员、超管；负责人不可自认。
    - 已认定成果对负责人锁定：负责人不能编辑或删除，认定人仍可修改（修改后需重新认定）。
    - 无认定记录的历史成果按「已认定」处理，避免旧数据被误开放编辑。
  关键交互：
    - 弹窗与面板共用，结项工作台 Tab 与旧路由 /projects/:id/achievements 都复用它。
    - 成果类型切换会清空不再适用的字段并重建校验规则，减少无意义字段提交。
    - 新上传证明材料先以 biz_id=0 暂存，保存成果时通过 attachment_ids 绑定。
    - 撤销认定后成果回到「待认定」，可重新走认定流程。
-->
<template>
  <div v-loading="loading">
    <!-- 工具栏：登记入口仅负责人 / 指导教师 / 管理员可见，
         且项目必须已进入可登记阶段；普通成员只能查看 -->
    <div class="achievement-toolbar">
      <span class="achievement-count">共 {{ achievements.length }} 项成果</span>
      <el-button v-if="canRegister" type="primary" @click="openCreate">登记成果</el-button>
    </div>

    <!-- 成果表格：认定状态列在「不通过」时用 tooltip 展示认定意见，避免追加一列 -->
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
              <!-- 操作说明：
                   查看：所有人可见；
                   认定：有认定权限且当前不是「已认定」；
                   撤销认定：有认定权限且当前已认定；
                   编辑 / 删除：受认定锁定与角色双重限制 -->
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

    <!-- 成果登记 / 编辑弹窗：字段随成果类型动态显隐，避免论文、专利、竞赛共用一张巨表 -->
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
          <!-- 日期限制：不早于项目开始日、不晚于今天，防止登记项目周期外的成果 -->
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
          <!-- 证明材料：已保存附件可直接删除；新上传附件先暂存，提交时随成果绑定 -->
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
        <!-- 提交前由动态 rules 校验；保存失败由全局拦截器提示，按钮 loading 防重复 -->
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>

    <!-- 成果认定弹窗：不通过必须填写意见，便于负责人修改后重新提交 -->
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

    <!-- 证明材料查看弹窗：只读列表，预览 / 下载沿用统一的鉴权拼接 -->
    <el-dialog center v-model="attDialog" :title="`成果证明材料 - ${attTitle}`" width="600px">
      <ProjectAttachmentList :attachments="attList" />
    </el-dialog>

    <!-- 成果详情弹窗：集中展示认定人、认定时间与认定意见，便于申诉时核对 -->
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

// ==================== 依赖 / 项目上下文 ====================
// 面板由外层页面传入完整 project，所有阶段与权限判断都基于它，面板本身不再请求项目详情。
const props = defineProps<{ project: any }>()

const userStore = useUserStore()
const pid = computed(() => Number(props.project?.id))

// ==================== 权限判定 ====================
// 与后端 AchievementService.create / delete 保持一致，避免前端出现可点但必失败的按钮。

/** 是否项目负责人本人（可登记、可编辑未认定成果、可删除，但不可认定） */
const isLeader = computed(() => !!props.project && Number(props.project.leader_id) === Number(userStore.userInfo?.id))
/** 是否该项目指导教师本人（可登记、可认定与撤销认定，但不可删除） */
const isProjectTeacher = computed(() => userStore.isTeacher && !!props.project && Number(props.project.teacher_id) === Number(userStore.userInfo?.id))
/** 是否管理员：超管全校；学院管理员仅限本院项目 */
const isProjectAdmin = computed(() => {
  if (userStore.isSuperAdmin) return true
  if (userStore.isCollegeAdmin) return !!props.project && Number(props.project.college_id) === Number(userStore.collegeId)
  return false
})

// 成果登记仅在「已立项及之后」阶段（6/7/8/9）且具备权限时可用；
// 使用白名单而不是 >=6，避免驳回(10)、撤销(11)、待教师确认(12) 误入
const REGISTER_STATUS = [6, 7, 8, 9]
const canRegister = computed(() => !!props.project && REGISTER_STATUS.includes(Number(props.project.status))
  && (isLeader.value || isProjectTeacher.value || isProjectAdmin.value))
// 删除成果：仅项目负责人或管理员（后端 delete 不允许指导教师删除）
const canDelete = computed(() => isLeader.value || isProjectAdmin.value)
// 成果认定：项目指导教师 / 学院管理员 / 超级管理员（负责人不可自认）
const canReview = computed(() => !!props.project && REGISTER_STATUS.includes(Number(props.project.status))
  && (isProjectTeacher.value || isProjectAdmin.value))

// ==================== 列表与弹窗状态 ====================
/** 当前项目成果列表，由 listAchievements 拉取 */
const achievements = ref<any[]>([])
/** 列表加载态 */
const loading = ref(false)
/** 登记 / 编辑弹窗显隐 */
const showDialog = ref(false)
/** 成果保存 loading */
const submitting = ref(false)
/** 正在编辑的成果 ID；为空表示新建 */
const editingId = ref<number | null>(null)
/** 编辑时回显的已保存证明材料 */
const existingAttachments = ref<any[]>([])
/** 本次新上传、尚未保存的证明材料 */
const newAttachments = ref<any[]>([])
/** 证明材料查看弹窗 */
const attDialog = ref(false)
/** 证明材料弹窗标题（成果名称） */
const attTitle = ref('')
/** 证明材料查看列表 */
const attList = ref<any[]>([])
/** 成果详情弹窗 */
const detailDialog = ref(false)
/** 详情弹窗当前成果 */
const detailRow = ref<any>(null)
/** 认定弹窗 */
const reviewDialog = ref(false)
/** 认定提交 loading */
const reviewing = ref(false)
/** 当前正在认定的成果 */
const reviewTarget = ref<any>(null)
/** 认定表单：result 1 通过、2 不通过 */
const reviewForm = reactive({ result: 1, comment: '' })
/** 认定状态文案：后端可能不返回 review_status，历史数据按「已认定」兼容 */
const REVIEW_STATUS_LABEL: Record<number, string> = { 0: '待认定', 1: '已认定', 2: '不通过' }
/** 状态 → 标签颜色：待认定 warning、不通过 danger、已认定 success */
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
// 已认定成果锁定负责人：仅认定人（指导教师/管理员）仍可编辑；
// 这样既保护认定结果不被负责人随意改动，又允许认定人修正录入错误
function canEditRow(row: any): boolean {
  return canRegister.value && (reviewStatusOf(row) !== 1 || canReview.value)
}
// 已认定成果负责人不可删除，管理员不受限；避免删除已认定成果导致认定记录悬空
function canDeleteRow(row: any): boolean {
  if (!canDelete.value) return false
  if (isProjectAdmin.value) return true
  return reviewStatusOf(row) !== 1
}

// ==================== 登记表单 ====================
// 表单与列表解耦：弹窗打开时按行数据回填，关闭时统一重置，避免脏字段残留。
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
/** 成果类型码到名称的映射，与后端 AchievementType 保持一致 */
const achievementTypeMap: Record<number, string> = {
  1: '论文', 2: '专利', 3: '软件著作权', 4: '竞赛获奖', 5: '创业成果', 6: '其他',
}
// 获奖级别（与成果登记弹窗、后端 AchievementCreate.level 保持一致）
const achievementLevelMap: Record<number, string> = {
  1: '校级', 2: '省级', 3: '国家级',
}
/** 类型下拉选项：由映射表派生，保证展示与提交值同源 */
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
/** 字段默认文案：类型配置没有覆盖时使用，保证每个字段都有可读标签 */
const DEFAULT_FIELD_LABELS: Record<string, string> = {
  author: '作者', publish_date: '日期', publisher: '发表刊物',
  achievement_no: '编号', level: '级别', award_level: '获奖等级',
}
/** 获奖等级为自由文本枚举，允许筛选；与后端 award_level 字符串字段一致 */
const awardLevelOptions = ['特等奖', '一等奖', '二等奖', '三等奖', '优秀奖'].map((v) => ({ value: v, label: v }))
/** 当前所选类型的字段配置；未选类型时返回空配置，表单只显示类型与标题 */
const currentTypeConfig = computed<TypeFieldConfig>(() => {
  const t = form.achievement_type
  if (t == null) return { fields: [], required: [], labels: {} }
  return ACHIEVEMENT_TYPE_CONFIG[t] || { fields: [], required: [], labels: {} }
})
/** 判断字段在当前类型下是否展示 */
function isFieldVisible(key: string) {
  return currentTypeConfig.value.fields.includes(key)
}
/** 取字段标签：优先类型专属文案，其次通用文案，最后空串 */
function labelOf(key: string) {
  return currentTypeConfig.value.labels[key] || DEFAULT_FIELD_LABELS[key] || ''
}
/**
 * 切换成果类型：清空新类型不再使用的字段并清除旧校验。
 * 说明：防止论文残留的「论文编号」被带到专利提交里，造成后端字段语义错乱。
 */
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
/**
 * 动态校验规则：类型与标题必填，编号 / 级别 / 获奖等级按类型配置追加。
 * 说明：规则随类型实时变化，切换类型后需 clearValidate 才能消除旧提示。
 */
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

/**
 * 加载当前项目成果列表。
 * 说明：project id 为空时直接返回；失败降级为空列表，避免面板整体报错。
 */
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

/**
 * 成果日期限制：不早于项目开始日期、不晚于今天。
 * 说明：项目周期外的成果通常不属于本项目，前端先做提示性限制，最终仍由后端校验。
 */
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
/** 日期选择提示：告诉用户可选的区间，减少反复试错 */
const publishDateTip = computed(() => {
  const start = props.project?.start_date ? String(props.project.start_date).slice(0, 10) : ''
  return start ? `不早于项目开始日期（${start}），不晚于今天` : '不晚于今天'
})

/**
 * 重置登记表单到初始态：清空编辑 ID、附件缓存、字段值与校验结果。
 * 说明：新建与编辑共用弹窗，必须在每次打开前重置，防止上一条成果的字段泄漏。
 */
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

/** 打开「登记成果」弹窗：先重置表单，再显示弹窗 */
function openCreate() {
  resetDialogForm()
  showDialog.value = true
}

/**
 * 打开「编辑成果」弹窗并回填行数据。
 * 说明：已认定成果仅认定人可进入；进入后修改会使认定失效，因此先二次确认。
 * 参数 row：成果行数据。
 * 失败处理：用户取消确认时直接返回，不重置表单。
 */
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

/**
 * 证明材料上传成功：暂存并补充上传人、下载 / 预览地址。
 * 参数 file：FileUpload 返回的文件对象；缺少 id 时忽略，避免提交空附件。
 */
function handleFileUpload(file: any) {
  if (!file?.id) return
  newAttachments.value.push({
    ...file,
    uploader_name: userStore.userInfo?.real_name || '本人',
    download_url: file.file_url,
    preview_url: `/api/files/preview/${file.id}`,
  })
}

/**
 * 删除证明材料。
 * 说明：已保存附件需二次确认并调用后端删除；新上传附件直接本地移除。
 * 后端删除失败不阻断表单（临时文件后续仍会随成果绑定），仅做兜底。
 */
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

/** 打开证明材料弹窗：缓存当前成果标题与附件列表，避免表格数据刷新后弹窗内容变化 */
function viewAttachments(row: any) {
  attTitle.value = row.title
  attList.value = row.attachments || []
  attDialog.value = true
}

/**
 * 保存成果：新建走 createAchievement（带 project_id），编辑走 updateAchievement。
 * 说明：附件只下发本次新增的 id；空字符串字段统一转 undefined，避免后端存空串。
 * 失败处理：校验失败直接返回；接口异常由全局拦截器提示，finally 复位 loading。
 */
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

/** 删除成果：不可恢复，需二次确认；已认定成果对负责人不可见删除入口 */
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

/** 打开成果详情弹窗：直接使用行数据，不再额外请求详情接口 */
function openDetail(row: any) {
  detailRow.value = row
  detailDialog.value = true
}

/**
 * 撤销成果认定：撤销后回到「待认定」，需重新走认定流程。
 * 失败处理：取消确认直接返回；接口异常由全局拦截器提示。
 */
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

/** 打开认定弹窗：默认「通过」且清空意见，避免沿用上一条成果的认定结论 */
function openReview(row: any) {
  reviewTarget.value = row
  reviewForm.result = 1
  reviewForm.comment = ''
  reviewDialog.value = true
}

/**
 * 提交认定结果。
 * 说明：不通过必须填写意见，便于负责人修改后重新提交；
 * 通过时意见可选，提交成功后关闭弹窗并刷新列表。
 * 失败处理：意见缺失仅提示；接口异常由全局拦截器提示。
 */
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

// 项目切换时重新加载成果；immediate 保证首次挂载也能拉到数据
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
