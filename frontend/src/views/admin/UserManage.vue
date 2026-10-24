<!--
  页面名称：用户管理（管理员端）
  面向角色：系统管理员（全校用户）、学院管理员（仅本院用户）
  功能：
    1. 用户分页查询（关键词 / 角色 / 状态 / 学院筛选）
    2. 新增、编辑、删除用户，启用 / 禁用用户
    3. 批量删除、批量启用 / 禁用
    4. Excel 批量导入（先在前端解析并逐行校验，再上传原始文件）
    5. 下载导入模板
  调用 API：
    - GET  /api/users：分页列表，后端按 DataScope 过滤
    - POST /api/users、PUT /api/users/{id}、DELETE /api/users/{id}
    - PATCH /api/users/batch/status：批量启停
    - GET  /api/colleges：学院下拉
    - POST /api/excel/import/user：上传 Excel 导入
    - GET  /api/excel/template/user：下载模板
  权限边界：
    - 角色下拉中的「系统管理员」仅超级管理员可选；学院管理员无法创建或编辑管理员账号
    - 学院管理员的学院字段禁用并强制为本人学院，前端做防御性修正，后端仍有权限兜底
    - 删除、批量启停、导入均要求管理员权限
  关键交互：
    - 学院管理员进入页面即锁定本院筛选，重置时也只恢复到本院
    - 导入预览会标红错误行；存在错误或未选文件时「确认导入」不可用
    - 批量操作依赖表格多选，未选中时按钮禁用
