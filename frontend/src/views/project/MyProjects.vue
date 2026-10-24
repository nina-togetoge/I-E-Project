<!--
  页面名称：我的项目列表
  面向角色：学生（本人负责的项目）、指导教师（名下项目）、学院管理员 / 超级管理员（可见范围由后端权限收敛）
  核心功能：关键词 / 状态筛选与分页、查看详情、编辑草稿、提交、撤回、删除、
           批量导出 Excel、批量打印申请书、批量提交 / 批量删除草稿，
           以及从侧边栏「流程阶段」携带 status 进入时自动直达对应的阶段子页面。
  调用 API：getProjectList、getProjectDetail、updateProject、submitProject、deleteProject、
           withdrawProject、deleteAttachment、getColleges、getCompetitionList、getUserList。
  权限 / 状态约束：
    - 编辑、提交：仅项目负责人本人或超级管理员；仅草稿(0)与「指导教师驳回且允许重提」(10 + resubmittable)。
    - 撤回：仅「待指导教师确认」(12)；超管全校、学院管理员限本院、学生限本人；教师 / 专家不可撤回。
    - 删除、批量提交、批量删除：仅草稿(0)；批量操作会自动跳过非草稿行。
    - 中期检查入口：本人且状态 6 / 7；成果登记入口：本人且状态 6 / 7 / 8 / 9。
  关键交互：
    - 「查看」走 projectDetailStore.open(id)，关闭详情后回刷列表，保证审核结果即时反映。
    - 「编辑」先拉取详情再打开弹窗，避免请求未返回时用户对着旧数据直接点确定。
    - 关键词 / 状态变化走 400ms 防抖并回到第 1 页；路由 query.status 变化会同步筛选条件。
    - 阶段直达会在「筛选后仅剩一个本人项目」时自动 replace 到中期 / 成果 / 结项 / 详情页。
