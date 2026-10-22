<!--
  学院管理页面（管理员端）
  学院列表查询；新增/编辑/启停仅超级管理员可用（与后端 CollegeService 权限一致）
-->
<template>
  <div class="page-container">
    <el-card shadow="never" class="search-card">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词">
          <el-input v-model="searchForm.keyword" placeholder="学院名称/编码" clearable style="width: 200px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="searchForm.status" placeholder="全部状态" clearable style="width: 120px">
            <el-option label="启用" :value="1" />
            <el-option label="停用" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Refresh" @click="loadData">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="action-bar">
      <el-button v-if="userStore.isSuperAdmin" type="primary" :icon="Plus" @click="handleAdd">新增学院</el-button>
    </div>

    <el-table :data="filteredData" v-loading="loading" border stripe style="width: 100%">
      <el-table-column prop="college_code" label="学院编码" width="140" />
      <el-table-column prop="college_name" label="学院名称" min-width="200" />
      <el-table-column prop="sort_order" label="排序" width="90" align="center" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small">
            {{ row.status === 1 ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="170">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column v-if="userStore.isSuperAdmin" label="操作" width="150" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
          <el-button link type="warning" size="small" @click="handleToggleStatus(row)">
            {{ row.status === 1 ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <EmptyIllustration type="default" description="暂无学院数据" />
      </template>
    </el-table>

    <el-alert
      v-if="!userStore.isSuperAdmin"
      title="学院管理仅超级管理员可新增/修改，学院管理员仅可查看本院组织信息"
      type="info"
      :closable="false"
      show-icon
      style="margin-top: 12px"
    />

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      center
      v-model="dialogVisible"
      :title="editingId ? '编辑学院' : '新增学院'"
      width="480px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="学院编码" prop="college_code">
          <el-input v-model="form.college_code" placeholder="如 001" maxlength="32" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="学院名称" prop="college_name">
          <el-input v-model="form.college_name" placeholder="请输入学院名称" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="院长ID">
          <el-input-number v-model="form.dean_id" :min="1" :controls="false" placeholder="可选" style="width: 100%" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.status" :active-value="1" :inactive-value="0" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'
import { getColleges, createCollege, updateCollege } from '@/api/auth'
import { formatDateTime } from '@/utils/format'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined,
})

const tableData = ref<any[]>([])
const loading = ref(false)

const filteredData = computed(() =>
  tableData.value.filter((c) => {
    if (searchForm.status != null && Number(c.status) !== Number(searchForm.status)) return false
    const kw = searchForm.keyword.trim().toLowerCase()
    if (!kw) return true
    return String(c.college_name || '').toLowerCase().includes(kw)
      || String(c.college_code || '').toLowerCase().includes(kw)
  })
)

async function loadData() {
  loading.value = true
  try {
    const res: any = await getColleges({ include_disabled: true })
    tableData.value = res.data || []
  } finally {
    loading.value = false
  }
}

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const submitLoading = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({
  college_code: '',
  college_name: '',
  dean_id: undefined as number | undefined,
  sort_order: 0,
  status: 1,
})

const rules: FormRules = {
  college_code: [{ required: true, message: '请输入学院编码', trigger: 'blur' }],
  college_name: [{ required: true, message: '请输入学院名称', trigger: 'blur' }],
}

function handleAdd() {
  editingId.value = null
  Object.assign(form, { college_code: '', college_name: '', dean_id: undefined, sort_order: 0, status: 1 })
  dialogVisible.value = true
}

function handleEdit(row: any) {
  editingId.value = row.id
  Object.assign(form, {
    college_code: row.college_code,
    college_name: row.college_name,
    dean_id: row.dean_id ?? undefined,
    sort_order: row.sort_order ?? 0,
    status: row.status ?? 1,
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitLoading.value = true
    try {
      const payload: any = {
        college_code: form.college_code,
        college_name: form.college_name,
        sort_order: form.sort_order,
        status: form.status,
      }
      if (form.dean_id != null) payload.dean_id = form.dean_id
      if (editingId.value) {
        await updateCollege(editingId.value, payload)
        ElMessage.success('修改成功')
      } else {
        await createCollege(payload)
        ElMessage.success('新增成功')
      }
      dialogVisible.value = false
      loadData()
    } finally {
      submitLoading.value = false
    }
  })
}

async function handleToggleStatus(row: any) {
  const target = row.status === 1 ? 0 : 1
  try {
    await ElMessageBox.confirm(
      `确定${target === 1 ? '启用' : '停用'}学院「${row.college_name}」吗？`,
      '提示',
      { type: 'warning' },
    )
  } catch { return }
  await updateCollege(row.id, { status: target })
  ElMessage.success(target === 1 ? '已启用' : '已停用')
  loadData()
}

onMounted(() => loadData())
</script>

<style scoped>
.search-card {
  margin-bottom: 16px;
}

.action-bar {
  margin-bottom: 16px;
}
</style>