-->
<template>
  <div class="page-container">
    <!--
      搜索栏
      keyword 由后端模糊匹配用户名/姓名/手机号；role/status 为空表示不过滤。
      学院下拉对学院管理员禁用且不可清空，与列表数据范围保持一致；
      「重置」会清空其他条件，但学院管理员仍保留本院，避免重置后误看全校。
    -->
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

    <!--
      操作栏
      批量删除 / 启用 / 禁用都依赖表格多选，selection 为空时禁用，避免发出空请求。
      模板下载使用 window.open 直接走浏览器 GET 下载，不经过 axios，因此无需处理 blob。
    -->
    <div class="action-bar">
      <el-button type="primary" :icon="Plus" @click="handleAdd">新增用户</el-button>
      <el-button type="success" :icon="Upload" @click="openImportDialog">批量导入</el-button>
      <el-button :icon="Download" @click="handleDownloadTemplate">下载模板</el-button>
      <el-button type="warning" :icon="Delete" :disabled="selection.length === 0" @click="handleBatchDelete">
        批量删除
      </el-button>
      <el-button type="success" :icon="Check" :disabled="selection.length === 0" @click="handleBatchStatus(1)">
        批量启用
      </el-button>
      <el-button type="info" :icon="Close" :disabled="selection.length === 0" @click="handleBatchStatus(0)">
        批量禁用
      </el-button>
    </div>

    <!--
      用户表格
      角色、状态、操作列使用插槽：角色配色由 roleTagType 统一，状态用成功/危险色区分启停。
      selection-change 把选中的完整行写入 selection，批量操作据此取 id。
      行内「禁用/启用」直接调用更新接口切换 status，不弹二次确认；删除与批量操作才需确认。
    -->
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

    <!--
      新增 / 编辑用户弹窗
      编辑时用户名只读（作为登录标识不允许改），密码字段只在新增时出现。
      「系统管理员」选项仅超级管理员可见；学院管理员的学院下拉禁用，
      表单初始化时已填入本院，提交时还会再做一次强制修正。
      角色为管理员时不显示学院字段（管理员是全校级角色，不绑定学院）。
    -->
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

    <!--
      批量导入弹窗
      采用「先解析预览、再确认上传」两步：选择文件后只在浏览器解析并逐行校验，
      不立刻入库，用户能先看到错误行并修正。auto-upload 关闭，limit=1 防止多文件。
      关闭弹窗时清空文件与预览，避免下次打开残留上一次的数据。
      确认按钮在有错误行或未选文件时禁用，并在文案上提示需要重新上传。
    -->
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

      <!--
        导入预览区域
        只渲染前 20 行以控制弹窗高度，但统计数字针对全部行；
        错误行通过 row-class-name 加红底，错误列展示具体原因。
        errorCount > 0 时顶部切换为错误提示，全部通过时才显示可导入。
      -->
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
import { Search, Refresh, Plus, Upload, Download, Delete, Check, Close } from '@element-plus/icons-vue'
import PaginationTable from '@/components/PaginationTable.vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import PasswordStrength from '@/components/PasswordStrength.vue'
import type { TableColumn } from '@/components/PaginationTable.vue'
import {
  getUserList, createUser, updateUser, deleteUser, batchUpdateUserStatus
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

// ==================== 类型定义 ====================
// 导入预览行：在原始 Excel 字段基础上追加错误信息，便于表格标红与汇总统计
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

// ==================== 筛选条件 ====================
// 查询条件；角色 1/2/3/4 分别对应学生/教师/专家/管理员，undefined 表示全部
const searchForm = reactive({
  keyword: '',
  role: undefined as number | undefined,
  status: undefined as number | undefined,
  college_id: undefined as number | undefined,
})

/**
 * 初始化学院数据范围
 * 学院管理员进入页面时默认锁定本人学院，使列表与后端 DataScope 一致；
 * 超级管理员不设置，默认可查看全校。
 */
function initCollegeScopeDefaults() {
  if (userStore.isCollegeAdmin) {
    searchForm.college_id = userStore.collegeId ?? undefined
  }
}

/** 查询：回到第 1 页后加载，防止筛选后页码越界 */
function handleSearch() {
  page.value = 1
  loadData()
}

/**
 * 重置筛选
 * 清空关键词、角色、状态；学院管理员保留本院（不能重置成全校），
 * 随后立即查询，避免界面条件已变但列表未刷新。
 */
function handleReset() {
  searchForm.keyword = ''
  searchForm.role = undefined
  searchForm.status = undefined
  searchForm.college_id = userStore.isCollegeAdmin ? (userStore.collegeId ?? undefined) : undefined
  handleSearch()
}

// ==================== 列表状态 ====================
// 当前页用户
const tableData = ref<any[]>([])
// 服务端总数
const total = ref(0)
// 列表加载状态
const loading = ref(false)
// 当前页码
const page = ref(1)
// 每页条数
const pageSize = ref(10)
// 表格勾选行，批量删除 / 启停使用
const selection = ref<any[]>([])

// ==================== 表格列 ====================
// 角色、状态、操作列通过模板插槽渲染，其余为纯文本列
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

// ==================== 数据加载 ====================
/**
 * 加载当前页用户
 * 把分页参数与筛选条件一起交给 getUserList，后端根据当前登录人角色注入数据范围，
 * 前端不能通过改 college_id 越权（学院管理员的条件会被后端约束）。
 * 失败处理：本地不捕获，由全局拦截器提示；finally 复位 loading。
 */
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

/**
 * 分页回调
 * @param p 页码
 * @param ps 每页条数
 */
function handlePageChange(p: number, ps: number) {
  page.value = p
  pageSize.value = ps
  loadData()
}

// ==================== 学院下拉 ====================
// 学院列表用于筛选与表单；加载失败不会阻断用户列表（仅少一个下拉数据）
const colleges = ref<any[]>([])
/** 拉取学院列表，成功时覆盖下拉数据 */
async function loadColleges() {
  const res = await getColleges()
  colleges.value = res.data || []
}

// ==================== 新增 / 编辑表单 ====================
// 弹窗显隐
const dialogVisible = ref(false)
// 正在编辑的用户；为 null 表示新增
const editingUser = ref<any>(null)
// 表单实例，用于触发校验
const formRef = ref<FormInstance>()
// 提交按钮 loading，防止重复提交
const submitLoading = ref(false)

// 表单模型；新增与编辑共用，打开弹窗时整体覆盖，避免残留上一次的字段
const userForm = reactive({
  username: '',
  password: '',
  real_name: '',
  email: '',
  phone: '',
  role: 1,
  college_id: undefined as number | undefined,
})

// 校验规则：邮箱/手机号非必填但填了必须合法；密码规则只在新增时校验
const userRules: FormRules = {
  username: [{ validator: requiredValidator('用户名'), trigger: 'blur' }],
  password: [{ validator: passwordValidator(true, '初始密码'), trigger: 'blur' }],
  real_name: [{ validator: requiredValidator('姓名'), trigger: 'blur' }],
  email: [{ validator: emailValidator(false, '邮箱'), trigger: 'blur' }],
  phone: [{ validator: phoneValidator(false, '手机号'), trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

/**
 * 打开新增弹窗
 * 重置表单为默认值；学院管理员预填本院，避免在表单里再选学院。
 * 副作用：写入 userForm、清空 editingUser、显示弹窗。
 */
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

/**
 * 打开编辑弹窗
 * @param row 选中的用户行
 * 把行数据回填到表单；密码留空（编辑不修改密码），用户名在弹窗中只读。
 */
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

/**
 * 提交新增 / 编辑
 * 先由 el-form 校验，校验通过后再请求。
 * 学院管理员做防御性修正：学院强制为本院，且禁止提交管理员角色（role=4）。
 * 编辑只提交可变字段（姓名、邮箱、手机号、角色、学院），不提交用户名与密码。
 * 失败处理：接口异常由全局拦截器提示，finally 复位 submitLoading；
 *   成功后关闭弹窗并刷新列表。
 */
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

// ==================== 删除与启停 ====================
/**
 * 删除单个用户
 * @param row 目标用户
 * 先二次确认，用户取消则直接返回；确认后调用软删除接口并刷新列表。
 * 失败处理：请求异常由全局拦截器提示。
 */
async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.real_name}」吗？`, '提示', { type: 'warning' })
  } catch { return }
  await deleteUser(row.id)
  ElMessage.success('删除成功')
  loadData()
}

/**
 * 批量删除
 * 后端没有批量删除接口，因此按选中顺序逐个调用删除。
 * 注意：中途某条失败会中断循环，已删除的不会回滚，成功提示也不会出现；
 * 用户需要重新查询后核对剩余数据。
 */
async function handleBatchDelete() {
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selection.value.length} 个用户吗？`, '提示', { type: 'warning' })
  } catch { return }
  for (const user of selection.value) {
    await deleteUser(user.id)
  }
  ElMessage.success(`已删除 ${selection.value.length} 个用户`)
  selection.value = []
  loadData()
}

