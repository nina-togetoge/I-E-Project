<!--
  页面 / 组件名称：项目详情（维普学术论文风格；支持页面模式与弹窗模式）
  面向角色：项目负责人、团队成员、指导教师、学院 / 校级管理员、评审专家（专家可盲审）
  核心功能：展示项目完整信息（标题、摘要、团队、预算、附件、成果、结项、变更申请），
           内嵌审核流程时间轴与审核操作面板，支持提交 / 修改 / 撤回变更申请与结项报告。
  调用 API：getProjectDetail、getReviewHistory、getChangeList、listAchievements、
           createChangeRequest、resubmitChangeRequest、withdrawChangeRequest、withdrawFinal。
  权限 / 状态约束：
    - 成果登记与结项报告提交仅项目负责人本人；审核面板按当前阶段与角色决定是否渲染。
    - 变更申请仅学生负责人、且项目处于「待校级复审(3)」或「待专家评审(5)」时开放；
      后端回填 change_locked / change_deadline 后到期自动锁定。
    - 结项报告撤回仅「待验收(1)」且未过截止日，负责人或超管可操作。
    - 驳回(10) 区分「可修改重提」与「落选（终局）」，文案与颜色随之变化。
  关键交互：
    - 弹窗模式下点「成果登记 / 结项验收」会先关闭详情弹窗再跳转，避免遮住目标页。
    - 从子页返回时携带 ?scroll=key，加载完成后滚动到对应区块并清理 query。
    - 盲审脱敏只对专家角色生效；项目状态会同步到主侧边栏「过程管理」。
    - 变更申请弹窗新建与「修改重提」复用同一表单，编辑态仅由 editingChangeId 区分。
