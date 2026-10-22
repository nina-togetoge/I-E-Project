<!--
  个人中心
  信息修改、密码修改、头像上传
-->
<template>
  <div class="page-container">
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card shadow="never" class="profile-card">
          <div class="profile-header">
            <div class="avatar-wrapper" @click="cropperVisible = true">
              <el-avatar :size="80" :src="tempAvatar || userStore.userInfo?.avatar || undefined">
                {{ userStore.userInfo?.real_name?.[0] || 'U' }}
              </el-avatar>
              <div class="avatar-edit-badge">
                <el-icon :size="14"><EditPen /></el-icon>
              </div>
            </div>
            <h3>{{ userStore.userInfo?.real_name }}</h3>
            <el-tag size="small">{{ userStore.roleName }}</el-tag>
            <p class="profile-college">{{ userStore.displayCollegeName || '暂无学院' }}</p>
          </div>
        </el-card>
      </el-col>

      <AvatarCropper
        v-model:visible="cropperVisible"
        @success="handleAvatarSuccess"
      />

      <el-col :span="16">
        <el-card shadow="never">
          <el-tabs v-model="activeTab" :before-leave="beforeTabChange">
            <el-tab-pane label="基本信息" name="info">
              <el-form ref="infoFormRef" :model="infoForm" :rules="infoRules" label-width="80px">
                <el-form-item label="用户名">
                  <el-input :value="userStore.userInfo?.username" disabled />
                </el-form-item>
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

const userStore = useUserStore()
const route = useRoute()
const activeTab = ref('info')
/** [P0-2] 强制改密模式：锁死 Tab 切换，必须改密 */
const forceResetMode = ref(false)
const cropperVisible = ref(false)
const tempAvatar = ref('')

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

const infoFormRef = ref<FormInstance>()
const pwdFormRef = ref<FormInstance>()
const saveLoading = ref(false)
const pwdLoading = ref(false)

/** 强制改密时，禁止切换到其他 Tab */
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

/** 监听 URL 参数，进入强制改密模式 */
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

const infoForm = reactive({
  real_name: '',
  email: '',
  phone: '',
})

const infoRules: FormRules = {
  real_name: [{ validator: requiredValidator('姓名'), trigger: 'blur' }],
  email: [{ validator: emailValidator(false, '邮箱'), trigger: 'blur' }],
  phone: [{ validator: phoneValidator(false, '手机号'), trigger: 'blur' }],
}

const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

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

onMounted(() => {
  if (userStore.userInfo) {
    infoForm.real_name = userStore.userInfo.real_name || ''
    infoForm.email = userStore.userInfo.email || ''
    infoForm.phone = userStore.userInfo.phone || ''
  }
})
</script>

<style scoped>
.profile-card { text-align: center; }
.profile-header { padding: 20px 0; }
.profile-header h3 { margin: 12px 0 8px; font-size: 18px; color: #303133; }
.profile-college { margin-top: 8px; font-size: 14px; color: #909399; }

.avatar-wrapper {
  position: relative;
  display: inline-block;
  cursor: pointer;
}
.avatar-wrapper:hover :deep(.el-avatar) {
  filter: brightness(0.85);
  transition: filter 0.2s;
}
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