/**
 * 批量启用 / 禁用
 * @param status 1 启用，0 禁用
 * 使用后端批量接口一次提交，比逐条更新更省请求；成功数优先取后端返回的 updated_count。
 * 副作用：清空勾选、刷新列表；用户取消确认时不发请求。
 */
async function handleBatchStatus(status: number) {
  const n = selection.value.length
  if (n === 0) return
  const action = status === 1 ? '启用' : '禁用'
  try {
    await ElMessageBox.confirm(`确定${action}选中的 ${n} 个用户吗？`, '提示', { type: 'warning' })
  } catch { return }
  const res: any = await batchUpdateUserStatus(selection.value.map((u: any) => u.id), status)
  ElMessage.success(`已${action} ${res?.data?.updated_count ?? n} 个用户`)
  selection.value = []
  loadData()
}

/**
 * 行内切换启用 / 禁用
 * @param row 目标用户
 * 直接用 updateUser 提交相反的 status，不弹确认框（行内高频操作，避免打断）。
 * 成功后刷新列表，使标签与后端状态保持一致。
 */
async function handleToggleStatus(row: any) {
  await updateUser(row.id, { status: row.status === 1 ? 0 : 1 })
  ElMessage.success(row.status === 1 ? '已禁用' : '已启用')
  loadData()
}