-->
<template>
  <div class="page-container" v-loading="loading">
    <!-- 返回按钮：仅页面模式显示；弹窗模式由外层关闭，不需要返回 -->
    <div class="back-bar" v-if="!props.projectId">
      <el-button text @click="router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
    </div>

    <template v-if="project">
      <!-- 论文式标题区：模拟学术论文首页，集中展示负责人、教师、学院与项目元信息；
           专家盲审时姓名 / 学院走脱敏显示，并给出提示标签 -->
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

      <!-- 摘要区：纯文本摘要 + 富文本创新点 / 预期成果，富文本由 RichText 统一渲染 -->
      <div class="paper-abstract">
        <div class="abstract-label">摘　要</div>
        <div class="abstract-text">
          <span class="abstract-indent">{{ project.project_summary || '暂无摘要' }}</span>
        </div>
        <div class="abstract-keywords">
          <div class="kw-row">
            <b>创新点：</b>
            <RichText class="kw-text" :content="project.innovation_points || '暂无'" />
          </div>
          <div class="kw-row">
            <b>预期成果：</b>
            <RichText class="kw-text" :content="project.expected_results || '暂无'" />
          </div>
        </div>
      </div>

      <!-- 驳回提示：区分「可修改重提」与「落选（终局）」；
           落选用 error 样式并明确不可再提交，可重提用 warning 引导按意见修改 -->
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

      <!-- 1. 审核流程：时间轴按时间正序拼接创建、提交、各阶段审核、立项、结项、驳回事件 -->
      <section class="paper-section">
        <h2 class="section-title"><span class="section-num">1</span>审核流程</h2>
        <ProjectTimeline :project="project" :review-history="reviewHistory" />
      </section>

      <!-- 2. 团队成员：学号与姓名在盲审模式下脱敏，分工保持原样供专家评估团队构成 -->
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

      <!-- 3. 预算明细：逐科目展示并由前端实时合计，合计值仅用于展示，不参与后端校验 -->
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

      <!-- 4. 申报附件：只读展示，预览 / 下载均通过 ProjectAttachmentList 统一处理鉴权 -->
      <section class="paper-section">
        <h2 class="section-title"><span class="section-num">4</span>申报附件</h2>
        <ProjectAttachmentList :attachments="project.attachments" />
      </section>

      <!-- 5. 项目成果：详情页只做展示；「登记成果」仅项目负责人本人可见，
           且整个区块只在已立项及之后的状态（6/7/8/9）出现 -->
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

      <!-- 6. 结项验收：仅在待结题(8)/已结题(9)出现；
           报告状态 0 未提交、1 待验收、2 已通过、3 已驳回：
           驳回状态允许修改重提且不受截止日限制，待验收且未过截止日可撤回 -->
      <section v-if="project && (project.status === 8 || project.status === 9)" class="paper-section">
        <h2 class="section-title">
          <span class="section-num">6</span>结项验收
          <span class="section-action deadline-hint-wrap">
            <el-tag v-if="project.status === 8 && finalDeadlineText" :type="finalLocked ? 'info' : 'success'" size="small" effect="plain">{{ finalDeadlineText }}</el-tag>
            <el-button
              v-if="isProjectLeader && project.status === 8 && (finalReportStatus === 0 || finalReportStatus === 3)"
              type="success"
              size="small"
              :disabled="finalLocked && finalReportStatus !== 3"
              @click="goFinal"
            >{{ finalReportStatus === 3 ? '修改并重新提交' : '提交结项验收报告' }}</el-button>
            <el-button v-else-if="canWithdrawFinal" type="warning" size="small" :loading="finalLoading" @click="handleWithdrawFinal">撤回报告提交</el-button>
            <el-button v-else-if="finalReportStatus > 0" size="small" @click="goFinal">查看结项报告</el-button>
          </span>
        </h2>
        <el-alert
          v-if="finalReportStatus === 2"
          title="结项验收已通过，项目已结题"
          type="success"
          :closable="false"
          show-icon
          class="final-submitted-alert"
        />
        <el-alert
          v-else-if="finalReportStatus === 3"
          :title="`验收驳回：${project.final_reject_reason || project.reject_reason || '请修改后重新提交'}`"
          type="error"
          :closable="false"
          show-icon
          class="final-submitted-alert"
        />
        <el-alert
          v-else-if="finalReportStatus === 1"
          title="结项验收报告已提交，等待专家验收"
          type="success"
          :closable="false"
          show-icon
          class="final-submitted-alert"
        />
        <el-empty v-else description="项目已完成中期检查，请提交结项验收报告以完成结题" :image-size="60" />
      </section>

      <!-- 7. 变更 / 延期申请：学生负责人可提交，教师与管理员只读；
           列表中的「撤回」只对草稿(0)开放，「修改重提」只对已驳回(4)且窗口未锁定开放 -->
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

      <!-- 审核操作：面板内部再次按「当前阶段 + 角色 + 是否已评审」判断是否渲染，
           指导教师确认 / 学院初审 / 校级复审 / 专家评审 / 中期审核均在此完成 -->
      <ReviewActionPanel :project-id="pid" :project="project" :review-history="reviewHistory" :section-num="reviewSectionNum" @submitted="loadData" />
    </template>

    <!-- 变更申请弹窗：新建与「修改重提」共用一个表单；
         append-to-body + 高 z-index 保证嵌套在详情弹窗内时仍能盖在上层 -->
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
        <!-- 提交前由 el-form 规则校验必填项；修改重提时 editingChangeId 决定调用哪个接口 -->
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
import RichText from '@/components/RichText.vue'
import ReviewActionPanel from '@/components/ReviewActionPanel.vue'
import { useProcessStore } from '@/store/process'
import { useUserStore } from '@/store/user'
import { useProjectDetailStore } from '@/store/projectDetail'
import { useAppearanceStore } from '@/store/appearance'
import { useBlindReview } from '@/composables/useBlindReview'
import { getProjectDetail, withdrawFinal, listAchievements } from '@/api/project'
import { getReviewHistory, createChangeRequest, getChangeList, withdrawChangeRequest, resubmitChangeRequest } from '@/api/review'
import { formatDateTime } from '@/utils/format'

