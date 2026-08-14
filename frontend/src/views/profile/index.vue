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
            <el-avatar :size="80" :src="userStore.userInfo?.avatar || undefined">
              {{ userStore.userInfo?.real_name?.[0] || 'U' }}
            </el-avatar>
            <h3>{{ userStore.userInfo?.real_name }}</h3>
            <el-tag size="small">{{ userStore.roleName }}</el-tag>
            <p class="profile-college">{{ userStore.userInfo?.college_name || '暂无学院' }}</p>
          </div>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="never">
          <el-tabs v-model="activeTab">
            <el-tab-pane label="基本信息" name="info">
              <el-form ref="infoFormRef" :model="infoForm" :rules="infoRules" label-width="80px">
                <el-form-item label="用户名">
                  <el-input :value="userStore.userInfo?.username" disabled />
                </el-form-item>
                <el-form-item label="姓名" prop="real_name">
                  <el-input v-model="infoForm.real_name" />
                </el-form-item>
                <el-form-item label="邮箱" prop="email">
                  <el-input v-model="infoForm.email" />
                </el-form-item>
                <el-form-item label="手机号" prop="phone">
                  <el-input v-model="infoForm.phone" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="saveLoading" @click="handleSaveInfo">保存修改</el-button>
                </el-form-item>
              </el-form>
            </el-tab-pane>

            <el-tab-pane label="修改密码" name="password">
              <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="100px" style="max-width: 400px;">
                <el-form-item label="当前密码" prop="old_password">
                  <el-input v-model="pwdForm.old_password" type="password" show-password />
                </el-form-item>
                <el-form-item label="新密码" prop="new_password">
                  <el-input v-model="pwdForm.new_password" type="password" show-password />
                </el-form-item>
                <el-form-item label="确认密码" prop="confirm_password">
                  <el-input v-model="pwdForm.confirm_password" type="password" show-password />
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
import { ref, reactive, onMounted, type FormInstance, type FormRules } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const activeTab = ref('info')

const infoFormRef = ref<FormInstance>()
const pwdFormRef = ref<FormInstance>()
const saveLoading = ref(false)
const pwdLoading = ref(false)

const infoForm = reactive({
  real_name: '',
  email: '',
  phone: '',
})

const infoRules: FormRules = {
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [{ type: 'email', message: '请输入正确的邮箱', trigger: 'blur' }],
}

const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const pwdRules: FormRules = {
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== pwdForm.new_password) callback(new Error('两次密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

async function handleSaveInfo() {
  if (!infoFormRef.value) return
  await infoFormRef.value.validate(async (valid) => {
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
  await pwdFormRef.value.validate(async (valid) => {
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
</style>
