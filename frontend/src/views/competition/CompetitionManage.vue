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
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row.id)">详情</el-button>
            <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-dropdown @command="(s) => changeStatus(row.id, s)">
              <el-button link type="warning">状态</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-for="(label, val) in statusMap" :key="val" :command="Number(val)">{{ label }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button link type="danger" @click="remove(row.id, row.title)">删除</el-button>
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
          <el-descriptions-item label="类型">{{ detail.competition_type_name }}</el-descriptions-item>
          <el-descriptions-item label="级别">{{ detail.level_name }}</el-descriptions-item>
          <el-descriptions-item label="状态"><el-tag :type="statusTagType(detail.status)">{{ detail.status_name }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="主办方">{{ detail.organizer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="承办方">{{ detail.co_organizer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="报名时间">{{ fmt(detail.registration_start) }} ~ {{ fmt(detail.registration_end) }}</el-descriptions-item>
          <el-descriptions-item label="比赛时间">{{ fmt(detail.competition_start) }} ~ {{ fmt(detail.competition_end) }}</el-descriptions-item>
          <el-descriptions-item label="地点">{{ detail.location || '-' }}</el-descriptions-item>
          <el-descriptions-item label="联系方式">{{ detail.contact || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detail.description" class="section"><h4>简介</h4><p>{{ detail.description }}</p></div>
        <div v-if="detail.requirements" class="section"><h4>参赛要求</h4><p>{{ detail.requirements }}</p></div>
        <div v-if="detail.rewards" class="section"><h4>奖项设置</h4><p>{{ detail.rewards }}</p></div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Plus } from '@element-plus/icons-vue'
import {
  getCompetitionList, getCompetitionDetail, createCompetition, updateCompetition, deleteCompetition,
  updateCompetitionStatus, type CompetitionListItem, type CompetitionDetail, type CompetitionForm,
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

const searchForm = reactive({ page: 1, page_size: 10, keyword: '', status: undefined as number | undefined })

const defaultForm = (): CompetitionForm => ({
  title: '', competition_type: 1, level: 1, status: 0,
  organizer: '', co_organizer: '', description: '', requirements: '', rewards: '',
  registration_start: '', registration_end: '', competition_start: '', competition_end: '',
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
        title: d.title, competition_type: d.competition_type, level: d.level, status: d.status,
        organizer: d.organizer || '', co_organizer: d.co_organizer || '',
        description: d.description || '', requirements: d.requirements || '', rewards: d.rewards || '',
        registration_start: d.registration_start || '', registration_end: d.registration_end || '',
        competition_start: d.competition_start || '', competition_end: d.competition_end || '',
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

async function submit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    // 空字符串日期字段转为 undefined，避免后端 date 校验失败
    const payload = { ...form }
    const dateFields = ['registration_start', 'registration_end', 'competition_start', 'competition_end']
    dateFields.forEach((k) => {
      if (!payload[k as keyof CompetitionForm]) (payload as any)[k] = undefined
    })
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

onMounted(loadData)
</script>

<style scoped>
.page-container { padding: 16px; }
.filter-card { margin-bottom: 12px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
.section { margin-top: 18px; }
.section h4 { margin: 0 0 8px; }
.section p { color: #606266; line-height: 1.7; white-space: pre-wrap; }
</style>