-->
<template>
  <div class="page-container" id="my-projects-print">
    <!-- 筛选区：关键词负责项目名模糊匹配，状态下拉直接使用后端状态码；
         二者变化会自动防抖查询，无需再点「查询」 -->
    <el-card shadow="never" class="search-card no-print">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="项目名称">
          <el-input v-model="searchForm.keyword" placeholder="请输入关键词" clearable />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 130px">
            <el-option label="草稿" :value="0" />
            <el-option label="待学院初审" :value="1" />
            <el-option label="待校级复审" :value="3" />
            <el-option label="待分配评审专家" :value="13" />
            <el-option label="待专家评审" :value="5" />
            <el-option label="已立项" :value="6" />
            <el-option label="中期检查中" :value="7" />
            <el-option label="待结题" :value="8" />
            <el-option label="已结题" :value="9" />
            <el-option label="已驳回" :value="10" />
            <el-option label="已撤销" :value="11" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 操作栏：新建入口仅学生可见；批量按钮只在勾选行后出现，
         其中「批量提交 / 批量删除」仅统计选中行里的草稿，非草稿会被后端逐一跳过 -->
    <div class="action-bar no-print">
      <!-- 教师、专家、管理员不参与项目申报，故仅学生角色展示新建按钮 -->
      <el-button v-if="userStore.isStudent" type="primary" :icon="EditPen" @click="router.push('/projects/create')">新建项目申报</el-button>

      <template v-if="selectedRows.length > 0">
        <el-divider direction="vertical" />
        <span style="color: #606266; margin-right: 8px;">已选 <b style="color: var(--el-color-primary);">{{ selectedRows.length }}</b> 项</span>
        <el-button :icon="Download" @click="handleBatchExport">批量导出 Excel</el-button>
        <el-button :icon="Printer" @click="handleBatchPrint">批量打印申请书</el-button>
        <el-button
          type="success"
          :icon="Check"
          :disabled="draftSelectedIds.length === 0"
          @click="handleBatchSubmit"
        >
          批量提交{{ draftSelectedIds.length > 0 ? `(${draftSelectedIds.length})` : '' }}
        </el-button>
        <el-button
          type="danger"
          :icon="Delete"
          :disabled="draftSelectedIds.length === 0"
          @click="handleBatchDelete"
        >
          批量删除{{ draftSelectedIds.length > 0 ? `(${draftSelectedIds.length})` : '' }}
        </el-button>
      </template>
    </div>

    <!-- 表格：服务端分页；勾选结果受分页影响，因此批量操作只对当前页选中行生效 -->
    <PaginationTable
      :data="sortedTableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      :selection="true"
      @page-change="handlePageChange"
      @selection-change="handleSelectionChange"
    >
      <template #status="{ row }">
        <StatusTag
          :status="row.status"
          :label="statusLabel(row)"
          :override-type="statusOverrideType(row)"
        />
      </template>
      <!-- 行操作：每个按钮的显示条件都由「状态 + 当前用户身份」共同决定；
           「查看」对所有可见行开放，其余入口按业务阶段逐步收敛，避免越权操作 -->
      <template #actions="{ row }">
        <el-button link type="primary" size="small" @click="projectDetailStore.open(row.id)">查看</el-button>
        <!-- 中期检查：仅负责人本人且项目已立项 / 中期检查中 -->
        <el-button v-if="canMidterm(row)" link type="primary" size="small" @click="handleMidterm(row)">中期检查</el-button>
        <!-- 成果登记：仅负责人本人且项目处于已立项及之后的阶段 -->
        <el-button v-if="canAchievement(row)" link type="primary" size="small" @click="handleAchievement(row)">成果登记</el-button>
        <!-- 编辑：草稿或「指导教师驳回并允许重提」；已落选项目不可编辑 -->
        <el-button v-if="canEdit(row)" link type="warning" size="small" @click="handleEdit(row)">编辑</el-button>
        <!-- 提交：与编辑同权限，提交后进入教师确认，不能再修改 -->
        <el-button v-if="canSubmit(row)" link type="success" size="small" @click="handleSubmit(row)">提交</el-button>
        <!-- 撤回：仅待指导教师确认阶段，教师 / 专家无此按钮 -->
        <el-button v-if="canWithdraw(row)" link type="danger" size="small" @click="handleWithdraw(row)">撤回</el-button>
        <!-- 删除：仅草稿可删，避免误删已进入流程的项目 -->
        <el-button v-if="row.status === 0" link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="project" :description="emptyDescription" />
      </template>
    </PaginationTable>

    <!-- 编辑弹窗：仅草稿 / 可重提的驳回项目会打开；
         「确定」= 保存并立即提交，「暂存」= 仅保存草稿，二者共用同一份提交数据 -->
    <el-dialog
      center
      v-model="editDialogVisible"
      title="编辑项目"
      width="720px"
      :close-on-click-modal="false"
      @closed="editingId = null"
    >
      <div v-loading="editLoading" style="max-height: 62vh; overflow-y: auto;">
        <el-form :model="editForm" label-width="100px">
          <el-form-item label="项目名称" required>
            <el-input v-model="editForm.project_name" placeholder="请输入项目名称" maxlength="100" show-word-limit />
          </el-form-item>
          <el-form-item label="项目类别" required>
            <el-select v-model="editForm.project_type" placeholder="请选择类别" style="width: 100%">
              <el-option label="创新训练项目" :value="1" />
              <el-option label="创业训练项目" :value="2" />
              <el-option label="创业实践项目" :value="3" />
            </el-select>
          </el-form-item>
          <el-form-item label="项目级别">
            <el-select v-model="editForm.project_level" placeholder="请选择级别" style="width: 100%">
              <el-option label="院级" :value="1" />
              <el-option label="校级" :value="2" />
              <el-option label="省级" :value="3" />
              <el-option label="国家级" :value="4" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属学院">
            <!-- 学院由申报时确定，编辑阶段不允许改挂学院，避免影响学院初审归属 -->
            <el-select v-model="editForm.college_id" filterable disabled placeholder="请选择学院" style="width: 100%">
              <el-option v-for="c in collegeOptions" :key="c.id" :label="c.college_name" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="参赛比赛" required>
            <el-select v-model="editForm.competition_id" filterable placeholder="请选择参加的比赛" clearable style="width: 100%">
              <el-option v-for="c in competitionOptions" :key="c.id" :label="competitionLabel(c)" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="指导教师" required>
            <el-select
              v-model="editForm.teacher_id"
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
          <el-form-item label="摘要">
            <el-input v-model="editForm.project_summary" type="textarea" :rows="3" placeholder="200字以内的项目摘要" maxlength="200" show-word-limit />
          </el-form-item>
          <el-form-item label="开始日期">
            <el-date-picker v-model="editForm.start_date" type="date" placeholder="选择开始日期" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
          <el-form-item label="结束日期">
            <el-date-picker v-model="editForm.end_date" type="date" placeholder="选择结束日期" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
          <el-form-item label="附件">
            <!-- 附件分两段：已有附件可直接删除（后端软删除立即生效）；
                 新上传文件先挂 temporaries（biz_id=0），保存时通过 attachment_ids 绑定到项目 -->
            <div style="width: 100%">
              <ProjectAttachmentList
                v-if="attachmentList.length > 0"
                :attachments="attachmentList"
                deletable
                @remove="handleRemoveAttachment"
              />
              <div v-else style="color: #909399; font-size: 13px; margin-bottom: 8px;">暂无附件</div>
              <FileUpload
                :accept="['.pdf', '.doc', '.docx', '.zip', '.rar']"
                :form-data="{ biz_type: 'project', biz_id: 0 }"
                @success="handleNewAttachment"
              />
            </div>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <!-- 确定：先校验必填再保存并提交；暂存：只保存不提交，允许字段暂缺 -->
        <el-button type="primary" :loading="editSaving" @click="handleEditConfirm">确定</el-button>
        <el-button :loading="editSaving" @click="handleEditSaveDraft">暂存</el-button>
        <el-button @click="editDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, EditPen, Download, Printer, Check, Delete } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import FileUpload from '@/components/FileUpload.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import { getProjectList, submitProject, deleteProject, withdrawProject, getProjectDetail, updateProject } from '@/api/project'
