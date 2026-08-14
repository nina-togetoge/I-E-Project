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
          <el-select v-model="searchForm.college_id" placeholder="全部学院" clearable style="width: 150px">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
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
      <el-button type="success" :icon="Upload" @click="importDialogVisible = true">批量导入</el-button>
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
    </PaginationTable>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingUser ? '编辑用户' : '新增用户'"
      width="500px"
    >
      <el-form ref="formRef" :model="userForm" :rules="userRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="userForm.username" :disabled="!!editingUser" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item v-if="!editingUser" label="密码" prop="password">
          <el-input v-model="userForm.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="userForm.real_name" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="userForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="userForm.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="userForm.role" placeholder="请选择角色" style="width: 100%">
            <el-option label="学生" :value="1" />
            <el-option label="指导教师" :value="2" />
            <el-option label="评审专家" :value="3" />
            <el-option label="系统管理员" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="userForm.role !== 4" label="学院" prop="college_id">
          <el-select v-model="userForm.college_id" placeholder="请选择学院" style="width: 100%">
            <el-option v-for="c in colleges" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog v-model="importDialogVisible" title="批量导入用户" width="500px">
      <el-alert title="请先下载模板，按模板格式填写后上传" type="info" :closable="false" show-icon />
      <FileUpload drag :limit="1" :accept="['.xlsx', '.xls']" @success="handleImportSuccess" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Search, Refresh, Plus, Upload, Download, Delete } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import FileUpload from '@/components/FileUpload.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import {
  getUserList, createUser, updateUser, deleteUser
} from '@/api/user'
import { getColleges } from '@/api/auth'
import { ROLE_LABELS, ROLES } from '@/api/types'

// ==================== 搜索 ====================
const searchForm = reactive({
  keyword: '',
  role: undefined as number | undefined,
  status: undefined as number | undefined,
  college_id: undefined as number | undefined,
})

function handleSearch() {
  page.value = 1
  loadData()
}

function handleReset() {
  searchForm.keyword = ''
  searchForm.role = undefined
  searchForm.status = undefined
  searchForm.college_id = undefined
  handleSearch()
}

// ==================== 表格 ====================
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
  { prop: 'status', label: '状态', slot: 'status', width: 80 },
  { prop: 'created_at', label: '创建时间', minWidth: 160 },
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

// ==================== 学院列表 ====================
const colleges = ref<any[]>([])
async function loadColleges() {
  const res = await getColleges()
  colleges.value = res.data || []
}

// ==================== 新增/编辑 ====================
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
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '密码至少6位', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [{ type: 'email', message: '请输入正确的邮箱', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

function handleAdd() {
  editingUser.value = null
  Object.assign(userForm, {
    username: '', password: '', real_name: '', email: '', phone: '', role: 1, college_id: undefined,
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
      if (editingUser.value) {
        await updateUser(editingUser.value.id, {
          real_name: userForm.real_name,
          email: userForm.email,
          phone: userForm.phone,
          role: userForm.role,
          college_id: userForm.college_id,
        })
        ElMessage.success('修改成功')
      } else {
        await createUser({
          username: userForm.username,
          password: userForm.password,
          real_name: userForm.real_name,
          email: userForm.email,
          phone: userForm.phone,
          role: userForm.role,
          college_id: userForm.college_id,
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

// ==================== 删除/禁用 ====================
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

// ==================== 导入 ====================
const importDialogVisible = ref(false)

function handleImportSuccess() {
  ElMessage.success('导入完成')
  importDialogVisible.value = false
  loadData()
}

async function handleDownloadTemplate() {
  // 调用后端下载模板接口
  window.open('/api/users/import/template', '_blank')
}

// ==================== 工具函数 ====================
function roleLabel(role: number) {
  return ROLE_LABELS[role] || '未知'
}

function roleTagType(role: number): string {
  const map: Record<number, string> = { 1: '', 2: 'success', 3: 'warning', 4: 'danger' }
  return map[role] || 'info'
}

// ==================== 初始化 ====================
onMounted(() => {
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
</style>
