<!--
  ==== 公告管理（管理员端） ====

  页面职责：发布、编辑、删除系统公告；按关键词/类型/状态筛选并分页浏览，
            查看公告详情与浏览量数据。
  角色与路由：仅 role=4 管理员可进入，路由 /admin/announcements（name: AnnouncementManage）。
            公告发布后教师、学生按公告状态和可见范围阅读；草稿(0)与已下线(2)对外不可见。
  调用接口：GET    /api/announcements        列表（page / page_size，返回 items + total）
            GET    /api/announcements/:id    详情
            POST   /api/announcements        发布
            PUT    /api/announcements/:id    编辑
            DELETE /api/announcements/:id    删除
  关键交互：新建与编辑共用弹窗，编辑前先取详情回填；正文使用富文本编辑器；
            状态码 0 草稿 / 1 已发布 / 2 已下线，优先级 1 普通 / 2 重要 / 3 紧急；
            到期时间留空表示永久有效，后端据此控制公告自动失效。
-->
<template>
  <div class="page-container">
    <!-- 区块：筛选与发布入口（关键词 / 类型 / 状态查询，右侧为发布公告按钮） -->
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

    <!-- 区块：公告列表（分页表格，含优先级、状态、发布/到期时间与行内操作） -->
    <el-card shadow="never">
      <el-table v-loading="loading" :data="list" stripe style="width:100%">
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="title" label="公告标题" min-width="240" show-overflow-tooltip />
        <el-table-column prop="announcement_type_name" label="类型" width="100" />
        <!-- 优先级：1 普通（灰）/ 2 重要（橙）/ 3 紧急（红），用于列表快速识别 -->
        <el-table-column label="优先级" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="priorityTagType(row.priority)" size="small">{{ row.priority_name }}</el-tag>
          </template>
        </el-table-column>
        <!-- 状态码：0 草稿 / 1 已发布 / 2 已下线；草稿与已下线不对教师学生展示 -->
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
      <!-- 区块：分页区（page / page_size 变化后重新请求列表） -->
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

    <!-- 区块：新建/编辑弹窗（新建与编辑共用；正文为富文本，到期时间可留空表示永久有效） -->
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

    <!-- 区块：详情抽屉（元信息 + 富文本正文，只读展示） -->
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
// ==================== 导入区 ====================
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Plus } from '@element-plus/icons-vue'
import RichEditor from '@/components/RichEditor.vue'
import RichText from '@/components/RichText.vue'
import {
  getAnnouncementList, getAnnouncementDetail, createAnnouncement, updateAnnouncement, deleteAnnouncement,
  type AnnouncementListItem, type AnnouncementDetail, type AnnouncementForm,
} from '@/api/announcement'

// ==================== 枚举与展示映射 ====================
// 公告类型 announcement_type：1 系统通知 / 2 申报通知 / 3 结果公示 / 4 其他
const typeMap: Record<number, string> = { 1: '系统通知', 2: '申报通知', 3: '结果公示', 4: '其他' }
// 公告状态 status：0 草稿 / 1 已发布 / 2 已下线
const statusMap: Record<number, string> = { 0: '草稿', 1: '已发布', 2: '已下线' }
// 公告优先级 priority：1 普通 / 2 重要 / 3 紧急
const priorityMap: Record<number, string> = { 1: '普通', 2: '重要', 3: '紧急' }

// ==================== 响应式状态 ====================
// 列表加载态：控制表格 v-loading
const loading = ref(false)
// 提交中：控制弹窗确定按钮 loading，避免重复发布/保存
const submitting = ref(false)
// 当前页公告列表，对应 GET /api/announcements 返回的 items
const list = ref<AnnouncementListItem[]>([])
// 列表总数，对应接口返回的 total，供分页组件使用
const total = ref(0)
// 当前查看的公告详情，对应 GET /api/announcements/:id
const detail = ref<AnnouncementDetail | null>(null)
// 详情抽屉显隐
const detailVisible = ref(false)
// 新建/编辑弹窗显隐
const dialogVisible = ref(false)
// 弹窗模式：true 为编辑（走 PUT），false 为新建发布（走 POST）
const isEdit = ref(false)
// 正在编辑的公告 ID；新建时为 null
const editId = ref<number | null>(null)
// el-form 实例引用，submit 时用于触发校验
const formRef = ref()

