<!--
  用户管理页面（管理员端）
  功能：用户增删改查、角色分配、批量导入、启用禁用、导出
-->
<template>
  <div class="page-container">
    <!-- 搜索栏 -->
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm" class="search-form">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="用户名/姓名/手机号" clearable />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="searchForm.role" placeholder="全部角色" clearable style="width: 120px">
            <el-option label="学生" :value="1" />
            <el-option label="指导教师" :value="2" />
            <el-option label="评审专家" :value="3" />
            <el-option label="管理员" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 120px">
            <el-option label="启用" :value="1" />
            <el-option label="禁用" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item label="学院">
          <el-select
            v-model="searchForm.college_id"
            :placeholder="userStore.isCollegeAdmin ? '本院' : '全部学院'"
            :clearable="!userStore.isCollegeAdmin"
            :disabled="userStore.isCollegeAdmin"
            style="width: 150px"
          >
            <el-option v-for="c in colleges" :key="c.id" :label="c.college_name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 操作栏 -->
    <div class="action-bar">
      <el-button type="primary" :icon="Plus" @click="handleAdd">新增用户</el-button>
      <el-button type="success" :icon="Upload" @click="openImportDialog">批量导入</el-button>
      <el-button :icon="Download" @click="handleDownloadTemplate">下载模板</el-button>
      <el-button type="warning" :icon="Delete" :disabled="selection.length === 0" @click="handleBatchDelete">
        批量删除
      </el-button>
    </div>

    <!-- 表格 -->
    <PaginationTable
      :data="tableData"
      :columns="columns"
      :total="total"
      :loading="loading"
      :selection="true"
      @page-change="handlePageChange"
      @selection-change="(val: any) => (selection = val)"
    >
      <!-- 角色列 -->
      <template #role="{ row }">
        <el-tag :type="roleTagType(row.role)">{{ roleLabel(row.role) }}</el-tag>
      </template>
      <!-- 状态列 -->
      <template #status="{ row }">
        <el-tag :type="row.status === 1 ? 'success' : 'danger'">
          {{ row.status === 1 ? '启用' : '禁用' }}
        </el-tag>
      </template>
      <!-- 操作列 -->
      <template #actions="{ row }">
        <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
        <el-button link type="warning" size="small" @click="handleToggleStatus(row)">
          {{ row.status === 1 ? '禁用' : '启用' }}
        </el-button>
        <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
      </template>
      <template #empty>
        <EmptyIllustration type="default" description="暂无用户数据" />
      </template>
    </PaginationTable>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      center
      v-model="dialogVisible"
      :title="editingUser ? '编辑用户' : '新增用户'"
      width="500px"
    >
      <el-form ref="formRef" :model="userForm" :rules="userRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="userForm.username" :disabled="!!editingUser" placeholder="请输入用户名" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item v-if="!editingUser" label="密码" prop="password">
          <el-input v-model="userForm.password" type="password" show-password placeholder="请输入密码" maxlength="6" />
          <PasswordStrength :password="userForm.password" />
        </el-form-item>
        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="userForm.real_name" placeholder="请输入姓名" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="userForm.email" placeholder="请输入邮箱" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="userForm.phone" placeholder="请输入手机号" maxlength="11" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="userForm.role" placeholder="请选择角色" style="width: 100%">
            <el-option label="学生" :value="1" />
            <el-option label="指导教师" :value="2" />
            <el-option label="评审专家" :value="3" />
            <el-option v-if="userStore.isSuperAdmin" label="系统管理员" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="userForm.role !== 4 && !userStore.isCollegeAdmin" label="学院" prop="college_id">
          <el-select v-model="userForm.college_id" placeholder="请选择学院" style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.college_name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="userForm.role !== 4 && userStore.isCollegeAdmin" label="学院" prop="college_id">
          <el-select v-model="userForm.college_id" placeholder="本院" disabled style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.college_name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog center v-model="importDialogVisible" title="批量导入用户" width="900px" @close="closeImportDialog">
      <el-alert title="请先下载模板，按模板格式填写后上传" type="info" :closable="false" show-icon style="margin-bottom: 16px;" />
      
      <el-upload
        ref="uploadRef"
        drag
        :limit="1"
        :accept="['.xlsx', '.xls']"
        :auto-upload="false"
        :on-change="handleFileSelect"
        :on-remove="handleFileRemove"
        :file-list="uploadFileList"
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">拖拽 Excel 文件到此处，或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">仅支持 .xlsx / .xls 格式</div>
        </template>
      </el-upload>

      <!-- 导入预览区域 -->
      <div v-if="previewData.length" class="preview-area">
        <el-divider content-position="left">
          <span style="font-weight: 600;">导入预览（显示前20行，共 {{ previewData.length }} 行）</span>
        </el-divider>
        
        <el-alert
          v-if="errorCount > 0"
          :title="`存在 ${errorCount} 行错误，请修正后重新上传`"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom: 12px;"
        />
        <el-alert
          v-else
          title="校验通过，可以确认导入"
          type="success"
          :closable="false"
          show-icon
          style="margin-bottom: 12px;"
        />

        <el-table
          :data="previewData.slice(0, 20)"
          size="small"
          border
          stripe
          max-height="360"
          :row-class-name="rowClassName"
        >
          <el-table-column type="index" label="#" width="50" align="center" />
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column prop="real_name" label="姓名" min-width="100" />
          <el-table-column prop="role" label="角色" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="roleTagType(Number(row.role))">{{ roleLabel(Number(row.role)) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="email" label="邮箱" min-width="160" />
          <el-table-column prop="phone" label="手机号" min-width="120" />
          <el-table-column prop="college_id" label="学院ID" width="90" align="center" />
          <el-table-column prop="_error" label="错误" min-width="180">
            <template #default="{ row }">
              <span v-if="row._error" style="color: #f56c6c;">❌ {{ row._error }}</span>
              <span v-else style="color: #67c23a;">✅ 通过</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="preview-summary">
          <el-tag type="info">共 {{ previewData.length }} 行</el-tag>
          <el-tag type="success">✅ 通过 {{ passCount }} 行</el-tag>
          <el-tag type="danger">❌ 错误 {{ errorCount }} 行</el-tag>
        </div>
      </div>

      <template #footer>
        <el-button @click="closeImportDialog">取消</el-button>
        <el-button
          type="primary"
          :loading="importLoading"
          :disabled="!selectedFile || errorCount > 0"
          @click="handleConfirmImport"
        >
          {{ errorCount > 0 ? '请修正错误后重新上传' : '确认导入' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules, type UploadUserFile } from 'element-plus'
import { Search, Refresh, Plus, Upload, Download, Delete } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import PasswordStrength from '@/components/PasswordStrength.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import {
  getUserList, createUser, updateUser, deleteUser
} from '@/api/user'
import { getColleges } from '@/api/auth'
import { ROLE_LABELS, ROLES } from '@/api/types'
import * as XLSX from 'xlsx'
import { post } from '@/utils/request'
import { formatDateTime } from '@/utils/format'
import {
  passwordValidator,
  phoneValidator,
  emailValidator,
  requiredValidator,
  isValidPhone,
  isValidEmail,
  isValidPassword,
} from '@/utils/validators'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

interface PreviewRow {
  username?: string
  real_name?: string
  role?: number | string
  email?: string
  phone?: string
  college_id?: number | string
  password?: string
  _error?: string
  _hasError?: boolean
}

const searchForm = reactive({
  keyword: '',
  role: undefined as number | undefined,
  status: undefined as number | undefined,
  college_id: undefined as number | undefined,
})

// 学院管理员进入页面时，默认锁定自己的学院作为搜索条件
function initCollegeScopeDefaults() {
  if (userStore.isCollegeAdmin) {
    searchForm.college_id = userStore.collegeId ?? undefined
  }
}

function handleSearch() {
  page.value = 1
  loadData()
}

function handleReset() {
  searchForm.keyword = ''
  searchForm.role = undefined
  searchForm.status = undefined
  searchForm.college_id = userStore.isCollegeAdmin ? (userStore.collegeId ?? undefined) : undefined
  handleSearch()
}

const tableData = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const selection = ref<any[]>([])

const columns: TableColumn[] = [
  { prop: 'username', label: '用户名', minWidth: 120 },
  { prop: 'real_name', label: '姓名', minWidth: 100 },
  { prop: 'role', label: '角色', slot: 'role', minWidth: 100 },
  { prop: 'college_name', label: '学院', minWidth: 120 },
  { prop: 'email', label: '邮箱', minWidth: 150 },
  { prop: 'phone', label: '手机号', minWidth: 120 },
  { prop: 'status', label: '状态', slot: 'status', width: 150 },
  { prop: 'created_at', label: '创建时间', minWidth: 160, formatter: (val: string) => formatDateTime(val) },
]

async function loadData() {
  loading.value = true
  try {
    const res = await getUserList({
      page: page.value,
      page_size: pageSize.value,
      ...searchForm,
    })
    tableData.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

const colleges = ref<any[]>([])
async function loadColleges() {
  const res = await getColleges()
  colleges.value = res.data || []
}

const dialogVisible = ref(false)
const editingUser = ref<any>(null)
const formRef = ref<FormInstance>()
const submitLoading = ref(false)

const userForm = reactive({
  username: '',
  password: '',
  real_name: '',
  email: '',
  phone: '',
  role: 1,
  college_id: undefined as number | undefined,
})

const userRules: FormRules = {
  username: [{ validator: requiredValidator('用户名'), trigger: 'blur' }],
  password: [{ validator: passwordValidator(true, '初始密码'), trigger: 'blur' }],
  real_name: [{ validator: requiredValidator('姓名'), trigger: 'blur' }],
  email: [{ validator: emailValidator(false, '邮箱'), trigger: 'blur' }],
  phone: [{ validator: phoneValidator(false, '手机号'), trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

function handleAdd() {
  editingUser.value = null
  const defaultRole = userStore.isCollegeAdmin ? 1 : 1
  const defaultCollege = userStore.isCollegeAdmin ? (userStore.collegeId ?? undefined) : undefined
  Object.assign(userForm, {
    username: '', password: '', real_name: '', email: '', phone: '',
    role: defaultRole, college_id: defaultCollege,
  })
  dialogVisible.value = true
}

function handleEdit(row: any) {
  editingUser.value = row
  Object.assign(userForm, {
    username: row.username,
    password: '',
    real_name: row.real_name,
    email: row.email || '',
    phone: row.phone || '',
    role: row.role,
    college_id: row.college_id,
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitLoading.value = true
    try {
      // 学院管理员：防御性修正，强制设置为自己的学院，且禁止 ADMIN 角色
      let payloadRole = userForm.role
      let payloadCollege = userForm.college_id
      if (userStore.isCollegeAdmin) {
        payloadCollege = userStore.collegeId ?? undefined
        if (payloadRole === 4) {
          ElMessage.error('学院管理员无法创建/编辑系统管理员账号')
          return
        }
      }
      if (editingUser.value) {
        await updateUser(editingUser.value.id, {
          real_name: userForm.real_name,
          email: userForm.email,
          phone: userForm.phone,
          role: payloadRole,
          college_id: payloadCollege,
        })
        ElMessage.success('修改成功')
      } else {
        await createUser({
          username: userForm.username,
          password: userForm.password,
          real_name: userForm.real_name,
          email: userForm.email,
          phone: userForm.phone,
          role: payloadRole,
          college_id: payloadCollege,
        })
        ElMessage.success('创建成功')
      }
      dialogVisible.value = false
      loadData()
    } finally {
      submitLoading.value = false
    }
  })
}

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确定删除用户「${row.real_name}」吗？`, '提示', { type: 'warning' })
  await deleteUser(row.id)
  ElMessage.success('删除成功')
  loadData()
}

async function handleBatchDelete() {
  await ElMessageBox.confirm(`确定删除选中的 ${selection.value.length} 个用户吗？`, '提示', { type: 'warning' })
  for (const user of selection.value) {
    await deleteUser(user.id)
  }
  ElMessage.success(`已删除 ${selection.value.length} 个用户`)
  loadData()
}

async function handleToggleStatus(row: any) {
  await updateUser(row.id, { status: row.status === 1 ? 0 : 1 })
  ElMessage.success(row.status === 1 ? '已禁用' : '已启用')
  loadData()
}

// ==================== F19 批量导入 预览/校验 ====================
const importDialogVisible = ref(false)
const importLoading = ref(false)
const uploadRef = ref()
const uploadFileList = ref<UploadUserFile[]>([])
const selectedFile = ref<File | null>(null)
const previewData = ref<PreviewRow[]>([])

const errorCount = computed(() => previewData.value.filter((r) => r._hasError).length)
const passCount = computed(() => previewData.value.length - errorCount.value)

function openImportDialog() {
  importDialogVisible.value = true
}

function closeImportDialog() {
  importDialogVisible.value = false
  uploadFileList.value = []
  selectedFile.value = null
  previewData.value = []
}

async function handleFileSelect(file: UploadUserFile) {
  const raw = file.raw as File
  if (!raw) return
  selectedFile.value = raw
  await parseAndPreview(raw)
}

function handleFileRemove() {
  selectedFile.value = null
  previewData.value = []
}

async function parseAndPreview(file: File) {
  try {
    const buffer = await file.arrayBuffer()
    const wb = XLSX.read(buffer, { type: 'array' })
    const firstSheet = wb.Sheets[wb.SheetNames[0]]
    const json: any[] = XLSX.utils.sheet_to_json(firstSheet, { defval: '' })
    const rows: PreviewRow[] = json.map((item) => ({
      username: String(item.username ?? item['用户名'] ?? item.user_name ?? '').trim(),
      real_name: String(item.real_name ?? item['姓名'] ?? item.name ?? '').trim(),
      role: item.role ?? item['角色'] ?? item.user_role ?? '',
      email: String(item.email ?? item['邮箱'] ?? '').trim(),
      phone: String(item.phone ?? item['手机号'] ?? item.telephone ?? '').trim(),
      college_id: item.college_id ?? item['学院ID'] ?? item['学院'] ?? '',
      password: String(item.password ?? item['密码'] ?? item.initial_password ?? '').trim(),
      _error: '',
      _hasError: false,
    }))
    validatePreviewRows(rows)
    previewData.value = rows
  } catch (e) {
    ElMessage.error('文件解析失败，请检查文件格式')
    selectedFile.value = null
    uploadFileList.value = []
  }
}

function validatePreviewRows(rows: PreviewRow[]) {
  const usernameSet = new Set<string>()
  const duplicateMap = new Map<string, number>()
  for (const r of rows) {
    const u = r.username || ''
    if (u) {
      if (usernameSet.has(u)) {
        duplicateMap.set(u, (duplicateMap.get(u) || 0) + 1)
      } else {
        usernameSet.add(u)
      }
    }
  }
  for (const r of rows) {
    const errors: string[] = []
    if (!r.username) errors.push('缺少用户名')
    if (!r.real_name) errors.push('缺少姓名')
    if (r.username && duplicateMap.has(r.username)) errors.push('用户名重复')
    const roleNum = Number(r.role)
    if (![1, 2, 3, 4].includes(roleNum)) errors.push('角色无效（需为1-4）')
    // 学院管理员：禁止导入 ADMIN (role=4)，且学院必须与自己一致
    if (userStore.isCollegeAdmin) {
      if (roleNum === 4) errors.push('学院管理员无法导入系统管理员账号')
      const userCollege = userStore.collegeId
      if (userCollege != null) {
        const collegeVal = r.college_id === '' ? null : Number(r.college_id)
        if (collegeVal != null && collegeVal !== userCollege) {
          errors.push(`学院必须为本院(ID=${userCollege})`)
        }
      }
    }
    if (!isValidPhone(r.phone)) errors.push('手机号格式不正确（需为11位中国大陆手机号）')
    if (!isValidEmail(r.email)) errors.push('邮箱格式不正确')
    if (!isValidPassword(r.password)) errors.push('密码格式不正确（需为6位纯数字）')
    if (r.college_id != null && r.college_id !== '' && Number.isNaN(Number(r.college_id))) {
      errors.push('学院ID必须是数字')
    }
    if (errors.length > 0) {
      r._error = errors.join('；')
      r._hasError = true
    }
  }
}

function rowClassName({ row }: { row: PreviewRow }) {
  return row._hasError ? 'error-row' : ''
}

async function handleConfirmImport() {
  if (!selectedFile.value || errorCount.value > 0) return
  importLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const res = await post<any>('/api/excel/import/user', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (res.code === 200) {
      ElMessage.success('导入完成')
      closeImportDialog()
      loadData()
    } else {
      ElMessage.error(res.message || '导入失败')
    }
  } catch {
    ElMessage.error('导入失败，请稍后重试')
  } finally {
    importLoading.value = false
  }
}

async function handleDownloadTemplate() {
  window.open('/api/excel/template/user', '_blank')
}

function roleLabel(role: number) {
  return ROLE_LABELS[role] || '未知'
}

function roleTagType(role: number): string {
  const map: Record<number, string> = { 1: '', 2: 'success', 3: 'warning', 4: 'danger' }
  return map[role] || 'info'
}

onMounted(() => {
  initCollegeScopeDefaults()
  loadData()
  loadColleges()
})
</script>

<style scoped>
.search-card {
  margin-bottom: 16px;
}

.action-bar {
  margin-bottom: 16px;
  display: flex;
  gap: 8px;
}

.preview-area {
  margin-top: 16px;
}

.preview-summary {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

:deep(.error-row) {
  background-color: #fef0f0 !important;
}

:deep(.error-row td.el-table__cell) {
  background-color: #fef0f0 !important;
}
</style>