// ==================== 批量导入：预览与校验 ====================
// 导入弹窗显隐
const importDialogVisible = ref(false)
// 上传提交状态
const importLoading = ref(false)
// el-upload 实例与受控文件列表（limit=1，选择新文件前需先移除旧文件）
const uploadRef = ref()
const uploadFileList = ref<UploadUserFile[]>([])
// 当前待上传的原始文件，确认导入时才真正上传
const selectedFile = ref<File | null>(null)
// 前端解析出的预览行，包含错误标记
const previewData = ref<PreviewRow[]>([])

// 错误行数；确认导入按钮据此禁用
const errorCount = computed(() => previewData.value.filter((r) => r._hasError).length)
// 通过行数 = 总行数 - 错误行数
const passCount = computed(() => previewData.value.length - errorCount.value)

/** 打开导入弹窗（弹窗关闭时会清理状态，这里无需重置） */
function openImportDialog() {
  importDialogVisible.value = true
}

/**
 * 关闭导入弹窗并清理状态
 * 清空文件列表、原始文件与预览，防止下一次导入看到上一次的解析结果。
 */
function closeImportDialog() {
  importDialogVisible.value = false
  uploadFileList.value = []
  selectedFile.value = null
  previewData.value = []
}

/**
 * 选择文件回调
 * @param file el-upload 的受控文件对象
 * 只保存原始 File 并立即解析预览，不自动上传。
 */
async function handleFileSelect(file: UploadUserFile) {
  const raw = file.raw as File
  if (!raw) return
  selectedFile.value = raw
  await parseAndPreview(raw)
}

/** 移除文件：同步清空原始文件与预览，避免残留可导入状态 */
function handleFileRemove() {
  selectedFile.value = null
  previewData.value = []
}

/**
 * 解析 Excel 并生成预览
 * @param file 用户选择的 Excel 文件
 * 表头兼容中英文与常见别名（username/用户名/user_name 等），减少模板差异导致的失败。
 * 解析成功后逐行校验；解析失败则提示并清空文件，避免保留一个无法预览的坏文件。
 */
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

/**
 * 逐行校验导入数据
 * @param rows 解析后的预览行（函数内直接写入 _error/_hasError）
 * 校验内容：必填用户名/姓名、用户名重复、角色范围 1~4、手机号/邮箱/密码格式、学院 ID 为数字。
 * 学院管理员的额外限制：禁止导入管理员（role=4），且填写的学院必须是本院。
 * 说明：重复检测基于整批数据，同一用户名只要出现两次，两行都会标错，便于用户定位。
 */
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

/** 为错误行附加 error-row 类名，样式中统一标红背景 */
function rowClassName({ row }: { row: PreviewRow }) {
  return row._hasError ? 'error-row' : ''
}

/**
 * 确认导入
 * 前置：已选择文件且没有错误行（按钮禁用是第一道，这里再判一次防止状态滞后）。
 * 上传的是原始 Excel 而非前端解析结果，后端会重新解析校验，前端预览只是提前暴露问题。
 * 成功：提示、关闭弹窗、刷新列表；失败：优先展示后端 message，网络异常用兜底文案。
 */
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

/**
 * 下载用户导入模板
 * 直接 window.open 打开后端模板地址，由浏览器处理附件下载，
 * 避免 axios 读取 blob 后再手动生成 a 标签。
 */
async function handleDownloadTemplate() {
  window.open('/api/excel/template/user', '_blank')
}

// ==================== 角色展示 ====================
/** 角色码 → 中文名，取自接口层常量，未知码显示「未知」 */
function roleLabel(role: number) {
  return ROLE_LABELS[role] || '未知'
}

/** 角色码 → el-tag 颜色：学生默认、教师成功、专家警告、管理员危险，未知回退 info */
function roleTagType(role: number): string {
  const map: Record<number, string> = { 1: '', 2: 'success', 3: 'warning', 4: 'danger' }
  return map[role] || 'info'
}

// ==================== 初始化 ====================
// 先锁定学院范围再查询；学院下拉并行加载，失败只影响筛选与表单，不影响列表
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
