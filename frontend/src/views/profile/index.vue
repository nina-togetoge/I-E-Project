<!--
  ==== 个人中心 ====
  解决的问题：所有角色都需要维护自己的联系方式与头像，并在首次登录/安全事件后强制修改密码。
  对应角色与路由：登录后的全部角色可访问，路由 /profile（无 roles 限制）。
  依赖 API：
    - PATCH /api/users/me/profile 更新姓名/邮箱/手机号/头像（userStore.updateProfile 复用该接口）；
    - userStore.changePassword 调用后端修改密码接口。
  业务规则：
    - 用户名与年级不可自助修改：用户名是账号标识，年级由学籍信息维护，仅学生展示年级。
    - 超管与学院管理员共用 role=4，页面通过 roleName 区分展示；
      学院为空时展示 displayCollegeName 的兜底（学校名称）。
    - 安全性要求 [P0-2]：URL 带 forceReset=1 时进入强制改密模式，锁定其他 Tab，
      必须修改初始密码后才能继续使用系统。
  关键交互流程：点头像 -> 裁剪上传 -> 先本地回显再调接口保存；
    基本信息/修改密码各自独立校验后提交。
-->
<template>
  <div class="page-container">
    <!-- 区块：左右两栏布局，左窄右宽；左侧固定展示身份信息，右侧承载可编辑表单 -->
    <el-row :gutter="20">
      <!-- 区块：左侧个人名片，展示头像、姓名、角色与所属学院 -->
      <el-col :span="8">
        <el-card shadow="never" class="profile-card">
          <div class="profile-header">
            <!-- 头像可点击，触发裁剪弹窗；未设置头像时用姓名首字占位 -->
            <div class="avatar-wrapper" @click="cropperVisible = true">
              <el-avatar :size="80" :src="tempAvatar || userStore.userInfo?.avatar || undefined">
                {{ userStore.userInfo?.real_name?.[0] || 'U' }}
              </el-avatar>
              <div class="avatar-edit-badge">
                <el-icon :size="14"><EditPen /></el-icon>
              </div>
            </div>
            <h3>{{ userStore.userInfo?.real_name }}</h3>
            <!-- 角色标签：由后端 role_name 下发，超管与学院管理员同属 role=4 但名称不同 -->
            <el-tag size="small">{{ userStore.roleName }}</el-tag>
            <p class="profile-college">{{ userStore.displayCollegeName || '暂无学院' }}</p>
          </div>
        </el-card>
      </el-col>

      <!-- 区块：头像裁剪弹窗，裁剪结果通过 success 事件回传 base64 -->
      <AvatarCropper
        v-model:visible="cropperVisible"
        @success="handleAvatarSuccess"
      />

      <!-- 区块：右侧功能区，基本信息与修改密码两个 Tab -->
      <el-col :span="16">
        <!-- 右侧卡片：用 Tab 隔离资料修改与密码修改，before-leave 负责强制改密拦截 -->
        <el-card shadow="never">
          <el-tabs v-model="activeTab" :before-leave="beforeTabChange">
            <!-- 基本信息：用户名/年级只读，姓名、邮箱、手机号可编辑 -->
            <el-tab-pane label="基本信息" name="info">
              <el-form ref="infoFormRef" :model="infoForm" :rules="infoRules" label-width="80px">
                <el-form-item label="用户名">
                  <el-input :value="userStore.userInfo?.username" disabled />
                </el-form-item>
                <!-- 年级仅学生展示；由学籍数据决定，不允许自行修改 -->
                <el-form-item v-if="userStore.isStudent" label="年级">
                  <el-input :value="userStore.userInfo?.grade || '—'" disabled />
                </el-form-item>
                <el-form-item label="姓名" prop="real_name">
                  <el-input v-model="infoForm.real_name" maxlength="64" show-word-limit />
                </el-form-item>
                <el-form-item label="邮箱" prop="email">
                  <el-input v-model="infoForm.email" maxlength="128" show-word-limit />
                </el-form-item>
                <el-form-item label="手机号" prop="phone">
                  <el-input v-model="infoForm.phone" maxlength="11" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="saveLoading" @click="handleSaveInfo">保存修改</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <!-- 修改密码：需校验当前密码，新密码有强度提示与确认一致性校验 -->
            <el-tab-pane label="修改密码" name="password">
              <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="100px" style="max-width: 400px;">
                <el-form-item label="当前密码" prop="old_password">
                  <el-input v-model="pwdForm.old_password" type="password" show-password maxlength="6" />
                </el-form-item>
                <el-form-item label="新密码" prop="new_password">
                  <el-input v-model="pwdForm.new_password" type="password" show-password maxlength="6" />
                  <PasswordStrength :password="pwdForm.new_password" />
                </el-form-item>
                <el-form-item label="确认密码" prop="confirm_password">
                  <el-input v-model="pwdForm.confirm_password" type="password" show-password maxlength="6" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="pwdLoading" @click="handleChangePassword">修改密码</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