// ==================== 路由 / Store / 盲审脱敏 ====================
// 弹窗模式由 props.projectId 驱动，页面模式从 route.params.id 取项目 ID；
// dialogStore 用于关闭外层详情弹窗，appearanceStore 提供全局盲审开关。
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

/** 项目详情原始数据；加载完成前整个内容区不渲染 */
const project = ref<any>(null)
/** 审核记录：既用于时间轴，也用于审核面板判断「当前用户是否已评审」 */
const reviewHistory = ref<any[]>([])
/** 首屏加载态 */
const loading = ref(true)

// 展示名：普通角色原样返回，专家在盲审模式下走脱敏方法
const displayLeaderName = computed(() => (isBlindForExpert.value ? maskName(project.value?.leader_name) : project.value?.leader_name))
const displayTeacherName = computed(() => (isBlindForExpert.value ? maskName(project.value?.teacher_name) : project.value?.teacher_name))
const displayCollegeName = computed(() => (isBlindForExpert.value ? maskCollege(project.value?.college_name) : project.value?.college_name))

/** 驳回原因（直接展示后端原始文本） */
const displayRejectReason = computed(() => (project.value?.reject_reason as string | null) || '（未填写原因）')
/** 已落选：学院/校级/专家驳回为终局，不可再修改或重新提交 */
const isEliminated = computed(() => Number(project.value?.status) === 10 && !project.value?.resubmittable)

// 状态白名单：中期检查 / 成果登记 / 结项只对已立项及之后开放，
// 不用 >=6 是为了避免把驳回(10)、撤销(11)、待教师确认(12) 误判为已立项
const PROGRESS_STATUS = [6, 7, 8, 9]
const canShowProgress = computed(() => !!project.value && PROGRESS_STATUS.includes(Number(project.value.status)))

// ========== 流程截止日（截止日驱动锁定） ==========
/** 距目标日期天数（负数=已过；target 为空返回 0）；只比较到「日」，忽略时分秒 */
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
/** 结项验收报告：是否已过提交截止日；过期后仅「已驳回(3)」仍可重提 */
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

/**
 * 跳转独立页面。
 * 说明：弹窗模式下必须先关闭详情弹窗，否则目标页面会被遮罩挡住。
 * 参数 path：目标路由路径。
 */
function goto(path: string) {
  if (props.projectId) dialogStore.close()
  router.push(path)
}

/** 跳转到项目成果登记页（仅项目负责人本人可操作） */
function goAchievements() {
  goto(`/projects/${pid.value}/achievements`)
}

/** 跳转到结项验收页（仅项目负责人本人可操作） */
function goFinal() {
  goto(`/projects/${pid.value}/final`)
}

// 是否为该项目负责人（成果登记入口仅对其显示）
const isProjectLeader = computed(() =>
  !!project.value && Number(userStore.userInfo?.id) === Number(project.value.leader_id)
)

// 项目成果列表：详情页只做展示，登记动作在独立页面完成
const achievements = ref<any[]>([])
/** 成果类型码到中文名称的映射，与后端 AchievementType 保持一致 */
const achievementTypeMap: Record<number, string> = {
  1: '论文', 2: '专利', 3: '软著', 4: '竞赛', 5: '创业', 6: '其他',
}

/** 预算合计：前端按科目金额累加，仅用于展示 */
const totalBudget = computed(() =>
  (project.value?.budgets || []).reduce((s: number, b: any) => s + Number(b.budget_amount || 0), 0)
)

// 变更/延期申请的章节号（5/6/7 条件显示，需要动态计算）
const sectionNum = computed(() => {
  if (!project.value) return 7
  let n = 5
  if (canShowProgress.value) n += 1 // 项目成果
  if ([8, 9].includes(project.value.status)) n++ // 结项验收（含已结题回看）
  return n
})

