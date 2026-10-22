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
      <!-- 论文式标题区 -->
      <div class="paper-header">
        <h1 class="paper-title">{{ project.project_name }}</h1>
        <div class="paper-authors">
          <span class="author-item"><b>负责人：</b>{{ displayLeaderName }}</span>
          <span class="author-divider">|</span>
          <span class="author-item"><b>指导教师：</b>{{ displayTeacherName || '未绑定' }}</span>
          <span class="author-divider">|</span>
          <span class="author-item"><b>所属学院：</b>{{ displayCollegeName }}</span>
          <el-tag v-if="isBlindForExpert" type="warning" size="small" effect="light" class="blind-tag">
            盲审模式已启用，个人信息已脱敏
          </el-tag>
        </div>
        <div class="paper-meta">
          <span class="meta-item"><el-icon><Document /></el-icon> 编号：{{ project.project_no }}</span>
          <span class="meta-item"><el-icon><Collection /></el-icon> 类别：{{ project.project_type_name }}</span>
          <span class="meta-item"><el-icon><Medal /></el-icon> 级别：{{ project.project_level_name || '-' }}</span>
          <span class="meta-item"><el-icon><Trophy /></el-icon> 赛事：{{ project.competition_name ? (project.competition_session ? `${project.competition_name}（${project.competition_session}）` : project.competition_name) : '未关联' }}</span>
          <span class="meta-item"><el-icon><Calendar /></el-icon> {{ project.start_date || '-' }} ~ {{ project.end_date || '-' }}</span>
          <span class="meta-item"><el-icon><Wallet /></el-icon> 预算：¥ {{ Number(project.budget_amount || 0).toFixed(2) }}</span>
          <StatusTag
            :status="project.status"
            :label="project.status === 10 ? (project.resubmittable ? '已驳回（可修改重提）' : '已落选') : undefined"
            :override-type="project.status === 10 ? (project.resubmittable ? 'warning' : 'danger') : undefined"
          />
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

      <!-- 驳回提示：区分「可修改重提」与「落选（终局）」 -->
      <el-alert
        v-if="project.reject_reason"
        :type="isEliminated ? 'error' : 'warning'"
        :title="isEliminated ? '该项目已落选（终审未通过），不可再修改或重新提交' : '该项目已被驳回，请按以下意见修改后重新提交'"
        show-icon
        :closable="false"
        class="reject-alert"
      >
        <div class="reject-reason">{{ displayRejectReason }}</div>
      </el-alert>

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
                <td>{{ maskIdNumber(m.student_no) }}</td>
                <td>{{ maskName(m.student_name) }}</td>
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

      <!-- 5. 项目成果（展示已登记成果；登记入口仅项目负责人本人可见） -->
      <section v-if="canShowProgress" class="paper-section">
        <h2 class="section-title">
          <span class="section-num">5</span>项目成果
          <el-button
            v-if="isProjectLeader"
            type="primary"
            size="small"
            class="section-action"
            @click="goAchievements"
          >登记成果</el-button>
        </h2>
        <div class="table-wrap" v-if="achievements.length > 0">
          <table class="paper-table">
            <thead>
              <tr>
                <th style="width:70px">序号</th>
                <th>成果名称</th>
                <th style="width:110px">类型</th>
                <th style="width:140px">作者</th>
                <th style="width:150px">编号/证书号</th>
                <th style="width:160px">登记时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(a, i) in achievements" :key="a.id">
                <td align="center">{{ i + 1 }}</td>
                <td>{{ a.title }}</td>
                <td align="center">{{ achievementTypeMap[a.achievement_type] || '—' }}</td>
                <td>{{ a.author || '—' }}</td>
                <td>{{ a.achievement_no || '—' }}</td>
                <td>{{ formatDateTime(a.created_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <el-empty v-else description="暂未登记项目成果" :image-size="60" />
      </section>

      <!-- 6. 结项验收 -->
      <section v-if="project && project.status === 8" class="paper-section">
        <h2 class="section-title">
          <span class="section-num">6</span>结项验收
          <span class="section-action deadline-hint-wrap">
            <el-tag v-if="finalDeadlineText" :type="finalLocked ? 'info' : 'success'" size="small" effect="plain">{{ finalDeadlineText }}</el-tag>
            <el-button v-if="isProjectLeader && !finalSubmitted" type="success" size="small" :disabled="finalLocked" @click="goFinal">提交结项验收报告</el-button>
            <el-button v-else-if="canWithdrawFinal" type="warning" size="small" :loading="finalLoading" @click="handleWithdrawFinal">撤回报告提交</el-button>
          </span>
        </h2>
        <el-alert
          v-if="finalSubmitted"
          title="结项验收报告已提交，等待专家验收"
          type="success"
          :closable="false"
          show-icon
          class="final-submitted-alert"
        />
        <el-empty v-else description="项目已完成中期检查，请提交结项验收报告以完成结题" :image-size="60" />
      </section>

      <!-- 7. 变更/延期申请（学生可提交，教师/管理员可查看） -->
      <section class="paper-section">
        <h2 class="section-title">
          <span class="section-num">{{ sectionNum }}</span>变更/延期申请
          <span class="section-action deadline-hint-wrap">
            <el-tag v-if="changeDeadlineText" :type="changeLocked ? 'info' : 'success'" size="small" effect="plain">{{ changeDeadlineText }}</el-tag>
            <el-button v-if="canApplyChange" type="primary" size="small" :disabled="changeLocked" @click="openNewChange">提交申请</el-button>
          </span>
        </h2>
        <div class="table-wrap" v-if="changeList.length > 0">
          <table class="paper-table">
            <thead>
              <tr>
                <th style="width:70px">序号</th>
                <th style="width:100px">类型</th>
                <th>变更原因</th>
                <th style="width:100px">状态</th>
                <th style="width:160px">提交时间</th>
                <th v-if="userStore.isStudent && isProjectLeader" style="width:90px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(c, i) in changeList" :key="i">
                <td align="center">{{ i + 1 }}</td>
                <td>{{ changeTypeMap[c.change_type] }}</td>
                <td>{{ c.change_reason }}</td>
                <td align="center">
                  <el-tag :type="c.status === 3 ? 'success' : c.status === 4 ? 'danger' : c.status === 5 ? 'info' : 'warning'" size="small">
                    {{ c.status_name }}
                  </el-tag>
                </td>
                <td>{{ formatDateTime(c.submit_time) }}</td>
                <td v-if="userStore.isStudent && isProjectLeader" align="center">
                  <el-button v-if="c.status === 0" link type="warning" size="small" @click="handleWithdrawChange(c)">撤回</el-button>
                  <el-button v-else-if="c.status === 4 && canApplyChange" link type="primary" size="small" :disabled="changeLocked" @click="openResubmitChange(c)">修改重提</el-button>
                  <span v-else>—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <el-empty v-else description="暂无变更申请" :image-size="60" />
      </section>

      <!-- 审核操作（仅当前阶段有审核权限的用户可见；指导教师确认/学院初审/校级复审/专家评审均在此完成） -->
      <ReviewActionPanel :project-id="pid" :project="project" :review-history="reviewHistory" :section-num="reviewSectionNum" @submitted="loadData" />
    </template>

    <!-- 变更申请弹窗 -->
    <el-dialog center append-to-body :z-index="4000" v-model="showChangeDialog" :title="editingChangeId ? '修改并重新提交变更申请' : '提交变更/延期申请'" width="600px">
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { ArrowLeft, Document, Collection, Medal, Trophy, Calendar, Wallet } from '@element-plus/icons-vue'
import StatusTag from '@/components/StatusTag.vue'
import ProjectTimeline from '@/components/ProjectTimeline.vue'
import ProjectAttachmentList from '@/components/ProjectAttachmentList.vue'
import ReviewActionPanel from '@/components/ReviewActionPanel.vue'
import { useProcessStore } from '@/store/process'
import { useUserStore } from '@/store/user'
import { useProjectDetailStore } from '@/store/projectDetail'
import { useAppearanceStore } from '@/store/appearance'
import { useBlindReview } from '@/composables/useBlindReview'
import { getProjectDetail, withdrawFinal, listAchievements } from '@/api/project'
import { getReviewHistory, createChangeRequest, getChangeList, withdrawChangeRequest, resubmitChangeRequest } from '@/api/review'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const processStore = useProcessStore()
const userStore = useUserStore()
const dialogStore = useProjectDetailStore()
const appearanceStore = useAppearanceStore()
const { maskName, maskCollege, maskIdNumber } = useBlindReview(() => appearanceStore.isBlindMode)

// 盲审模式：仅专家角色需要脱敏（与列表页、原审核详情页保持一致）
const isBlindForExpert = computed(() => appearanceStore.isBlindMode && userStore.isExpert)

// 支持弹窗模式（prop 传入）和页面模式（route.params）
const props = defineProps<{ projectId?: number }>()
const pid = computed(() => props.projectId ?? Number(route.params.id))

const project = ref<any>(null)
const reviewHistory = ref<any[]>([])
const loading = ref(true)

const displayLeaderName = computed(() => (isBlindForExpert.value ? maskName(project.value?.leader_name) : project.value?.leader_name))
const displayTeacherName = computed(() => (isBlindForExpert.value ? maskName(project.value?.teacher_name) : project.value?.teacher_name))
const displayCollegeName = computed(() => (isBlindForExpert.value ? maskCollege(project.value?.college_name) : project.value?.college_name))

/** 驳回原因（直接展示后端原始文本） */
const displayRejectReason = computed(() => (project.value?.reject_reason as string | null) || '（未填写原因）')
/** 已落选：学院/校级/专家驳回为终局，不可再修改或重新提交 */
const isEliminated = computed(() => Number(project.value?.status) === 10 && !project.value?.resubmittable)

// 项目成果 / 中期检查仅在「已立项及之后」阶段可用（状态白名单，避免用 >=6 把驳回(10)/撤销(11)/待教师确认(12) 误判进来）
const PROGRESS_STATUS = [6, 7, 8, 9]
const canShowProgress = computed(() => !!project.value && PROGRESS_STATUS.includes(Number(project.value.status)))

// ========== 流程截止日（截止日驱动锁定） ==========
/** 距目标日期天数（负数=已过）；target 为空返回 0 */
function dayDiff(target: string | null | undefined): number {
  if (!target) return 0
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const t = new Date(`${String(target).slice(0, 10)}T00:00:00`)
  return Math.round((t.getTime() - today.getTime()) / 86400000)
}
/** 变更/延期申请：是否已锁定 + 截止提示（后端回填 change_locked/change_deadline） */
const changeLocked = computed(() => !!project.value?.change_locked)
// 仅「待校级复审(3)」「待专家评审(5)」两个审核段可提交变更申请，且仅项目负责人本人
const canApplyChange = computed(() => {
  const st = Number(project.value?.status)
  return userStore.isStudent && isProjectLeader.value && (st === 3 || st === 5)
})
const changeDeadlineText = computed(() => {
  const d = project.value?.change_deadline
  if (!d) return ''
  const ds = String(d).slice(0, 10)
  if (changeLocked.value) return `变更窗口已锁定（审核日 ${ds}）`
  return `距变更截止 ${dayDiff(d)} 天（${ds}）`
})
/** 结项验收报告：是否已过提交截止日 */
const finalLocked = computed(() => {
  const d = project.value?.final_deadline
  return !!d && dayDiff(d) < 0
})
const finalDeadlineText = computed(() => {
  const d = project.value?.final_deadline
  if (!d) return ''
  const ds = String(d).slice(0, 10)
  if (finalLocked.value) return `结题截止日已过（${ds}）`
  return `距结题截止 ${dayDiff(d)} 天（${ds}）`
})

/** 跳转独立页面：弹窗模式下先关闭弹窗，避免弹窗遮住目标页面 */
function goto(path: string) {
  if (props.projectId) dialogStore.close()
  router.push(path)
}

// 跳转到项目成果登记页（仅项目负责人本人可操作）
function goAchievements() {
  goto(`/projects/${pid.value}/achievements`)
}

// 跳转到结项验收页（仅项目负责人本人可操作）
function goFinal() {
  goto(`/projects/${pid.value}/final`)
}

// 是否为该项目负责人（成果登记入口仅对其显示）
const isProjectLeader = computed(() =>
  !!project.value && Number(userStore.userInfo?.id) === Number(project.value.leader_id)
)

// 项目成果列表（详情页只做展示，登记在独立页面完成）
const achievements = ref<any[]>([])
const achievementTypeMap: Record<number, string> = {
  1: '论文', 2: '专利', 3: '软著', 4: '竞赛', 5: '创业', 6: '其他',
}

// 预算合计
const totalBudget = computed(() =>
  (project.value?.budgets || []).reduce((s: number, b: any) => s + Number(b.budget_amount || 0), 0)
)

// 变更/延期申请的章节号（5/6/7 条件显示，需要动态计算）
const sectionNum = computed(() => {
  if (!project.value) return 7
  let n = 5
  if (canShowProgress.value) n += 1 // 项目成果
  if (project.value.status === 8) n++ // 结项验收
  return n
})

// 审核操作为详情页最后一个区块（变更/延期申请区块恒显示，故恒 +1）
const reviewSectionNum = computed(() => sectionNum.value + 1)

// 变更申请
const changeList = ref<any[]>([])
const showChangeDialog = ref(false)
const editingChangeId = ref<number | null>(null)  // 非空=正在修改重提被驳回的申请
const changeLoading = ref(false)
const changeFormRef = ref<FormInstance>()
const changeForm = reactive({
  change_type: undefined as number | undefined,
  change_reason: '',
  original_content: '',
  new_content: '',
})
const changeTypeMap: Record<number, string> = {
  1: '延期申请', 2: '人员变更', 3: '内容变更', 4: '预算调整', 5: '其他',
}
const changeTypeOptions = Object.entries(changeTypeMap).map(([key, label]) => ({
  value: Number(key), label,
}))
const changeRules: FormRules = {
  change_type: [{ required: true, message: '请选择变更类型', trigger: 'change' }],
  change_reason: [{ required: true, message: '请填写变更原因', trigger: 'blur' }],
}

// 结项验收
const finalLoading = ref(false)

/** 结项验收报告是否已提交（后端字段：待结题阶段提交报告后为 True） */
const finalSubmitted = computed(() => !!project.value?.final_report_submitted)
/** 撤回结项报告提交：仅项目负责人本人（或超管），且报告已提交 */
const canWithdrawFinal = computed(() =>
  finalSubmitted.value && (isProjectLeader.value || userStore.isSuperAdmin)
)

async function handleWithdrawFinal() {
  try {
    await ElMessageBox.confirm(
      '撤回后本次结项验收报告将作废，项目仍处于待结题，可修改后重新提交。确定撤回？',
      '撤回报告提交',
      { type: 'warning', confirmButtonText: '确定撤回', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  finalLoading.value = true
  try {
    await withdrawFinal(Number(pid.value))
    ElMessage.success('结项验收报告已撤回，可修改后重新提交')
    loadData()
  } finally {
    finalLoading.value = false
  }
}

// 侧边栏阶段点击 → 跳转到对应页面或滚动到对应区域
function scrollToSection(key: string) {
  const sectionMap: Record<string, string> = {
    declare: '审核流程',
    teacher: '审核流程',
    college: '审核流程',
    university: '审核流程',
    expert: '审核流程',
    approved: '审核流程',
    achievement: '项目成果',
    final: '结项验收',
    finished: '结项验收',
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
    const [detailRes, reviewRes, chgRes, achRes] = await Promise.all([
      getProjectDetail(id),
      getReviewHistory(id).catch(() => ({ data: { records: [] } })),
      getChangeList({ page: 1, page_size: 100, project_id: id }).catch(() => ({ data: { items: [] } })),
      listAchievements(id).catch(() => ({ data: [] })),
    ])
    project.value = detailRes.data
    // 将项目状态同步到主侧边栏的"过程管理"菜单
    processStore.setStatus(detailRes.data.status)
    reviewHistory.value = reviewRes.data?.records || []
    changeList.value = chgRes.data?.items || []
    achievements.value = achRes.data || []
    // 从独立子页（中期检查/成果登记）跳回详情页时，通过 ?scroll=key 定位到对应区块
    await nextTick()
    const scrollKey = route.query.scroll
    if (scrollKey && typeof scrollKey === 'string') {
      scrollToSection(scrollKey)
      router.replace({ path: route.path }).catch(() => {})
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

// ========== 变更申请 ==========
/** 打开「提交新申请」弹窗 */
function openNewChange() {
  editingChangeId.value = null
  changeForm.change_type = undefined
  changeForm.change_reason = ''
  changeForm.original_content = ''
  changeForm.new_content = ''
  showChangeDialog.value = true
}

/** 打开「修改重提」弹窗（复用被驳回的记录） */
function openResubmitChange(row: any) {
  editingChangeId.value = row.id
  changeForm.change_type = row.change_type
  changeForm.change_reason = row.change_reason || ''
  changeForm.original_content = row.original_content || ''
  changeForm.new_content = row.new_content || ''
  showChangeDialog.value = true
}

async function handleSubmitChange() {
  if (!changeFormRef.value) return
  await changeFormRef.value.validate(async (valid) => {
    if (!valid) return
    changeLoading.value = true
    try {
      const payload = {
        project_id: Number(pid.value),
        change_type: changeForm.change_type!,
        change_reason: changeForm.change_reason,
        original_content: changeForm.original_content || undefined,
        new_content: changeForm.new_content || undefined,
      }
      if (editingChangeId.value) {
        await resubmitChangeRequest(editingChangeId.value, payload)
        ElMessage.success('变更申请已重新提交')
      } else {
        await createChangeRequest(payload)
        ElMessage.success('变更申请已提交')
      }
      showChangeDialog.value = false
      editingChangeId.value = null
      changeFormRef.value?.resetFields()
      loadData()
    } finally {
      changeLoading.value = false
    }
  })
}

/** 撤回待审核的变更申请（申请人本人） */
async function handleWithdrawChange(row: any) {
  try {
    await ElMessageBox.confirm('撤回后该变更申请作废，如需变更需重新提交。确定撤回？', '撤回变更申请', {
      type: 'warning', confirmButtonText: '确定撤回', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await withdrawChangeRequest(row.id)
  ElMessage.success('已撤回')
  loadData()
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

/* 驳回 / 落选 提示 */
.reject-alert {
  margin-bottom: 16px;
}
.reject-reason {
  margin-top: 4px;
  white-space: pre-wrap;
}
.final-submitted-alert {
  margin-bottom: 0;
}

/* 盲审提示标签 */
.blind-tag {
  margin-left: 12px;
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
.deadline-hint-wrap {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
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

.form-tip {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}
</style>