import { deleteAttachment } from '@/api/common'
import { getColleges } from '@/api/auth'
import { getCompetitionList, competitionLabel, isCompetitionSelectable } from '@/api/competition'
import { getUserList } from '@/api/user'
import * as XLSX from 'xlsx'
import { saveAs } from 'file-saver'
import { STATUS_LABELS } from '@/api/types'
import { formatDateTime } from '@/utils/format'
import { useDebounce } from '@/composables/useDebounce'
import { useProjectDetailStore } from '@/store/projectDetail'
import { useUserStore } from '@/store/user'

// ==================== 路由与全局 Store ====================
// 路由用于读取 query.status（侧边栏阶段入口）并做子页面跳转；
// projectDetailStore 负责跨页面的详情抽屉，userStore 提供角色、学院与当前用户 ID。
const route = useRoute()
const router = useRouter()
const projectDetailStore = useProjectDetailStore()
const userStore = useUserStore()

// 查看即审核：详情抽屉/弹窗里可能完成审核，关闭后回刷列表，保证状态列与按钮权限立即更新
watch(() => projectDetailStore.visible, (v) => {
  if (!v) loadData()
})

// ==================== 筛选与分页状态 ====================
/** 列表筛选条件：keyword 用于项目名称模糊搜索；status 为后端状态码，undefined 表示不限状态 */
const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined,
})

/** 当前页项目数据；分页、排序均以后端返回为准，前端不做二次排序 */
const tableData = ref<any[]>([])
/** 满足筛选条件的总条数，供分页组件计算页数 */
const total = ref(0)
/** 列表请求中的加载态，同时驱动表格 loading 遮罩 */
const loading = ref(false)
/** 当前页码，从 1 开始；筛选变化时会被重置 */
const page = ref(1)
/** 每页条数，由分页组件回调同步 */
const pageSize = ref(10)
/** 表格勾选行；批量导出 / 打印 / 提交 / 删除都以它为准 */
const selectedRows = ref<any[]>([])

