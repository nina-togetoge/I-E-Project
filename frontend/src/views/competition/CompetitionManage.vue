<!--
  创新创业大赛 - 管理员管理页
  仅超级管理员可进行增删改查
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="toolbar">
        <el-form :inline="true" :model="searchForm">
          <el-form-item label="关键词">
            <el-input v-model="searchForm.keyword" placeholder="比赛名称/主办方" clearable style="width:180px" @keyup.enter="handleSearch" />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="searchForm.status" placeholder="全部" clearable style="width:120px">
              <el-option v-for="(label, val) in statusMap" :key="val" :label="label" :value="Number(val)" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
            <el-button :icon="Refresh" @click="handleReset">重置</el-button>
          </el-form-item>
        </el-form>
        <el-button type="success" :icon="Plus" @click="openDialog()">新建比赛</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="list" stripe style="width:100%">
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="title" label="比赛名称" min-width="200" />
        <el-table-column prop="session" label="届次" width="100">
          <template #default="{ row }">{{ row.session || '-' }}</template>
        </el-table-column>
        <el-table-column prop="competition_type_name" label="类型" width="110" />
        <el-table-column prop="level_name" label="级别" width="90" />
        <el-table-column prop="organizer" label="主办方" width="140" />
        <el-table-column label="报名时间" width="220">
          <template #default="{ row }">
            {{ fmt(row.registration_start) }} ~ {{ fmt(row.registration_end) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ row.status_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="view_count" label="浏览" width="80" align="center" />
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-dropdown trigger="click" @command="(cmd: string) => handleRowCommand(cmd, row)">
              <el-button link type="primary">查看</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="view">查看详情</el-dropdown-item>
                  <el-dropdown-item command="edit">编辑</el-dropdown-item>
                  <el-dropdown-item command="status" divided>修改状态</el-dropdown-item>
                  <el-dropdown-item v-if="row.level === 1" command="awards" :disabled="awardLoading">生成获奖名单</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="searchForm.page"
          v-model:page-size="searchForm.page_size"
          :page-sizes="[10, 20, 50]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog center v-model="dialogVisible" :title="isEdit ? '编辑比赛' : '新建比赛'" width="780px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="比赛名称" prop="title">
          <el-input v-model="form.title" maxlength="255" show-word-limit />
        </el-form-item>
        <el-form-item label="届次" prop="session">
          <el-input v-model="form.session" placeholder="如 2026届" maxlength="32" style="width:220px" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="比赛类型" prop="competition_type">
              <el-select v-model="form.competition_type" style="width:100%">
                <el-option v-for="(label, val) in typeMap" :key="val" :label="label" :value="Number(val)" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="级别" prop="level">
              <el-select v-model="form.level" style="width:100%">
                <el-option v-for="(label, val) in levelMap" :key="val" :label="label" :value="Number(val)" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="主办方">
              <el-input v-model="form.organizer" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="承办方">
              <el-input v-model="form.co_organizer" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="报名开始">
              <el-date-picker v-model="form.registration_start" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="报名截止">
              <el-date-picker v-model="form.registration_end" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="比赛开始">
              <el-date-picker v-model="form.competition_start" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="比赛结束">
              <el-date-picker v-model="form.competition_end" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-divider content-position="left">项目流程时间表（截止日驱动锁定；不填则该阶段不锁）</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="学院初审日">
              <el-date-picker v-model="form.college_review_date" type="date" value-format="YYYY-MM-DD" style="width:100%" placeholder="兼指导教师确认截止日" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="校级复审日">
              <el-date-picker v-model="form.university_review_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="专家评审日">
              <el-date-picker v-model="form.expert_review_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="中期截止日">
              <el-date-picker v-model="form.midterm_deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" placeholder="中期报告提交/审核截止" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="结题截止日">
              <el-date-picker v-model="form.final_deadline" type="date" value-format="YYYY-MM-DD" style="width:100%" placeholder="结题报告提交/审核截止" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="比赛地点">
              <el-input v-model="form.location" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系方式">
              <el-input v-model="form.contact" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="封面图URL">
          <el-input v-model="form.cover_image" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="官方链接">
          <el-input v-model="form.official_url" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="比赛简介">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="参赛要求">
          <el-input v-model="form.requirements" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="奖项设置">
          <el-input v-model="form.rewards" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="form.status" style="width:200px">
            <el-option v-for="(label, val) in statusMap" :key="val" :label="label" :value="Number(val)" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detail?.title || '比赛详情'" size="40%" direction="rtl">
      <div v-if="detail" class="detail-content">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="届次">{{ detail.session || '-' }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ detail.competition_type_name }}</el-descriptions-item>
          <el-descriptions-item label="级别">{{ detail.level_name }}</el-descriptions-item>
          <el-descriptions-item label="状态"><el-tag :type="statusTagType(detail.status)">{{ detail.status_name }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="主办方">{{ detail.organizer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="承办方">{{ detail.co_organizer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="报名时间">{{ fmt(detail.registration_start) }} ~ {{ fmt(detail.registration_end) }}</el-descriptions-item>
          <el-descriptions-item label="比赛时间">{{ fmt(detail.competition_start) }} ~ {{ fmt(detail.competition_end) }}</el-descriptions-item>
          <el-descriptions-item label="学院初审日">{{ fmt(detail.college_review_date) }}</el-descriptions-item>
          <el-descriptions-item label="校级复审日">{{ fmt(detail.university_review_date) }}</el-descriptions-item>
          <el-descriptions-item label="专家评审日">{{ fmt(detail.expert_review_date) }}</el-descriptions-item>
          <el-descriptions-item label="中期截止日">{{ fmt(detail.midterm_deadline) }}</el-descriptions-item>
          <el-descriptions-item label="结题截止日">{{ fmt(detail.final_deadline) }}</el-descriptions-item>
          <el-descriptions-item label="地点">{{ detail.location || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系方式">{{ detail.contact || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detail.description" class="section"><h4>简介</h4><p>{{ detail.description }}</p></div>
        <div v-if="detail.requirements" class="section"><h4>参赛要求</h4><p>{{ detail.requirements }}</p></div>
        <div v-if="detail.rewards" class="section"><h4>奖项设置</h4><p>{{ detail.rewards }}</p></div>
      </div>
    </el-drawer>

    <!-- 获奖名单生成结果 -->
    <el-dialog
      center
      v-model="awardVisible"
      :title="awardResult ? `获奖名单 · ${awardResult.competition_title}${awardResult.session ? '（' + awardResult.session + '）' : ''}` : '获奖名单'"
      width="780px"
    >
      <template v-if="awardResult">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="award-tip"
          :title="`共生成 ${awardResult.total_awarded} 项获奖成果（已登记为「竞赛获奖」成果，计入结题成果数量门槛）。名次 1/2/3 → 校级一/二/三等奖，其后顺次 7 个参与奖；仅校级比赛参与自动分配。`"
        />
        <div v-for="g in awardResult.groups" :key="g.college_id" class="award-group">
          <h4>{{ g.college_name || ('学院#' + g.college_id) }}（{{ g.items.length }} 项）</h4>
          <el-table :data="g.items" size="small" border>
            <el-table-column prop="rank" label="名次" width="70" align="center" />
            <el-table-column prop="project_name" label="项目名称" min-width="200" />
            <el-table-column prop="average_score" label="平均分" width="100" align="center" />
            <el-table-column prop="award_level" label="获奖等级" width="130" />
          </el-table>
        </div>
        <el-empty v-if="awardResult.groups.length === 0" description="无符合自动分配条件的项目" :image-size="60" />
      </template>
      <template #footer>
        <el-button @click="awardVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 修改状态弹窗 -->
    <el-dialog center v-model="statusVisible" width="460px" class="status-dialog" :close-on-click-modal="false">
      <template #header>
        <div class="sd-header">
          <span class="sd-header-icon"><el-icon><EditPen /></el-icon></span>
          <span>修改比赛状态</span>
        </div>
      </template>

      <div v-if="statusRow" class="sd-body">
        <div class="sd-target" :title="statusRow.title">
          <span class="sd-target-tag">比赛</span>
          <span class="sd-target-name">{{ statusRow.title }}</span>
        </div>
        <div class="sd-options">
          <div
            v-for="(label, val) in statusMap"
            :key="val"
            class="sd-option"
            :class="{ 'is-active': statusNew === Number(val) }"
            @click="statusNew = Number(val)"
          >
            <span class="sd-dot" :style="{ background: statusColor(Number(val)) }"></span>
            <span class="sd-info">
              <span class="sd-label">{{ label }}</span>
              <span class="sd-desc">{{ statusDesc(Number(val)) }}</span>
            </span>
            <el-icon v-if="statusNew === Number(val)" class="sd-check"><Check /></el-icon>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="statusVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitStatus">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Plus, EditPen, Check } from '@element-plus/icons-vue'
import {
  getCompetitionList, getCompetitionDetail, createCompetition, updateCompetition, deleteCompetition,
  updateCompetitionStatus, generateCompetitionAwards,
  type CompetitionListItem, type CompetitionDetail, type CompetitionForm, type AwardGenerateResult,
} from '@/api/competition'

const typeMap: Record<number, string> = { 1: '创新训练类', 2: '创业实践类', 3: '学科竞赛类', 4: '综合类' }
const levelMap: Record<number, string> = { 1: '校级', 2: '省级', 3: '国家级', 4: '国际级' }
const statusMap: Record<number, string> = { 0: '草稿', 1: '报名中', 2: '进行中', 3: '已结束', 4: '已取消' }

const loading = ref(false)
const submitting = ref(false)
const list = ref<CompetitionListItem[]>([])
const total = ref(0)
const detail = ref<CompetitionDetail | null>(null)
const detailVisible = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref<number | null>(null)
const formRef = ref()
// 获奖名单生成
const awardLoading = ref(false)
const awardVisible = ref(false)
const awardResult = ref<AwardGenerateResult | null>(null)
// 修改状态弹窗
const statusVisible = ref(false)
const statusRow = ref<CompetitionListItem | null>(null)
const statusNew = ref<number>(1)

async function handleGenerateAwards(row: CompetitionListItem) {
  const label = `${row.title}${row.session ? '（' + row.session + '）' : ''}`
  try {
    await ElMessageBox.confirm(
      `将为「${label}」按本院排名自动生成获奖名单（若已生成会自动刷新既有自动获奖记录）。确定生成？`,
      '生成获奖名单',
      { type: 'warning', confirmButtonText: '确定生成', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  awardLoading.value = true
  try {
    const res = await generateCompetitionAwards(row.id)
    awardResult.value = res.data
    awardVisible.value = true
    ElMessage.success(`已生成获奖名单，共 ${res.data.total_awarded} 项`)
  } finally {
    awardLoading.value = false
  }
}

const searchForm = reactive({ page: 1, page_size: 10, keyword: '', status: undefined as number | undefined })

const defaultForm = (): CompetitionForm => ({
  title: '', session: '', competition_type: 1, level: 1, status: 0,
  organizer: '', co_organizer: '', description: '', requirements: '', rewards: '',
  registration_start: '', registration_end: '', competition_start: '', competition_end: '',
  college_review_date: '', university_review_date: '', expert_review_date: '',
  midterm_deadline: '', final_deadline: '',
  location: '', contact: '', cover_image: '', official_url: '',
})
const form = reactive<CompetitionForm>(defaultForm())

const rules = {
  title: [{ required: true, message: '请输入比赛名称', trigger: 'blur' }],
  competition_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  level: [{ required: true, message: '请选择级别', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
}

function fmt(d: string | null) { return d ? d.substring(0, 10) : '-' }
function statusTagType(s: number) {
  return ({ 0: 'info', 1: 'success', 2: 'warning', 3: '', 4: 'danger' } as Record<number, string>)[s] || 'info'
}
function statusColor(s: number) {
  return ({ 0: '#909399', 1: '#67C23A', 2: '#E6A23C', 3: '#409EFF', 4: '#F56C6C' } as Record<number, string>)[s] || '#909399'
}
function statusDesc(s: number) {
  return ({ 0: '尚未发布，学生不可见', 1: '开放报名，学生可申报', 2: '报名已截止，进行中', 3: '比赛结束并完成结项', 4: '比赛取消或提前终止' } as Record<number, string>)[s] || ''
}

async function loadData() {
  loading.value = true
  try {
    const res = await getCompetitionList(searchForm)
    const data = (res as any).data ?? res
    list.value = data.items || []
    total.value = data.total || 0
  } finally { loading.value = false }
}

function handleSearch() { searchForm.page = 1; loadData() }
function handleReset() { searchForm.page = 1; searchForm.keyword = ''; searchForm.status = undefined; loadData() }

function openDialog(row?: CompetitionListItem) {
  isEdit.value = !!row
  if (row) {
    editId.value = row.id
    getCompetitionDetail(row.id).then((r) => {
      const d = (r as any).data ?? r
      Object.assign(form, {
        title: d.title, session: d.session || '', competition_type: d.competition_type, level: d.level, status: d.status,
        organizer: d.organizer || '', co_organizer: d.co_organizer || '',
        description: d.description || '', requirements: d.requirements || '', rewards: d.rewards || '',
        registration_start: d.registration_start || '', registration_end: d.registration_end || '',
        competition_start: d.competition_start || '', competition_end: d.competition_end || '',
        college_review_date: d.college_review_date || '', university_review_date: d.university_review_date || '',
        expert_review_date: d.expert_review_date || '', midterm_deadline: d.midterm_deadline || '',
        final_deadline: d.final_deadline || '',
        location: d.location || '', contact: d.contact || '',
        cover_image: d.cover_image || '', official_url: d.official_url || '',
      })
    })
  } else {
    editId.value = null
    Object.assign(form, defaultForm())
  }
  dialogVisible.value = true
}

/** 时间表顺序校验：与后端 CompetitionCreate.check_dates 保持一致 */
function validateDateOrder(): string {
  const ts = (v?: string) => (v ? new Date(v).getTime() : null)
  const later = (a?: string, b?: string) => {
    const x = ts(a); const y = ts(b)
    return x !== null && y !== null && x > y
  }
  if (later(form.registration_start, form.registration_end)) return '报名开始日期不能晚于报名截止日期'
  if (later(form.competition_start, form.competition_end)) return '比赛开始日期不能晚于比赛结束日期'
  const reviews = [form.college_review_date, form.university_review_date, form.expert_review_date]
    .filter(Boolean) as string[]
  for (let i = 1; i < reviews.length; i++) {
    if (ts(reviews[i])! < ts(reviews[i - 1])!) {
      return '学院初审、校级复审、专家评审的审核日须按时间先后填写'
    }
  }
  if (later(form.midterm_deadline, form.final_deadline)) return '中期截止日不能晚于结题截止日'
  return ''
}

async function submit() {
  const dateError = validateDateOrder()
  if (dateError) { ElMessage.warning(dateError); return }
  await formRef.value.validate()
  submitting.value = true
  try {
    // 空字符串日期字段转为 undefined，避免后端 date 校验失败
    const payload = { ...form }
    const dateFields = ['registration_start', 'registration_end', 'competition_start', 'competition_end',
      'college_review_date', 'university_review_date', 'expert_review_date', 'midterm_deadline', 'final_deadline']
    dateFields.forEach((k) => {
      if (!payload[k as keyof CompetitionForm]) (payload as any)[k] = undefined
    })
    // 届次为空时提交 null，避免写入空字符串
    if (!payload.session) (payload as any).session = undefined
    if (isEdit.value && editId.value) {
      await updateCompetition(editId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await createCompetition(payload)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadData()
  } finally { submitting.value = false }
}

async function remove(id: number, title: string) {
  await ElMessageBox.confirm(`确定删除比赛"${title}"？`, '提示', { type: 'warning' })
  await deleteCompetition(id)
  ElMessage.success('删除成功')
  loadData()
}

async function changeStatus(id: number, status: number) {
  await updateCompetitionStatus(id, status)
  ElMessage.success('状态更新成功')
  loadData()
}

async function viewDetail(id: number) {
  const r = await getCompetitionDetail(id)
  detail.value = (r as any).data ?? r
  // 更新列表中对应项的浏览次数
  const idx = list.value.findIndex(item => item.id === id)
  if (idx !== -1 && detail.value) {
    list.value[idx].view_count = detail.value.view_count
  }
  detailVisible.value = true
}

function handleRowCommand(cmd: string, row: CompetitionListItem) {
  if (cmd === 'view') return viewDetail(row.id)
  if (cmd === 'edit') return openDialog(row)
  if (cmd === 'awards') return handleGenerateAwards(row)
  if (cmd === 'delete') return remove(row.id, row.title)
  if (cmd === 'status') {
    statusRow.value = row
    statusNew.value = row.status
    statusVisible.value = true
  }
}

async function submitStatus() {
  if (!statusRow.value) return
  submitting.value = true
  try {
    await changeStatus(statusRow.value.id, statusNew.value)
    statusVisible.value = false
  } finally {
    submitting.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.page-container { padding: 16px; }
.filter-card { margin-bottom: 12px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
/* 操作列中的下拉触发按钮（状态）与相邻 link 按钮垂直对齐 */
:deep(.el-dropdown) { vertical-align: middle; }
.section { margin-top: 18px; }
.section h4 { margin: 0 0 8px; }
.section p { color: #606266; line-height: 1.7; white-space: pre-wrap; }
.award-tip { margin-bottom: 16px; }
.award-group { margin-bottom: 16px; }
.award-group h4 { margin: 0 0 8px; }
/* 修改状态弹窗 */
.status-dialog :deep(.el-dialog__header) { padding-bottom: 0; }
.sd-header { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 600; color: #303133; }
.sd-header-icon { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 8px; background: #ecf5ff; color: #409eff; font-size: 16px; }
.sd-body { padding: 4px 0 8px; }
.sd-target { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #f5f7fa; border-radius: 8px; margin-bottom: 14px; }
.sd-target-tag { flex-shrink: 0; font-size: 12px; color: #409eff; background: #ecf5ff; padding: 2px 8px; border-radius: 4px; }
.sd-target-name { font-size: 14px; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sd-options { display: flex; flex-direction: column; gap: 8px; }
.sd-option { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid #e4e7ed; border-radius: 8px; cursor: pointer; transition: all .2s; }
.sd-option:hover { border-color: #409eff; background: #f0f7ff; }
.sd-option.is-active { border-color: #409eff; background: #f0f7ff; box-shadow: inset 0 0 0 1px #409eff; }
.sd-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.sd-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.sd-label { font-size: 14px; color: #303133; font-weight: 500; }
.sd-desc { font-size: 12px; color: #909399; }
.sd-check { color: #409eff; font-size: 16px; }
</style>