// ==================== 导入 ====================
import { ref, reactive, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { EditPen } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import PasswordStrength from '@/components/PasswordStrength.vue'
import AvatarCropper from '@/components/AvatarCropper.vue'
import { patch } from '@/utils/request'
import {
  passwordValidator,
  confirmPasswordValidator,
  phoneValidator,
  emailValidator,
  requiredValidator,
} from '@/utils/validators'

// ==================== 状态 ====================
/** 用户 Store：userInfo / roleName / isStudent / displayCollegeName 均从登录态读取 */
const userStore = useUserStore()
/** 当前路由，用于读取 tab 与 forceReset 参数 */
const route = useRoute()
/** 当前激活 Tab：info=基本信息，password=修改密码 */
const activeTab = ref('info')
/** [P0-2] 强制改密模式：锁死 Tab 切换，必须改密 */
const forceResetMode = ref(false)
/** 头像裁剪弹窗显隐 */
const cropperVisible = ref(false)
/** 裁剪后的头像 base64 临时值，用于本地立即回显 */
const tempAvatar = ref('')

/**
 * 头像裁剪完成回调。
 * 先更新 Store 与 sessionStorage 做即时回显，再调用 PATCH 接口持久化；
 * 失败时保留旧头像并提示重试。
 * 副作用：写 Store、写 sessionStorage、发起 PATCH 请求、提示结果。
 * @param dataUrl 裁剪后的图片 base64 数据
 */
async function handleAvatarSuccess(dataUrl: string) {
  tempAvatar.value = dataUrl
  // 先更新前端展示，保证即时反馈
  if (userStore.userInfo) {
    userStore.userInfo.avatar = dataUrl
    sessionStorage.setItem('user_info', JSON.stringify(userStore.userInfo))
  }
  try {
    await patch('/api/users/me/profile', { avatar: dataUrl })
    ElMessage.success('头像更新成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '头像更新失败，请重试')
  }
}

// ==================== 表单实例与提交状态 ====================
/** 基本信息表单实例 */
const infoFormRef = ref<FormInstance>()
/** 修改密码表单实例 */
const pwdFormRef = ref<FormInstance>()
/** 基本信息保存中标记 */
const saveLoading = ref(false)
/** 修改密码提交中标记 */
const pwdLoading = ref(false)

// ==================== 强制改密 ====================
/**
 * 强制改密时，禁止切换到其他 Tab。
 * 触发时机：Tab 切换前（before-leave）。
 * @param newTab 目标 Tab 名称
 * @returns true 允许切换；false 阻止并弹出安全提示
 */
function beforeTabChange(newTab: string) {
  if (forceResetMode.value && newTab !== 'password') {
    ElMessageBox.alert('为保障账户安全，请先修改初始密码后再继续使用。', '请先修改密码', {
      confirmButtonText: '我知道了',
      type: 'warning',
      showClose: false,
    })
    return false
  }
  return true
}

/**
 * 监听 URL 参数，进入强制改密模式。
 * 触发时机：组件挂载时立即执行一次，以及 route.query 的 tab/forceReset 变化时。
 * 目的：兼容两种入口 —— 直接深链 tab=password，或首次登录由守卫附加 forceReset=1。
 * 副作用：改写 activeTab / forceResetMode；onCleanup 仅用于在重跑前标记取消。
 */
watch(
  () => [route.query.tab, route.query.forceReset],
  ([tab, forceReset], _old, onCleanup) => {
    let cancelled = false
    onCleanup(() => { cancelled = true })
    if (cancelled) return
    if (tab === 'password') {
      activeTab.value = 'password'
    }
    if (forceReset === '1') {
      forceResetMode.value = true
      activeTab.value = 'password'
    }
  },
  { immediate: true },
)

// ==================== 表单模型 ====================
/** 基本信息表单：只包含允许自助修改的三个字段 */
const infoForm = reactive({
  real_name: '',
  email: '',
  phone: '',
})

/**
 * 基本信息校验规则：
 * 姓名必填，邮箱/手机号非必填但填了必须格式合法（false 表示允许为空）。
 */
const infoRules: FormRules = {
  real_name: [{ validator: requiredValidator('姓名'), trigger: 'blur' }],
  email: [{ validator: emailValidator(false, '邮箱'), trigger: 'blur' }],
  phone: [{ validator: phoneValidator(false, '手机号'), trigger: 'blur' }],
}

/** 修改密码表单：当前密码 + 新密码 + 确认密码 */
const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

/**
 * 修改密码校验规则：
 * 当前密码/新密码需符合密码强度要求；确认密码需与新密码一致（用 getter 实时取值）。
 */
const pwdRules: FormRules = {
  old_password: [{ validator: passwordValidator(true, '当前密码'), trigger: 'blur' }],
  new_password: [{ validator: passwordValidator(true, '新密码'), trigger: 'blur' }],
  confirm_password: [
    {
      validator: confirmPasswordValidator(() => pwdForm.new_password, '确认密码'),
      trigger: 'blur',
    },
  ],
}

// ==================== 事件处理 ====================
/**
 * 保存基本信息。
 * 流程：表单校验 -> userStore.updateProfile 提交（内部 PATCH 并同步本地用户信息）->
 *   成功提示。
 * 副作用：发起更新请求、刷新 Store 中的用户信息、提示结果。
 */
async function handleSaveInfo() {
  if (!infoFormRef.value) return
  await infoFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    saveLoading.value = true
    try {
      await userStore.updateProfile({
        real_name: infoForm.real_name,
        email: infoForm.email,
        phone: infoForm.phone,
      })
      ElMessage.success('修改成功')
    } finally {
      saveLoading.value = false
    }
  })
}