// ==================== 编辑弹窗 ====================
/** 编辑弹窗显隐；只有 loadEditForm 成功后才置 true */
const editDialogVisible = ref(false)
/** 正在编辑的项目 ID；弹窗关闭时清空，防止「确定」误提交到上一个项目 */
const editingId = ref<number | null>(null)
/** 详情加载态，覆盖弹窗内容区域 */
const editLoading = ref(false)
/** 保存 / 提交按钮的 loading，避免重复点击产生并发请求 */
const editSaving = ref(false)
/** 编辑表单数据；与详情接口字段一一对应，日期统一用 YYYY-MM-DD 字符串 */
const editForm = reactive({
  project_name: '',
  project_type: undefined as number | undefined,
  project_level: 1 as number,
  college_id: undefined as number | undefined,
  competition_id: undefined as number | undefined,
  project_summary: '',
  start_date: '',
  end_date: '',
  teacher_id: undefined as number | undefined,
  attachments: [] as any[],
})
// 本次新增上传的临时附件（biz_id=0），保存时随 attachment_ids 一起绑定到项目
const newAttachments = ref<any[]>([])
// 统一展示的附件列表：已有附件 + 本次新增附件
const attachmentList = computed(() => [...editForm.attachments, ...newAttachments.value])
/** 学院下拉数据；接口失败时降级为空数组，不阻断编辑 */
const collegeOptions = ref<any[]>([])
/** 比赛下拉数据；仅保留「报名中 / 进行中」等可选状态 */
const competitionOptions = ref<any[]>([])
/** 教师远程搜索结果 */
const teacherOptions = ref<any[]>([])
/** 教师远程搜索加载态 */
const teacherLoading = ref(false)

/**
 * 拉取项目详情并填充编辑表单，同时并行加载学院与比赛选项。
 * 参数 id：项目主键。
 * 副作用：会改写 editForm、collegeOptions、competitionOptions、teacherOptions。
 * 失败处理：统一提示并返回 false，调用方据此不打开弹窗，避免对空表单操作。
 */
async function loadEditForm(id: number): Promise<boolean> {
  editLoading.value = true
  try {
    const [detailRes, collegeRes, compRes] = await Promise.all([
      getProjectDetail(id),
      getColleges().catch(() => ({ data: [] })),
      getCompetitionList({ page: 1, page_size: 100 }).catch(() => ({ data: { items: [] } })),
    ])
    const p = detailRes.data
    editForm.project_name = p.project_name || ''
    editForm.project_type = p.project_type
    editForm.project_level = p.project_level || 1
    editForm.college_id = p.college_id
    editForm.competition_id = p.competition_id ?? undefined
    editForm.project_summary = p.project_summary || ''
    editForm.start_date = p.start_date || ''
    editForm.end_date = p.end_date || ''
    editForm.teacher_id = p.teacher_id ?? undefined
    editForm.attachments = p.attachments || []
    collegeOptions.value = (collegeRes as any).data || []
    competitionOptions.value = ((compRes as any).data?.items || []).filter(isCompetitionSelectable)
    // 教师：若有 teacher_id 直接填充，否则按姓名搜索
    if (p.teacher_id) {
      teacherOptions.value = [{ id: p.teacher_id, real_name: p.teacher_name || '' }]
      editForm.teacher_id = p.teacher_id
    } else if (p.teacher_name) {
      try {
        const tRes: any = await getUserList({ keyword: p.teacher_name, role: 2, page: 1, page_size: 10 })
        const items = tRes.data?.items || []
        const matched = items.find((t: any) => t.real_name === p.teacher_name) || items[0]
        if (matched) {
          teacherOptions.value = [matched]
          editForm.teacher_id = matched.id
        }
      } catch { /* ignore */ }
    }
    return true
  } catch {
    ElMessage.error('加载项目数据失败')
    return false
  } finally {
    editLoading.value = false
  }
}

/**
 * 按姓名远程搜索指导教师（后端限定 role=2）。
 * 参数 query：用户输入的关键词；为空时直接清空选项，避免无意义请求。
 * 失败处理：提示「教师搜索失败」，保留旧选项以便继续选择。
 */
async function searchTeacher(query: string) {
  if (!query) { teacherOptions.value = []; return }
  teacherLoading.value = true
  try {
    const res: any = await getUserList({ keyword: query, role: 2, page: 1, page_size: 20 })
    teacherOptions.value = res.data?.items || []
  } catch { ElMessage.error('教师搜索失败') }
  finally { teacherLoading.value = false }
}

/**
 * 组装更新接口所需的 payload。
 * 说明：college_id 有意不下发，学院在申报后锁定；
 * attachment_ids 只包含本次新上传的附件，已存在附件由后端保持原绑定。
 */
