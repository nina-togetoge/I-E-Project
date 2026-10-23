<!--
  系统公告 - 管理员管理页
  仅管理员可进行增删改查
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="toolbar">
        <el-form :inline="true" :model="searchForm">
          <el-form-item label="关键词">
            <el-input v-model="searchForm.keyword" placeholder="标题/内容" clearable style="width:180px" @keyup.enter="handleSearch" />
          </el-form-item>
          <el-form-item label="类型">
            <el-select v-model="searchForm.announcement_type" placeholder="全部" clearable style="width:130px">
              <el-option v-for="(label, val) in typeMap" :key="val" :label="label" :value="Number(val)" />
            </el-select>
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
        <el-button type="success" :icon="Plus" @click="openDialog()">发布公告</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="list" stripe style="width:100%">
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="title" label="公告标题" min-width="240" show-overflow-tooltip />
        <el-table-column prop="announcement_type_name" label="类型" width="100" />
        <el-table-column label="优先级" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="priorityTagType(row.priority)" size="small">{{ row.priority_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="150" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="creator_name" label="发布人" width="100" />
        <el-table-column label="发布时间" width="160">
          <template #default="{ row }">
            {{ fmt(row.publish_time || row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="到期时间" width="160">
          <template #default="{ row }">
            {{ fmt(row.expire_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="view_count" label="浏览" width="70" align="center" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row.id)">详情</el-button>
            <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
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
    <el-dialog center v-model="dialogVisible" :title="isEdit ? '编辑公告' : '发布公告'" width="720px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="公告标题" prop="title">
          <el-input v-model="form.title" maxlength="255" show-word-limit placeholder="请输入公告标题" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="公告类型" prop="announcement_type">
              <el-select v-model="form.announcement_type" style="width:100%">
                <el-option v-for="(label, val) in typeMap" :key="val" :label="label" :value="Number(val)" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="优先级" prop="priority">
              <el-select v-model="form.priority" style="width:100%">
                <el-option v-for="(label, val) in priorityMap" :key="val" :label="label" :value="Number(val)" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="状态" prop="status">
              <el-select v-model="form.status" style="width:100%">
                <el-option v-for="(label, val) in statusMap" :key="val" :label="label" :value="Number(val)" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="到期时间" prop="expire_time">
          <el-date-picker
            v-model="form.expire_time"
            type="datetime"
            placeholder="不设置则永久有效"
            style="width:100%"
            value-format="YYYY-MM-DD HH:mm:ss"
          />
        </el-form-item>
        <el-form-item label="公告内容" prop="content">
          <RichEditor v-model="form.content" min-height="300px" placeholder="请输入公告内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detail?.title || '公告详情'" size="45%" direction="rtl">
      <div v-if="detail" class="detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="类型">{{ detail.announcement_type_name }}</el-descriptions-item>
          <el-descriptions-item label="优先级">
            <el-tag :type="priorityTagType(detail.priority)" size="small">{{ detail.priority_name }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)" size="small">{{ detail.status_name }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="浏览次数">{{ detail.view_count }}</el-descriptions-item>
          <el-descriptions-item label="发布人">{{ detail.creator_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="发布时间">{{ fmt(detail.publish_time || detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="到期时间">{{ fmt(detail.expire_time) }}</el-descriptions-item>
        </el-descriptions>
        <div class="section">
          <h4>公告内容</h4>
          <RichText class="content-html" :content="detail.content" />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Plus } from '@element-plus/icons-vue'
import RichEditor from '@/components/RichEditor.vue'
import RichText from '@/components/RichText.vue'
import {
  getAnnouncementList, getAnnouncementDetail, createAnnouncement, updateAnnouncement, deleteAnnouncement,
  type AnnouncementListItem, type AnnouncementDetail, type AnnouncementForm,
} from '@/api/announcement'

const typeMap: Record<number, string> = { 1: '系统通知', 2: '申报通知', 3: '结果公示', 4: '其他' }
const statusMap: Record<number, string> = { 0: '草稿', 1: '已发布', 2: '已下线' }
const priorityMap: Record<number, string> = { 1: '普通', 2: '重要', 3: '紧急' }

const loading = ref(false)
const submitting = ref(false)
const list = ref<AnnouncementListItem[]>([])
const total = ref(0)
const detail = ref<AnnouncementDetail | null>(null)
const detailVisible = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref<number | null>(null)
const formRef = ref()

const searchForm = reactive({
  page: 1, page_size: 10,
  keyword: '',
  announcement_type: undefined as number | undefined,
  status: undefined as number | undefined,
})

const defaultForm = (): AnnouncementForm => ({
  title: '', content: '', announcement_type: 1, status: 1, priority: 1, expire_time: null,
})
const form = reactive<AnnouncementForm>(defaultForm())

const rules = {
  title: [{ required: true, message: '请输入公告标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入公告内容', trigger: 'blur' }],
  announcement_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }],
}

function fmt(d: string | null) {
  if (!d) return '-'
  return d.replace('T', ' ').substring(0, 16)
}
function statusTagType(s: number) {
  return ({ 0: 'info', 1: 'success', 2: 'danger' } as Record<number, string>)[s] || 'info'
}
function priorityTagType(p: number) {
  return ({ 1: 'info', 2: 'warning', 3: 'danger' } as Record<number, string>)[p] || 'info'
}

async function loadData() {
  loading.value = true
  try {
    const res = await getAnnouncementList(searchForm)
    const data = (res as any).data ?? res
    list.value = data.items || []
    total.value = data.total || 0
  } finally { loading.value = false }
}

function handleSearch() { searchForm.page = 1; loadData() }
function handleReset() {
  searchForm.page = 1
  searchForm.keyword = ''
  searchForm.announcement_type = undefined
  searchForm.status = undefined
  loadData()
}

async function openDialog(row?: AnnouncementListItem) {
  isEdit.value = !!row
  if (row) {
    // 先取详情再打开弹窗，避免请求返回前用户对着旧数据点“确定”
    try {
      const r = await getAnnouncementDetail(row.id)
      const d = (r as any).data ?? r
      editId.value = row.id
      Object.assign(form, {
        title: d.title, content: d.content || '',
        announcement_type: d.announcement_type, status: d.status, priority: d.priority,
        expire_time: d.expire_time || null,
      })
    } catch {
      return
    }
  } else {
    editId.value = null
    Object.assign(form, defaultForm())
  }
  dialogVisible.value = true
}

async function submit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    if (isEdit.value && editId.value) {
      await updateAnnouncement(editId.value, { ...form })
      ElMessage.success('更新成功')
    } else {
      await createAnnouncement({ ...form })
      ElMessage.success('发布成功')
    }
    dialogVisible.value = false
    loadData()
  } finally { submitting.value = false }
}

async function remove(id: number, title: string) {
  try {
    await ElMessageBox.confirm(`确定删除公告"${title}"？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await deleteAnnouncement(id)
  ElMessage.success('删除成功')
  loadData()
}

async function viewDetail(id: number) {
  const r = await getAnnouncementDetail(id)
  detail.value = (r as any).data ?? r
  detailVisible.value = true
}

onMounted(loadData)
</script>

<style scoped>
.page-container { padding: 16px; }
.filter-card { margin-bottom: 12px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
.section { margin-top: 20px; }
.section h4 { margin: 0 0 12px; font-size: 15px; color: #303133; }
.content-html { color: #606266; line-height: 1.8; }
.content-html :deep(p) { margin: 0 0 10px; }
.content-html :deep(ul), .content-html :deep(ol) { padding-left: 20px; margin: 0 0 10px; }
.content-html :deep(img) { max-width: 100%; height: auto; }
</style>
