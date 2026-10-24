<!--
  页面名称：学院管理（管理员端）
  面向角色：超级管理员（查看 + 新增/编辑/启停）、学院管理员（只读本院组织信息）
  功能：学院列表、关键词/状态筛选、新增学院、编辑学院、启用/停用
  调用 API：
    - GET  /api/colleges?include_disabled=true：拉取包含停用学院在内的全部学院
    - POST /api/colleges：新增学院
    - PUT  /api/colleges/{id}：修改学院（编码、名称、院长、排序、状态）
  权限 / 数据范围：
    - 列表接口本身是公开的，前端入口按菜单角色控制；后端新增/修改仅超级管理员可调用
      （CollegeService 内再次校验 is_super_admin），前端隐藏按钮只是交互层约束
    - 学院管理员不显示新增入口与操作列，并在表格下方提示只读原因
  关键交互：
    - 关键词与状态筛选在本地对已加载列表做计算过滤（学院数量少，无需分页接口）
    - 编辑时学院编码不可修改，避免已关联用户、项目的编码失效
    - 启停需二次确认，成功后重新拉取列表
-->
<template>
  <div class="page-container">
    <!--
      筛选区
      学院接口不支持 keyword/status 参数，这里只改响应式条件，
      由 computed 的 filteredData 在本地过滤；「刷新」重新拉取远端全量数据。
    -->
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

    <!--
      操作栏
      「新增学院」只对超级管理员展示；学院管理员看不到入口，即使强行调用接口也会被后端拒绝。
    -->
    <div class="action-bar">
      <el-button v-if="userStore.isSuperAdmin" type="primary" :icon="Plus" @click="handleAdd">新增学院</el-button>
    </div>

    <!--
      学院表格
      数据源为 filteredData（客户端过滤后的结果），不分页：学院总量有限，一页展示更直观。
      操作列的编辑/启停按钮同样只对超级管理员渲染；
      空数据使用统一空状态插画。
    -->
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

    <!--
      只读提示
      非超级管理员（学院管理员）能看到列表但无法维护组织架构，用 alert 说明边界，
      避免用户误以为按钮因故障消失。
    -->
    <el-alert
      v-if="!userStore.isSuperAdmin"
      title="学院管理仅超级管理员可新增/修改，学院管理员仅可查看本院组织信息"
      type="info"
      :closable="false"
      show-icon
      style="margin-top: 12px"
    />

    <!--
      新增 / 编辑学院弹窗
      编辑时 college_code 输入框禁用：编码可能被用户/项目等业务数据引用，变更会导致关联失配。
      院长 ID 可选，留空时提交 payload 不携带该字段，避免把 undefined 传给后端。
    -->
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

// ==================== 筛选与列表状态 ====================
// 本地筛选条件：keyword 匹配学院名称或编码，status 为 1 启用 / 0 停用
const searchForm = reactive({
  keyword: '',
  status: undefined as number | undefined,
})

// 远端返回的全部学院（含停用）
const tableData = ref<any[]>([])
// 表格加载状态
const loading = ref(false)

/**
 * 客户端过滤后的学院列表
 * 状态筛选先做精确匹配，再按关键词做名称/编码的大小写无关包含匹配；
 * 不调用后端是因为 /api/colleges 没有分页与搜索参数，且学院数据量很小。
 */
const filteredData = computed(() =>
  tableData.value.filter((c) => {
    if (searchForm.status != null && Number(c.status) !== Number(searchForm.status)) return false
    const kw = searchForm.keyword.trim().toLowerCase()
    if (!kw) return true
    return String(c.college_name || '').toLowerCase().includes(kw)
      || String(c.college_code || '').toLowerCase().includes(kw)
  })
)

// ==================== 数据加载 ====================
/**
 * 拉取学院列表
 * 传 include_disabled=true，管理端需要看到并管理已停用的学院；
 * 失败处理：不在此捕获，由全局拦截器提示；finally 复位 loading。
 */
async function loadData() {
  loading.value = true
  try {
    const res: any = await getColleges({ include_disabled: true })
    tableData.value = res.data || []
  } finally {
    loading.value = false
  }
}

// ==================== 新增 / 编辑表单 ====================
// 弹窗显隐
const dialogVisible = ref(false)
// 正在编辑的学院 id；为 null 表示新增
const editingId = ref<number | null>(null)
// 提交按钮 loading，防止重复提交
const submitLoading = ref(false)
// 表单实例，用于校验
const formRef = ref<FormInstance>()
// 表单模型：编码、名称、院长 ID（可选）、排序、状态
const form = reactive({
  college_code: '',
  college_name: '',
  dean_id: undefined as number | undefined,
  sort_order: 0,
  status: 1,
})

// 仅编码与名称必填；院长 ID、排序、状态有默认值
const rules: FormRules = {
  college_code: [{ required: true, message: '请输入学院编码', trigger: 'blur' }],
  college_name: [{ required: true, message: '请输入学院名称', trigger: 'blur' }],
}

/**
 * 打开新增弹窗
 * 重置为默认表单（排序 0、状态启用），清空 editingId 以切换到新增模式。
 */
function handleAdd() {
  editingId.value = null
  Object.assign(form, { college_code: '', college_name: '', dean_id: undefined, sort_order: 0, status: 1 })
  dialogVisible.value = true
}

/**
 * 打开编辑弹窗
 * @param row 学院行数据
 * 回填表单并用 row.id 标记编辑对象；编码字段虽被禁用，仍需带入以保持提交数据完整。
 */
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

/**
 * 提交新增 / 编辑学院
 * 先执行表单校验；payload 只包含后端 CollegeUpdate 支持的字段，
 * 院长 ID 为空时不放入 payload，避免必填校验冲突。
 * 失败处理：异常交给全局拦截器提示，finally 复位 submitLoading；
 *   成功后关闭弹窗并重新拉取列表。
 */
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

/**
 * 启用 / 停用学院
 * @param row 目标学院
 * 停用会影响该学院用户/项目的可见范围，因此必须二次确认；
 * 用户取消则直接返回，不调用接口。
 * 成功后重新拉取列表，使状态标签与后端一致。
 */
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

// ==================== 初始化 ====================
// 首屏拉取全部学院；筛选在本地进行，不需要额外请求
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