function buildEditPayload() {
  return {
    project_name: editForm.project_name,
    project_type: editForm.project_type,
    project_level: editForm.project_level,
    competition_id: editForm.competition_id || null,
    project_summary: editForm.project_summary,
    start_date: editForm.start_date || null,
    end_date: editForm.end_date || null,
    teacher_id: editForm.teacher_id || null,
    attachment_ids: newAttachments.value.map((a: any) => a.id),
  }
}

/** 起止日期顺序校验（YYYY-MM-DD 可直接按字符串比较）；不通过时提示并返回 false */
function validateDateRange(): boolean {
  if (editForm.start_date && editForm.end_date && editForm.start_date > editForm.end_date) {
    ElMessage.warning('开始日期不能晚于结束日期')
    return false
  }
  return true
}

/**
 * 新增附件上传成功回调。
 * 参数 file：FileUpload 返回的文件对象（含 id、file_name 等）。
 * 说明：此处只暂存，不立即绑定项目；若用户取消编辑，临时附件不会污染项目数据。
 */
// 新增附件上传成功回调：暂存待保存时绑定到项目
function handleNewAttachment(file: any) {
  newAttachments.value.push(file)
}

/**
 * 删除附件：已有附件需二次确认后走后端软删除；新上传附件同样从本地列表移除。
 * 参数 att：附件对象。
 * 失败处理：用户取消确认时直接返回；接口异常由全局请求拦截器提示。
 */