/**
 * 修改密码。
 * 流程：表单校验（含新旧密码强度与确认一致性）-> userStore.changePassword ->
 *   成功提示 -> 清空三个输入框，防止密码残留在页面上。
 * 副作用：发起修改请求、提示结果、重置本地表单字段。
 */
async function handleChangePassword() {
  if (!pwdFormRef.value) return
  await pwdFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return
    pwdLoading.value = true
    try {
      await userStore.changePassword(pwdForm.old_password, pwdForm.new_password)
      ElMessage.success('密码修改成功')
      pwdForm.old_password = ''
      pwdForm.new_password = ''
      pwdForm.confirm_password = ''
    } finally {
      pwdLoading.value = false
    }
  })
}

// ==================== 生命周期 ====================
/**
 * 挂载时用登录态中的用户信息回填基本信息表单。
 * 目的：避免用户看到空表单或在未修改时提交空值。
 */
onMounted(() => {
  if (userStore.userInfo) {
    infoForm.real_name = userStore.userInfo.real_name || ''
    infoForm.email = userStore.userInfo.email || ''
    infoForm.phone = userStore.userInfo.phone || ''
  }
})
</script>

<style scoped>
/* 名片内容整体居中，突出头像与角色身份 */
.profile-card { text-align: center; }
.profile-header { padding: 20px 0; }
.profile-header h3 { margin: 12px 0 8px; font-size: 18px; color: #303133; }
.profile-college { margin-top: 8px; font-size: 14px; color: #909399; }

/* 头像容器：相对定位以便右下角叠加编辑角标，cursor:pointer 提示可点击更换 */
.avatar-wrapper {
  position: relative;
  display: inline-block;
  cursor: pointer;
}
/* 悬停变暗：给用户「可操作」的即时反馈 */
.avatar-wrapper:hover :deep(.el-avatar) {
  filter: brightness(0.85);
  transition: filter 0.2s;
}
/* 编辑角标：右下角圆形按钮，用白色描边与卡片背景区分 */
.avatar-edit-badge {
  position: absolute;
  right: -4px;
  bottom: -4px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--primary-color, #409EFF);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}
</style>
