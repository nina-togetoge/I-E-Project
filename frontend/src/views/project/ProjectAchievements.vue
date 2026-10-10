<!--
  项目成果（独立页面）
  从项目详情页抽离，支持查看/登记/删除项目成果
-->
<template>
  <div class="page-container" v-loading="loading">
    <div class="back-bar">
      <el-button text @click="goBack">
        <el-icon><ArrowLeft /></el-icon> 返回项目详情
      </el-button>
    </div>

    <template v-if="project">
      <div class="page-header">
        <div class="header-row">
          <div>
            <h2 class="page-title">项目成果</h2>
            <div class="page-subtitle">{{ project.project_name }}</div>
          </div>
          <el-button type="primary" @click="showDialog = true">登记成果</el-button>
        </div>
      </div>

      <div class="table-wrap" v-if="achievements.length > 0">
        <table class="paper-table">
          <thead>
            <tr>
              <th style="width:70px">序号</th>
              <th style="width:100px">类型</th>
              <th>标题</th>
              <th style="width:130px">作者</th>
              <th style="width:110px">日期</th>
              <th style="width:70px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(a, i) in achievements" :key="i">
              <td align="center">{{ i + 1 }}</td>
              <td>{{ achievementTypeMap[a.achievement_type] }}</td>
              <td>{{ a.title }}</td>
              <td>{{ a.author }}</td>
              <td>{{ formatDate(a.publish_date) }}</td>
              <td align="center">
                <el-button link type="danger" size="small" @click="handleDelete(a)">删除</el-button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <el-empty v-else description="暂无成果" :image-size="60" />
    </template>

    <!-- 成果登记弹窗 -->
    <el-dialog center v-model="showDialog" title="登记项目成果" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="成果类型" prop="achievement_type">
          <el-select v-model="form.achievement_type" placeholder="请选择" style="width: 100%">
            <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="成果标题/名称" maxlength="255" show-word-limit />
        </el-form-item>
        <el-form-item label="作者">
          <el-input v-model="form.author" placeholder="作者/发明人" maxlength="255" />
        </el-form-item>
        <el-form-item label="发表日期">
          <el-date-picker v-model="form.publish_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="发表刊物">
          <el-input v-model="form.publisher" placeholder="发表刊物/授权机构" maxlength="255" />
        </el-form-item>
        <el-form-item label="编号">
          <el-input v-model="form.achievement_no" placeholder="专利号/论文编号等" maxlength="128" />
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="form.level" placeholder="请选择" clearable style="width: 100%">
            <el-option label="校级" :value="1" />
            <el-option label="省级" :value="2" />
            <el-option label="国家级" :value="3" />
            <el-option label="国际级" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item label="获奖等级">
          <el-input v-model="form.award_level" placeholder="如：一等奖" maxlength="64" />
        </el-form-item>
        <el-form-item label="成果简介">
          <el-input v-model="form.summary" type="textarea" :rows="3" placeholder="成果简介" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getProjectDetail, listAchievements, createAchievement, deleteAchievement } from '@/api/project'
import { formatDate } from '@/utils/format'
import { useProcessStore } from '@/store/process'

const route = useRoute()
const router = useRouter()
const processStore = useProcessStore()
const pid = computed(() => Number(route.params.id))

const project = ref<any>(null)
const achievements = ref<any[]>([])
const loading = ref(true)
const showDialog = ref(false)
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({
  achievement_type: undefined as number | undefined,
  title: '',
  author: '',
  publish_date: '',
  publisher: '',
  achievement_no: '',
  level: undefined as number | undefined,
  award_level: '',
  summary: '',
})
const achievementTypeMap: Record<number, string> = {
  1: '论文', 2: '专利', 3: '软件著作权', 4: '竞赛获奖', 5: '创业成果', 6: '其他',
}
const typeOptions = Object.entries(achievementTypeMap).map(([key, label]) => ({
  value: Number(key), label,
}))
const rules: FormRules = {
  achievement_type: [{ required: true, message: '请选择成果类型', trigger: 'change' }],
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
}

function goBack() {
  router.push(`/projects/${pid.value}`)
}

async function loadData() {
  loading.value = true
  try {
    const [detailRes, achRes] = await Promise.all([
      getProjectDetail(pid.value),
      listAchievements(pid.value).catch(() => ({ data: [] })),
    ])
    project.value = detailRes.data
    processStore.setStatus(detailRes.data.status)
    achievements.value = achRes.data || []
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      await createAchievement({
        project_id: pid.value,
        achievement_type: form.achievement_type!,
        title: form.title,
        author: form.author || undefined,
        publish_date: form.publish_date || undefined,
        publisher: form.publisher || undefined,
        achievement_no: form.achievement_no || undefined,
        level: form.level,
        award_level: form.award_level || undefined,
        summary: form.summary || undefined,
      })
      ElMessage.success('成果登记成功')
      showDialog.value = false
      formRef.value?.resetFields()
      loadData()
    } finally {
      submitting.value = false
    }
  })
}

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确认删除成果「${row.title}」？`, '提示', { type: 'warning' })
  await deleteAchievement(row.id)
  ElMessage.success('已删除')
  loadData()
}

onMounted(() => loadData())
</script>

<style scoped>
.back-bar {
  margin-bottom: 12px;
}
.page-header {
  margin-bottom: 20px;
}
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 6px 0;
}
.page-subtitle {
  color: #909399;
  font-size: 13px;
}
.table-wrap {
  overflow-x: auto;
}
.paper-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.paper-table th,
.paper-table td {
  border: 1px solid #ebeef5;
  padding: 10px 12px;
  text-align: left;
}
.paper-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #606266;
}
.paper-table tbody tr:hover {
  background: #fafafa;
}
</style>