// 删除已有附件（后端软删除，立即生效）
async function handleRemoveAttachment(att: any) {
  try {
    await ElMessageBox.confirm(`确定删除附件「${att.file_name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await deleteAttachment(att.id)
  editForm.attachments = editForm.attachments.filter((a: any) => a.id !== att.id)
  newAttachments.value = newAttachments.value.filter((a: any) => a.id !== att.id)
  ElMessage.success('附件已删除')
}

/**
 * 「暂存」：仅保存当前编辑内容，不触发提交。
 * 副作用：成功后关闭弹窗并刷新列表。
 * 失败处理：接口异常由全局拦截器提示，finally 中复位 loading，避免按钮卡死。
 */
async function handleEditSaveDraft() {
  if (!editingId.value) return
  if (!validateDateRange()) return
  editSaving.value = true
  try {
    await updateProject(editingId.value, buildEditPayload())
    ElMessage.success('暂存成功')
    editDialogVisible.value = false
    loadData()
  } finally { editSaving.value = false }
}

/**
 * 「确定」：前端先行校验必填项与日期区间，再保存并立即提交。
 * 说明：提交后项目进入指导教师确认，不能再编辑，因此这里逐项拦截缺失字段。
 * 失败处理：校验失败仅提示不请求；接口异常由全局拦截器提示。
 */
async function handleEditConfirm() {
  if (!editingId.value) return
  if (!editForm.project_name.trim()) { ElMessage.warning('请输入项目名称'); return }
  if (!editForm.project_type) { ElMessage.warning('请选择项目类别'); return }
  if (!editForm.competition_id) { ElMessage.warning('请选择参加的比赛'); return }
  if (!editForm.teacher_id) { ElMessage.warning('请选择指导教师'); return }
  if (!validateDateRange()) return
  editSaving.value = true
  try {
    await updateProject(editingId.value, buildEditPayload())
    await submitProject(editingId.value)
    ElMessage.success('已提交，等待审核')
    editDialogVisible.value = false
    loadData()
  } finally { editSaving.value = false }
}

/** 选中行中状态为草稿(0)的 ID 集合；批量提交 / 删除只处理这批 ID */
const draftSelectedIds = computed(() => selectedRows.value.filter((r) => r.status === 0).map((r) => r.id))

/** 表格数据副本：避免表格组件内部对原数组的改动影响分页状态 */
const sortedTableData = computed(() => {
  return [...tableData.value]
})

// 空状态文案：按当前状态筛选给出对应提示，避免误导（如已结题筛选下不再提示"快去创建"）
const emptyDescription = computed(() => {
  switch (searchForm.status) {
    case 9: return '暂无已结题项目'
    case 8: return '暂无待结题项目'
    case 7: return '暂无中期检查中的项目'
    case 6: return '暂无已立项项目（立项后可登记成果）'
    default: return '暂无项目，快去创建一个吧'
  }
})

// 列定义：状态列使用自定义插槽以区分「驳回可重提」与「落选」；比赛列组合赛事届次展示
const columns: TableColumn[] = [
  { prop: 'project_name', label: '项目名称', minWidth: 200 },
  { prop: 'project_type_name', label: '类别', width: 120 },
  { prop: 'project_level_name', label: '级别', width: 90 },
  { prop: 'teacher_name', label: '指导教师', width: 100 },
  { prop: 'competition_name', label: '参赛比赛', minWidth: 200, formatter: (_val: string, row: any) => row.competition_name ? (row.competition_session ? `${row.competition_name}（${row.competition_session}）` : row.competition_name) : '-' },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
  { prop: 'created_at', label: '创建时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

/** 表格勾选变化回调：同步批量操作的数据源 */
function handleSelectionChange(rows: any[]) {
  selectedRows.value = rows
}

/**
 * 加载当前页项目列表。
 * 副作用：写入 tableData / total，并可能触发阶段直达跳转。
 * 失败处理：未单独捕获，异常由全局请求拦截器统一提示；finally 保证 loading 复位。
 */
async function loadData() {
  loading.value = true
  try {
    const res = await getProjectList({
      page: page.value,
      page_size: pageSize.value,
      ...searchForm,
    })
    tableData.value = res.data.items
    total.value = res.data.total
    autoRedirectOnStageFilter()
  } finally {
    loading.value = false
  }
}

// 流程阶段直达：从侧边栏阶段进入（URL 携带 status）且过滤后仅有一个本人项目时，
// 直接进入该阶段对应的子页面（中期检查/成果登记表单，结项验收/已结题详情）
function autoRedirectOnStageFilter() {
  const raw = route.query.status
  if (raw == null || raw === '') return
  const status = Number(raw)
  if (tableData.value.length !== 1) return
  const p = tableData.value[0]
  if (!(userStore.isStudent && isProjectLeader(p))) return
  let target: string | null = null
  if (status === 6) target = `/projects/${p.id}/achievements`
  else if (status === 7) target = `/projects/${p.id}/midterm`
  else if (status === 8) target = `/projects/${p.id}/final`
  else if (status === 9) target = `/projects/${p.id}?scroll=finished`
  if (target) router.replace(target)
}

/** 筛选条件变化后的防抖查询：400ms 内连续输入只发一次请求，减轻后端压力 */
const debouncedLoadData = useDebounce(loadData, 400)

// 关键词或状态变化时回到第 1 页再查询，避免停留在超出结果范围的页码
watch(
  () => [searchForm.keyword, searchForm.status],
  () => {
    page.value = 1
    debouncedLoadData()
  }
)

/** 点击「查询」：重置页码并立即执行（flush 取消防抖等待） */
function handleSearch() {
  page.value = 1
  debouncedLoadData.flush()
}

/** 点击「重置」：清空关键词与状态后立即查询 */
function handleReset() {
  searchForm.keyword = ''
  searchForm.status = undefined
  handleSearch()
}

/** 分页变化：同步页码 / 每页条数并重新请求 */
function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

// ==================== 操作按钮权限判断 ====================
// 可管理（编辑/提交）：仅项目负责人本人或超级管理员；
// 教师/专家/其他学生查看他人项目时不得出现编辑、提交按钮
function canManage(row: any) {
  return isProjectLeader(row) || userStore.isSuperAdmin
}
// 可编辑：草稿；或「指导教师驳回」的已驳回项目（可修改重提）；「落选」不可编辑
function canEdit(row: any) {
  return canManage(row) && (row.status === 0 || (row.status === 10 && !!row.resubmittable))
}
// 可提交：草稿；或「指导教师驳回」的已驳回项目
function canSubmit(row: any) {
  return canManage(row) && (row.status === 0 || (row.status === 10 && !!row.resubmittable))
}
// 状态列文案：区分「指导教师驳回（可修改重提）」与「落选（终局）」
function statusLabel(row: any): string | undefined {
  if (row.status === 10) return row.resubmittable ? '已驳回（可修改重提）' : '已落选'
  return undefined
}
function statusOverrideType(row: any): string | undefined {
  if (row.status === 10) return row.resubmittable ? 'warning' : 'danger'
  return undefined
}
// 可撤回：与后端 ProjectService.withdraw 保持一致
// 状态前提：仅「待指导教师确认」(12) 可撤回；进入学院初审(1)及以后环节不可撤回
// 身份前提：超管全校 / 学院管理员仅本院 / 学生仅本人负责；教师、专家不可撤回
function canWithdraw(row: any) {
  if (row.status !== 12) return false
  if (userStore.isSuperAdmin) return true
  if (userStore.isCollegeAdmin) return row.college_id === userStore.collegeId
  if (userStore.isStudent) return row.leader_id === userStore.userInfo?.id
  return false
}

// 是否为该项目负责人（本人）
function isProjectLeader(row: any) {
  return Number(row.leader_id) === Number(userStore.userInfo?.id)
}
// 中期检查入口：项目负责人本人，项目处于已立项(6)/中期检查中(7)
function canMidterm(row: any) {
  return userStore.isStudent && isProjectLeader(row) && [6, 7].includes(row.status)
}
// 成果登记入口：项目负责人本人，已立项及之后（与后端 AchievementService 状态校验一致）
function canAchievement(row: any) {
  return userStore.isStudent && isProjectLeader(row) && [6, 7, 8, 9].includes(row.status)
}
/** 跳转中期检查独立页；页面内会再次按状态与负责人身份做权限校验 */
function handleMidterm(row: any) {
  router.push(`/projects/${row.id}/midterm`)
}
/** 跳转成果登记独立页；登记动作本身由后端校验项目阶段与角色 */
function handleAchievement(row: any) {
  router.push(`/projects/${row.id}/achievements`)
}

/**
 * 打开编辑弹窗：先重置新增附件缓存并加载详情，成功后才显示弹窗。
 * 参数 row：当前行数据，仅用到 id。
 * 失败处理：loadEditForm 返回 false 时保持弹窗关闭，避免旧表单被误提交。
 */
async function handleEdit(row: any) {
  // 先拉取详情再打开弹窗，避免请求返回前用户对着旧数据点“确定”
  editingId.value = row.id
  newAttachments.value = []
  if (await loadEditForm(row.id)) {
    editDialogVisible.value = true
  }
}

/**
 * 提交单个项目：强制要求已绑定比赛，二次确认后进入审核流。
 * 参数 row：当前行数据。
 * 失败处理：用户取消确认直接返回；接口异常由全局拦截器提示，成功后回刷列表。
 */
async function handleSubmit(row: any) {
  if (!row.competition_id) {
    ElMessage.warning('请先编辑项目并选择参加的比赛')
    return
  }
  try {
    await ElMessageBox.confirm(`确定提交项目「${row.project_name}」进入审核流程？提交后不可修改`, '提示', { type: 'warning' })
  } catch { return }
  await submitProject(row.id)
  ElMessage.success('已提交，等待审核')
  loadData()
}

/** 撤回待教师确认的项目：撤回后回到草稿态，可重新编辑提交 */
async function handleWithdraw(row: any) {
  try {
    await ElMessageBox.confirm(`确定撤回项目「${row.project_name}」？撤回后可重新编辑提交`, '提示', { type: 'warning' })
  } catch { return }
  await withdrawProject(row.id)
  ElMessage.success('已撤回')
  loadData()
}

/** 删除单个草稿项目：不可恢复，需二次确认 */
async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除项目「${row.project_name}」？`, '提示', { type: 'warning' })
  } catch { return }
  await deleteProject(row.id)
  ElMessage.success('删除成功')
  loadData()
}

