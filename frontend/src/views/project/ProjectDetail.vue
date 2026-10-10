<!--
  项目详情页（维普学术论文风格）
  展示项目完整信息、审核流程进度、团队成员、预算、成果
-->
<template>
  <div class="page-container" v-loading="loading">
    <!-- 返回按钮（页面模式显示，弹窗模式隐藏） -->
    <div class="back-bar" v-if="!props.projectId">
      <el-button text @click="router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
    </div>

    <template v-if="project">
      <!-- 标签页导航 -->
      <div class="paper-tabs" v-if="props.projectId">
        <div
          v-for="tab in tabs"
          :key="tab.key"
          class="paper-tab"
          :class="{ active: activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >{{ tab.label }}</div>
      </div>

      <!-- 论文式标题区 -->
      <div class="paper-header">
        <h1 class="paper-title">{{ project.project_name }}</h1>
        <div class="paper-authors">
          <span class="author-item"><b>负责人：</b>{{ project.leader_name }}</span>
          <span class="author-divider">|</span>
          <span class="author-item"><b>指导教师：</b>{{ project.teacher_name || '未绑定' }}</span>
          <span class="author-divider">|</span>
          <span class="author-item"><b>所属学院：</b>{{ project.college_name }}</span>
        </div>
        <div class="paper-meta">
          <span class="meta-item"><el-icon><Document /></el-icon> 编号：{{ project.project_no }}</span>
          <span class="meta-item"><el-icon><Collection /></el-icon> 类别：{{ project.project_type_name }}</span>
          <span class="meta-item"><el-icon><Trophy /></el-icon> 赛事：{{ project.competition_name || '未关联' }}</span>
          <span class="meta-item"><el-icon><Calendar /></el-icon> {{ project.start_date || '-' }} ~ {{ project.end_date || '-' }}</span>
          <span class="meta-item"><el-icon><Wallet /></el-icon> 预算：¥ {{ Number(project.budget_amount || 0).toFixed(2) }}</span>
          <StatusTag :status="project.status" />
        </div>
      </div>

      <!-- 摘要区 -->
      <div class="paper-abstract">
        <div class="abstract-label">摘　要</div>
        <div class="abstract-text">
          <span class="abstract-indent">{{ project.project_summary || '暂无摘要' }}</span>
        </div>
        <div class="abstract-keywords">
          <b>创新点：</b>{{ project.innovation_points || '暂无' }}
          <span class="kw-divider">　</span>
          <b>预期成果：</b>{{ project.expected_results || '暂无' }}
        </div>
      </div>

      <!-- 1. 审核流程 -->
      <section class="paper-section">
        <h2 class="section-title"><span class="section-num">1</span>审核流程</h2>
        <ProjectTimeline :project="project" :review-history="reviewHistory" />
      </section>

      <!-- 2. 团队成员 -->
      <section class="paper-section">
        <h2 class="section-title"><span class="section-num">2</span>团队成员</h2>
        <div class="table-wrap">
          <table class="paper-table">
            <thead>
              <tr>
                <th style="width:70px">序号</th>
                <th>学号</th>
                <th>姓名</th>
                <th>分工</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(m, i) in project.team_members" :key="i">
                <td align="center">{{ i + 1 }}</td>
                <td>{{ m.student_no }}</td>
                <td>{{ m.student_name }}</td>
                <td>{{ m.role_in_team || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 3. 预算明细 -->
      <section class="paper-section">
        <h2 class="section-title"><span class="section-num">3</span>预算明细</h2>
        <div class="table-wrap">
          <table class="paper-table">
            <thead>
              <tr>
                <th style="width:70px">序号</th>
                <th>科目</th>
                <th style="width:140px">金额(元)</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(b, i) in project.budgets" :key="i">
                <td align="center">{{ i + 1 }}</td>
                <td>{{ b.budget_item }}</td>
                <td align="right">¥ {{ Number(b.budget_amount || 0).toFixed(2) }}</td>
                <td>{{ b.remark }}</td>
              </tr>
              <tr class="table-summary">
                <td colspan="2" align="right"><b>合计</b></td>
                <td align="right"><b>¥ {{ totalBudget.toFixed(2) }}</b></td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 4. 申报附件 -->
      <section class="paper-section">
        <h2 class="section-title"><span class="section-num">4</span>申报附件</h2>
        <ProjectAttachmentList :attachments="project.attachments" />
      </section>

      <!-- 5. 项目成果（跳转独立页面） -->
      <section v-if="project && project.status >= 6" class="paper-section">
        <h2 class="section-title"><span class="section-num">5</span>项目成果</h2>
        <div class="link-card" @click="goAchievements">
          <div class="link-card-text">
            <el-icon><Trophy /></el-icon>
            <span>查看和登记项目成果（论文、专利、软著等）</span>
          </div>
          <el-button type="primary" size="small">进入</el-button>
        </div>
      </section>

      <!-- 6. 中期检查（跳转独立页面） -->
      <section v-if="project && project.status >= 6" class="paper-section">
        <h2 class="section-title"><span class="section-num">6</span>中期检查</h2>
        <div class="link-card" @click="goMidterm">
          <div class="link-card-text">
            <el-icon><Calendar /></el-icon>
            <span>填写项目进展、已完成任务、经费使用等中期检查信息</span>
          </div>
          <el-button type="primary" size="small">进入</el-button>
        </div>
      </section>

      <!-- 7. 结项验收 -->
      <section v-if="project && project.status === 8" class="paper-section">
        <h2 class="section-title">
          <span class="section-num">7</span>结项验收
          <el-button type="success" size="small" class="section-action" @click="showFinalDialog = true">提交结项验收报告</el-button>
        </h2>
        <el-empty description="项目已完成中期检查，请提交结项验收报告以完成结题" :image-size="60" />
      </section>

      <!-- 8. 变更/延期申请（仅学生可见） -->
      <section class="paper-section" v-if="userStore.isStudent">
        <h2 class="section-title">
          <span class="section-num">{{ sectionNum }}</span>变更/延期申请
          <el-button type="primary" size="small" class="section-action" @click="showChangeDialog = true">提交申请</el-button>
        </h2>
        <div class="table-wrap" v-if="changeList.length > 0">
          <table class="paper-table">
            <thead>
              <tr>
                <th style="width:70px">序号</th>
                <th style="width:100px">类型</th>
                <th>变更原因</th>
                <th style="width:90px">状态</th>
                <th style="width:160px">提交时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(c, i) in changeList" :key="i">
                <td align="center">{{ i + 1 }}</td>
                <td>{{ changeTypeMap[c.change_type] }}</td>
                <td>{{ c.change_reason }}</td>
                <td align="center">
                  <el-tag :type="c.status === 3 ? 'success' : c.status === 4 ? 'danger' : 'warning'" size="small">
                    {{ c.status_name }}
                  </el-tag>
                </td>
                <td>{{ formatDateTime(c.submit_time) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <el-empty v-else description="暂无变更申请" :image-size="60" />
      </section>

      <!-- 参考文献式页脚 -->
      <div class="paper-footer">
        <div class="footer-line"></div>
        <p class="footer-note">本文为「校园创新创业项目管理平台」项目申报书，数据由平台自动生成。</p>
      </div>
    </template>

    <!-- 变更申请弹窗 -->
    <el-dialog center v-model="showChangeDialog" title="提交变更/延期申请" width="600px">
      <el-form ref="changeFormRef" :model="changeForm" :rules="changeRules" label-width="100px">
        <el-form-item label="变更类型" prop="change_type">
          <el-select v-model="changeForm.change_type" placeholder="请选择" style="width: 100%">
            <el-option v-for="item in changeTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="变更原因" prop="change_reason">
          <el-input v-model="changeForm.change_reason" type="textarea" :rows="3" placeholder="请说明变更原因" maxlength="1000" show-word-limit />
        </el-form-item>
        <el-form-item label="原内容">
          <el-input v-model="changeForm.original_content" type="textarea" :rows="2" placeholder="变更前的内容" />
        </el-form-item>
        <el-form-item label="变更后内容">
          <el-input v-model="changeForm.new_content" type="textarea" :rows="2" placeholder="变更后的内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showChangeDialog = false">取消</el-button>
        <el-button type="primary" :loading="changeLoading" @click="handleSubmitChange">提交</el-button>
      </template>
    </el-dialog>

    <!-- 结项验收报告弹窗 -->
    <el-dialog center v-model="showFinalDialog" title="提交结项验收报告" width="640px">
      <el-form ref="finalFormRef" :model="finalForm" :rules="finalRules" label-width="120px">
        <el-form-item label="结项报告" prop="final_report">
          <el-input v-model="finalForm.final_report" type="textarea" :rows="6" placeholder="请填写项目完成情况、成果总结等结项验收报告内容" maxlength="2000" show-word-limit />
        </el-form-item>
        <el-form-item label="验收材料">
          <FileUpload
            :accept="['.pdf', '.doc', '.docx', '.zip', '.rar', '.png', '.jpg']"
            :form-data="{ biz_type: 'project', biz_id: 0 }"
            @success="handleFinalFileUpload"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFinalDialog = false">取消</el-button>
        <el-button type="success" :loading="finalLoading" @click="handleSubmitFinal">提交结项报告</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { ArrowLeft, Document, Collection, Trophy, Calendar, Wallet } from '@element-plus/icons-vue'
import StatusTag from '@/components/StatusTag.vue'
import ProjectTimeline from '@/components/ProjectTimeline.vue'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import FileUpload from '@/components/FileUpload.vue'
import { useProcessStore } from '@/store/process'
import { useUserStore } from '@/store/user'
import { getProjectDetail, submitFinal } from '@/api/project'
import { getReviewHistory, createChangeRequest, getChangeList } from '@/api/review'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const processStore = useProcessStore()
const userStore = useUserStore()

// 支持弹窗模式（prop 传入）和页面模式（route.params）
const props = defineProps<{ projectId?: number }>()
const pid = computed(() => props.projectId ?? Number(route.params.id))

const project = ref<any>(null)
const reviewHistory = ref<any[]>([])
const loading = ref(true)

// 标签页
const tabs = [
  { key: 'overview', label: '项目概览' },
  { key: 'team', label: '团队成员' },
  { key: 'budget', label: '预算明细' },
  { key: 'progress', label: '进度管理' },
  { key: 'result', label: '项目成果' },
]
const activeTab = ref('overview')
function switchTab(key: string) {
  activeTab.value = key
  // 中期检查、项目成果已拆分为独立页面
  if (key === 'progress') {
    router.push(`/projects/${pid.value}/midterm`)
    return
  }
  if (key === 'result') {
    router.push(`/projects/${pid.value}/achievements`)
    return
  }
  const map: Record<string, string> = {
    overview: '审核流程', team: '团队成员', budget: '预算明细',
  }
  const target = map[key]
  if (!target) return
  const sections = document.querySelectorAll('.paper-section')
  for (const sec of sections) {
    const title = sec.querySelector('.section-title')
    if (title && title.textContent?.includes(target)) {
      sec.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
  }
}

// 跳转到中期检查页面
function goMidterm() {
  router.push(`/projects/${pid.value}/midterm`)
}
// 跳转到项目成果页面
function goAchievements() {
  router.push(`/projects/${pid.value}/achievements`)
}

// 预算合计
const totalBudget = computed(() =>
  (project.value?.budgets || []).reduce((s: number, b: any) => s + Number(b.budget_amount || 0), 0)
)

// 变更/延期申请的章节号（5/6/7 条件显示，需要动态计算）
const sectionNum = computed(() => {
  if (!project.value) return 8
  let n = 5
  if (project.value.status >= 6) n++ // 项目成果
  if (project.value.status >= 6) n++ // 中期检查
  if (project.value.status === 8) n++ // 结项验收
  return n
})

// 变更申请
const changeList = ref<any[]>([])
const showChangeDialog = ref(false)
const changeLoading = ref(false)
const changeFormRef = ref<FormInstance>()
const changeForm = reactive({
  change_type: undefined as number | undefined,
  change_reason: '',
  original_content: '',
  new_content: '',
})
const changeTypeMap: Record<number, string> = {
  1: '延期', 2: '人员变更', 3: '内容变更', 4: '预算调整', 5: '其他',
}
const changeTypeOptions = Object.entries(changeTypeMap).map(([key, label]) => ({
  value: Number(key), label,
}))
const changeRules: FormRules = {
  change_type: [{ required: true, message: '请选择变更类型', trigger: 'change' }],
  change_reason: [{ required: true, message: '请填写变更原因', trigger: 'blur' }],
}

// 结项验收
const showFinalDialog = ref(false)
const finalLoading = ref(false)
const finalFormRef = ref<FormInstance>()
const finalForm = reactive({
  final_report: '',
})
const finalAttachmentIds = ref<number[]>([])
const finalRules: FormRules = {
  final_report: [{ required: true, message: '请填写结项验收报告', trigger: 'blur' }],
}

function handleFinalFileUpload(file: any) {
  if (file?.id && !finalAttachmentIds.value.includes(file.id)) {
    finalAttachmentIds.value.push(file.id)
  }
}

async function handleSubmitFinal() {
  await finalFormRef.value?.validate()
  finalLoading.value = true
  try {
    await submitFinal(Number(pid.value), {
      final_report: finalForm.final_report,
      attachment_ids: finalAttachmentIds.value,
    })
    ElMessage.success('结项验收报告已提交，项目已结题')
    showFinalDialog.value = false
    finalForm.final_report = ''
    finalAttachmentIds.value = []
    loadData()
  } finally {
    finalLoading.value = false
  }
}

// 侧边栏阶段点击 → 跳转到对应页面或滚动到对应区域
function scrollToSection(key: string) {
  // 中期检查、项目成果已拆分为独立页面
  if (key === 'midterm') {
    router.push(`/projects/${pid.value}/midterm`)
    return
  }
  if (key === 'achievement') {
    router.push(`/projects/${pid.value}/achievements`)
    return
  }
  const sectionMap: Record<string, string> = {
    declare: '审核流程',
    teacher: '审核流程',
    college: '审核流程',
    university: '审核流程',
    expert: '审核流程',
    approved: '审核流程',
    final: '结项验收',
  }
  const target = sectionMap[key]
  if (!target) return
  const sections = document.querySelectorAll('.paper-section')
  for (const sec of sections) {
    const title = sec.querySelector('.section-title')
    if (title && title.textContent?.includes(target)) {
      sec.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
  }
}

// 监听主侧边栏的阶段点击，滚动到对应区域
watch(() => processStore.scrollToStage, (val) => {
  if (!val) return
  const key = val.split(':')[0]
  scrollToSection(key)
})

async function loadData() {
  const id = Number(pid.value)
  loading.value = true
  try {
    const [detailRes, reviewRes, chgRes] = await Promise.all([
      getProjectDetail(id),
      getReviewHistory(id).catch(() => ({ data: { records: [] } })),
      getChangeList({ page: 1, page_size: 100, project_id: id }).catch(() => ({ data: { items: [] } })),
    ])
    project.value = detailRes.data
    // 将项目状态同步到主侧边栏的"过程管理"菜单
    processStore.setStatus(detailRes.data.status)
    reviewHistory.value = reviewRes.data?.records || []
    changeList.value = chgRes.data?.items || []
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

// ========== 变更申请 ==========
async function handleSubmitChange() {
  if (!changeFormRef.value) return
  await changeFormRef.value.validate(async (valid) => {
    if (!valid) return
    changeLoading.value = true
    try {
      await createChangeRequest({
        project_id: Number(pid.value),
        change_type: changeForm.change_type!,
        change_reason: changeForm.change_reason,
        original_content: changeForm.original_content || undefined,
        new_content: changeForm.new_content || undefined,
      })
      ElMessage.success('变更申请已提交')
      showChangeDialog.value = false
      changeFormRef.value?.resetFields()
      loadData()
    } finally {
      changeLoading.value = false
    }
  })
}

onMounted(() => loadData())
onBeforeUnmount(() => processStore.reset())

// 弹窗模式下 projectId 变化时重新加载
watch(() => props.projectId, (newId) => {
  if (newId) loadData()
})
</script>

<style scoped>
/* 返回栏 */
.back-bar {
  margin-bottom: 12px;
}

/* 跳转卡片（中期检查/项目成果入口） */
.link-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: #f5f7fa;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.link-card:hover {
  background: #ecf5ff;
  border-color: #409eff;
}
.link-card-text {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #606266;
  font-size: 14px;
}
.link-card-text .el-icon {
  font-size: 18px;
  color: #409eff;
}

/* 标签页导航 */
.paper-tabs {
  display: flex;
  gap: 4px;
  padding: 0 16px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  margin-bottom: 16px;
  border-radius: 8px 8px 0 0;
}
.paper-tab {
  padding: 12px 18px;
  font-size: 14px;
  color: #606266;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
  white-space: nowrap;
}
.paper-tab:hover {
  color: #409eff;
}
.paper-tab.active {
  color: #409eff;
  border-bottom-color: #409eff;
  font-weight: 600;
}

/* 论文式标题区（参考维普信息卡片，浅黄背景） */
.paper-header {
  text-align: left;
  padding: 20px 24px;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 8px;
  margin-bottom: 20px;
}
.paper-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a1a;
  line-height: 1.4;
  margin: 0 0 12px;
  text-align: center;
}
.paper-authors {
  font-size: 14px;
  color: #555;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 10px;
}
.paper-authors b {
  color: #333;
  font-weight: 600;
}
.author-divider {
  color: #ccc;
}
.paper-meta {
  font-size: 13px;
  color: #777;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 16px;
}
.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.meta-item .el-icon {
  font-size: 14px;
}

/* 摘要区 */
.paper-abstract {
  background: #fff;
  border-radius: 8px;
  padding: 20px 28px;
  margin-bottom: 20px;
}
.abstract-label {
  font-size: 15px;
  font-weight: 700;
  color: #1a1a1a;
  margin-bottom: 10px;
}
.abstract-text {
  font-size: 14px;
  line-height: 1.9;
  color: #444;
  text-align: justify;
}
.abstract-indent {
  text-indent: 2em;
}
.abstract-keywords {
  margin-top: 14px;
  font-size: 13px;
  color: #555;
  line-height: 1.8;
}
.abstract-keywords b {
  color: #333;
}
.kw-divider {
  margin: 0 12px;
}

/* 论文章节 */
.paper-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px 28px;
  margin-bottom: 16px;
}
.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 16px;
  padding: 6px 0 6px 12px;
  border-left: 4px solid #409eff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: #409eff;
  color: #fff;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 600;
  margin-right: 4px;
}
.section-action {
  margin-left: auto;
}
.section-tag {
  margin-left: auto;
}

/* 学术风格表格 */
.table-wrap {
  overflow-x: auto;
}
.paper-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.paper-table th {
  background: #f5f7fa;
  color: #303133;
  font-weight: 600;
  padding: 10px 12px;
  border: 1px solid #e4e7ed;
  text-align: left;
}
.paper-table td {
  padding: 9px 12px;
  border: 1px solid #ebeef5;
  color: #606266;
}
.paper-table tbody tr:hover {
  background: #fafafa;
}
.table-summary td {
  background: #f5f7fa;
  font-weight: 600;
}

/* 页脚 */
.paper-footer {
  margin-top: 28px;
  text-align: center;
}
.footer-line {
  border-top: 1px solid #dcdfe6;
  margin-bottom: 12px;
}
.footer-note {
  font-size: 12px;
  color: #909399;
  margin: 0;
}

.form-tip {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}
</style>