// ==================== 查询条件与分页 ====================
// 列表查询参数，直接作为 GET /api/announcements 的 query：
// page 当前页、page_size 每页条数、keyword 标题/内容搜索、类型与状态筛选
const searchForm = reactive({
  page: 1, page_size: 10,
  keyword: '',
  announcement_type: undefined as number | undefined,
  status: undefined as number | undefined,
})

// ==================== 表单模型与校验 ====================
// 新建默认值：系统通知、已发布、普通优先级、永久有效（expire_time 为 null）
const defaultForm = (): AnnouncementForm => ({
  title: '', content: '', announcement_type: 1, status: 1, priority: 1, expire_time: null,
})
// 新建/编辑共用表单模型，编辑时用详情接口返回值回填
const form = reactive<AnnouncementForm>(defaultForm())

// 必填校验：标题、正文、类型、状态、优先级；到期时间允许为空
const rules = {
  title: [{ required: true, message: '请输入公告标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入公告内容', trigger: 'blur' }],
  announcement_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }],
}

// ==================== 展示辅助函数 ====================
/** 把发布时间/到期时间格式化为 yyyy-MM-dd HH:mm，兼容 ISO 的 T 分隔符；空值显示 '-' */
function fmt(d: string | null) {
  if (!d) return '-'
  return d.replace('T', ' ').substring(0, 16)
}
/** 状态码转 el-tag 颜色：草稿灰、已发布绿、已下线红 */
function statusTagType(s: number) {
  return ({ 0: 'info', 1: 'success', 2: 'danger' } as Record<number, string>)[s] || 'info'
}
/** 优先级转 el-tag 颜色：普通灰、重要橙、紧急红，突出高风险公告 */
function priorityTagType(p: number) {
  return ({ 1: 'info', 2: 'warning', 3: 'danger' } as Record<number, string>)[p] || 'info'
}

// ==================== 数据加载与筛选 ====================
/**
 * 加载当前页公告列表。
 * 副作用：写入 loading、list、total；兼容 ApiResponse 与直接 data 两种返回结构。
 */
async function loadData() {
  loading.value = true
  try {
    const res = await getAnnouncementList(searchForm)
    const data = (res as any).data ?? res
    list.value = data.items || []
    total.value = data.total || 0
  } finally { loading.value = false }
}

/** 点击查询：先回到第 1 页再请求，避免筛选后页码越界 */
function handleSearch() { searchForm.page = 1; loadData() }
/** 重置关键词、类型、状态，并回到第 1 页重新查询 */
function handleReset() {
  searchForm.page = 1
  searchForm.keyword = ''
  searchForm.announcement_type = undefined
  searchForm.status = undefined
  loadData()
}

// ==================== 新建/编辑与提交 ====================
/**
 * 打开新建或编辑弹窗。
 * @param row 传入则为编辑，会先请求详情回填；不传则为新建，套用 defaultForm
 * 副作用：写 editId、回填 form，最终置 dialogVisible 为 true
 */
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

/**
 * 提交新建或编辑。
 * 先做 el-form 校验；编辑走 PUT，新建走 POST。
 * 副作用：校验失败直接返回；成功后提示、关闭弹窗、刷新列表。
 */
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

// ==================== 删除与详情 ====================
/**
 * 删除公告。
 * @param id 公告 ID
 * @param title 公告标题，用于确认框文案
 * 副作用：确认框、DELETE 请求、成功提示、刷新列表
 */
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

/**
 * 打开公告详情抽屉。
 * @param id 公告 ID
 * 副作用：GET 详情、写入 detail、打开抽屉
 */
async function viewDetail(id: number) {
  const r = await getAnnouncementDetail(id)
  detail.value = (r as any).data ?? r
  detailVisible.value = true
}

// ==================== 生命周期 ====================
// 首次进入按默认分页加载公告列表，保证发布/下线操作后看到最新数据
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