// ==================== 批量操作 ====================

/**
 * 批量导出 Excel（前端本地生成）。
 * 说明：服务端导出接口只按筛选条件导全量、不接收 ids，无法满足「只导选中行」，
 * 因此这里用 xlsx + file-saver 在前端拼装。
 * 失败处理：无选中行直接返回；生成过程为纯前端操作，不涉及请求。
 */
function handleBatchExport() {
  if (selectedRows.value.length === 0) return
  // 前端本地导出选中行（服务端导出接口只按筛选条件导全量，不接收 ids，无法满足"导出选中"）
  const exportData = selectedRows.value.map((r) => ({
    项目编号: r.project_no || '-',
    项目名称: r.project_name,
    项目类别: r.project_type_name,
    项目级别: r.project_level_name,
    负责人: r.leader_name,
    指导教师: r.teacher_name || '-',
    所属学院: r.college_name,
    预算金额: Number(r.budget_amount || 0).toFixed(2),
    状态: STATUS_LABELS[r.status] || r.status,
    创建时间: formatDateTime(r.created_at),
    提交时间: formatDateTime(r.submit_time) || '-',
  }))
  const ws = XLSX.utils.json_to_sheet(exportData)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '项目列表')
  const excelBuf = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
  const blob = new Blob([excelBuf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const fileName = `我的项目列表_${new Date().toISOString().slice(0, 10)}.xlsx`
  saveAs(blob, fileName)
  ElMessage.success(`已导出 ${selectedRows.value.length} 条数据`)
}

/**
 * 批量打印申请书：临时注入打印样式后调用浏览器打印，打印结束自动移除样式。
 * 说明：打印内容为当前表格页，筛选区与操作栏通过 no-print 隐藏。
 * 失败处理：无选中行直接返回；样式清理放在打印后延时执行，避免影响后续页面。
 */
function handleBatchPrint() {
  if (selectedRows.value.length === 0) return
  const style = document.createElement('style')
  style.className = 'print-temp-style'
  style.innerHTML = `
    @media print {
      .no-print { display: none !important; }
      body { background: #fff !important; }
      .el-table th, .el-table td { color: #333 !important; border-color: #999 !important; }
      .el-card { box-shadow: none !important; border: none !important; }
    }
  `
  document.head.appendChild(style)
  window.print()
  setTimeout(() => {
    const s = document.querySelector('.print-temp-style')
    if (s) s.remove()
  }, 500)
}

/**
 * 批量提交草稿：只对 draftSelectedIds 逐个提交，非草稿自动跳过。
 * 说明：逐个串行提交便于统计成功 / 失败数量，避免部分失败时整体回滚。
 * 失败处理：单个失败只计数不中断；完成后统一提示成功与失败条数并清空勾选。
 */
async function handleBatchSubmit() {
  if (draftSelectedIds.value.length === 0) return
  const n = draftSelectedIds.value.length
  try {
    await ElMessageBox.confirm(
      `确定提交选中的 ${n} 个草稿项目进入审核流程？提交后不可修改。（非草稿项目将被自动跳过）`,
      '批量提交确认',
      { type: 'warning' }
    )
  } catch { return }
  let success = 0
  let fail = 0
  for (const id of draftSelectedIds.value) {
    try {
      await submitProject(id)
      success++
    } catch {
      fail++
    }
  }
  ElMessage.success(`批量提交完成：成功 ${success} 个，失败 ${fail} 个`)
  selectedRows.value = []
  loadData()
}

/**
 * 批量删除草稿：只对 draftSelectedIds 逐个删除，非草稿自动跳过。
 * 说明：删除不可恢复，故先整体二次确认再串行执行。
 * 失败处理：单个失败只计数不中断；完成后提示成功与失败条数并清空勾选。
 */
async function handleBatchDelete() {
  if (draftSelectedIds.value.length === 0) return
  const n = draftSelectedIds.value.length
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${n} 个草稿项目？删除后不可恢复。（非草稿项目将被自动跳过）`,
      '批量删除确认',
      { type: 'warning' }
    )
  } catch { return }
  let success = 0
  let fail = 0
  for (const id of draftSelectedIds.value) {
    try {
      await deleteProject(id)
      success++
    } catch {
      fail++
    }
  }
  ElMessage.success(`批量删除完成：成功 ${success} 个，失败 ${fail} 个`)
  selectedRows.value = []
  loadData()
}

/** 将路由 query.status 同步到筛选条件；非法值（空 / NaN）一律视为「全部状态」 */
// 从路由 query 同步状态过滤（侧边栏流程阶段跳转 /projects?status=X）
function applyQueryStatus() {
  const raw = route.query.status
  const n = raw == null || raw === '' ? undefined : Number(raw)
  searchForm.status = n != null && !Number.isNaN(n) ? n : undefined
}

// 侧边栏再次点击其他阶段时更新筛选；watch 只改条件，实际查询由上面的防抖逻辑触发
watch(() => route.query.status, () => {
  applyQueryStatus()
})

// 首次进入：先应用 URL 上的阶段筛选，再加载列表
onMounted(() => {
  applyQueryStatus()
  loadData()
})
</script>

<style scoped>
.search-card { margin-bottom: 16px; }
.action-bar { margin-bottom: 16px; }
</style>