// 审核操作为详情页最后一个区块（变更/延期申请区块恒显示，故恒 +1）
const reviewSectionNum = computed(() => sectionNum.value + 1)

// 变更 / 延期申请状态：changeList 为当前项目全部申请记录；
// editingChangeId 非空表示正在「修改重提」某条被驳回的记录，为空则是新建
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

// 结项验收相关：finalLoading 覆盖提交 / 撤回按钮，防止重复请求
const finalLoading = ref(false)

/** 结项报告状态：0未提交 1待验收 2已通过 3已驳回 */
const finalReportStatus = computed(() => Number(project.value?.final_report_status ?? 0))
/** 撤回结项报告提交：仅报告待验收 + 未过截止日 + 负责人/超管 */
const canWithdrawFinal = computed(() =>
  finalReportStatus.value === 1
  && !finalLocked.value
  && (isProjectLeader.value || userStore.isSuperAdmin)
)

/**
 * 撤回结项验收报告。
 * 说明：撤回后本次报告作废，项目仍为待结题，可修改后重新提交；
 * 仅报告待验收(1)、未过截止日且为负责人 / 超管时才显示入口。
 * 失败处理：取消确认直接返回；接口异常由全局拦截器提示。
 */
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

/**
 * 按阶段 key 滚动到对应区块。
 * 说明：阶段 key 来自主侧边栏「过程管理」，多个阶段共享「审核流程」区块；
 * 通过匹配章节标题文本定位，避免依赖额外 DOM id。
 * 参数 key：阶段标识（declare / teacher / achievement / final 等）。
 */
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

/**
 * 并行加载详情、审核记录、变更申请与成果列表。
 * 副作用：写入 project / reviewHistory / changeList / achievements，
 *        并把项目状态同步到主侧边栏；必要时执行 ?scroll= 定位。
 * 失败处理：详情失败时提示「加载失败」，其余接口各自降级为空数组，不阻断主流程。
 */
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

// ==================== 变更申请 ====================
/**
 * 打开「提交新申请」弹窗。
 * 副作用：清空编辑态与表单，确保不会带入上一条被驳回记录的字段。
 */
/** 打开「提交新申请」弹窗 */
function openNewChange() {
  editingChangeId.value = null
  changeForm.change_type = undefined
  changeForm.change_reason = ''
  changeForm.original_content = ''
  changeForm.new_content = ''
  showChangeDialog.value = true
}

/**
 * 打开「修改重提」弹窗：复用被驳回记录的内容。
 * 参数 row：变更申请记录；editingChangeId 置为 row.id 以切换为修提交径。
 */
/** 打开「修改重提」弹窗（复用被驳回的记录） */
function openResubmitChange(row: any) {
  editingChangeId.value = row.id
  changeForm.change_type = row.change_type
  changeForm.change_reason = row.change_reason || ''
  changeForm.original_content = row.original_content || ''
  changeForm.new_content = row.new_content || ''
  showChangeDialog.value = true
}

/**
 * 提交变更申请：表单校验通过后，按是否存在 editingChangeId 选择新建或重提接口。
 * 副作用：成功后关闭弹窗、重置表单并刷新详情与申请列表。
 * 失败处理：校验失败不请求；接口异常由全局拦截器提示，finally 复位 loading。
 */
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

/** 撤回待审核的变更申请（申请人本人）；撤回后该记录作废，需重新提交 */
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

// 页面挂载即加载详情；离开时清理侧边栏阶段状态，避免影响其他页面
onMounted(() => loadData())
onBeforeUnmount(() => processStore.reset())

// 弹窗模式下外部切换项目时重新加载；页面模式由路由变化触发组件重建，无需监听
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
.kw-row {
  display: flex;
  align-items: flex-start;
  gap: 2px;
}
.kw-row + .kw-row {
  margin-top: 6px;
}
.kw-text {
  flex: 1;
  min-width: 0;
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
