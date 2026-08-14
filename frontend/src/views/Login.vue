<!--
  登录页
  支持账号密码登录、记住密码、验证码
-->
<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <h1 class="login-title">校园创新创业项目管理平台</h1>
        <p class="login-subtitle">Campus Innovation & Entrepreneurship Project Management</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <el-form-item prop="captcha">
          <div class="captcha-row">
            <el-input
              v-model="loginForm.captcha"
              placeholder="请输入验证码"
              size="large"
              :prefix-icon="Key"
            />
            <div class="captcha-box" @click="refreshCaptcha">
              {{ captchaText }}
            </div>
          </div>
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="rememberPassword">记住密码</el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <p>测试账号：</p>
        <div class="test-accounts">
          <el-tag size="small" @click="quickFill('admin', 'admin123')">管理员 admin</el-tag>
          <el-tag size="small" type="success" @click="quickFill('student001', 'admin123')">学生 student001</el-tag>
          <el-tag size="small" type="warning" @click="quickFill('teacher001', 'admin123')">教师 teacher001</el-tag>
          <el-tag size="small" type="danger" @click="quickFill('expert001', 'admin123')">专家 expert001</el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Key } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const loginFormRef = ref<FormInstance>()
const loading = ref(false)
const rememberPassword = ref(false)
const captchaText = ref('')

const loginForm = reactive({
  username: '',
  password: '',
  captcha: '',
})

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  captcha: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}

/** 生成随机验证码 */
function generateCaptcha() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  let result = ''
  for (let i = 0; i < 4; i++) {
    result += chars[Math.floor(Math.random() * chars.length)]
  }
  captchaText.value = result
}

function refreshCaptcha() {
  generateCaptcha()
}

function quickFill(username: string, password: string) {
  loginForm.username = username
  loginForm.password = password
}

async function handleLogin() {
  if (!loginFormRef.value) return
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return

    // 验证码校验
    if (loginForm.captcha.toUpperCase() !== captchaText.value.toUpperCase()) {
      ElMessage.error('验证码不正确')
      refreshCaptcha()
      loginForm.captcha = ''
      return
    }

    loading.value = true
    try {
      await userStore.login(loginForm.username, loginForm.password)

      if (rememberPassword.value) {
        localStorage.setItem('saved_username', loginForm.username)
        localStorage.setItem('saved_password', btoa(loginForm.password))
      } else {
        localStorage.removeItem('saved_username')
        localStorage.removeItem('saved_password')
      }

      ElMessage.success('登录成功')
      const redirect = (route.query.redirect as string) || '/'
      router.push(redirect)
    } catch (error: any) {
      refreshCaptcha()
    } finally {
      loading.value = false
    }
  })
}

onMounted(() => {
  generateCaptcha()
  // 恢复记住的密码
  const savedUsername = localStorage.getItem('saved_username')
  const savedPassword = localStorage.getItem('saved_password')
  if (savedUsername && savedPassword) {
    loginForm.username = savedUsername
    loginForm.password = atob(savedPassword)
    rememberPassword.value = true
  }
})
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-box {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.12);
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-title {
  font-size: 22px;
  color: #303133;
  margin-bottom: 8px;
}

.login-subtitle {
  font-size: 12px;
  color: #909399;
}

.login-form {
  margin-top: 20px;
}

.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
}

.captcha-box {
  width: 120px;
  height: 40px;
  background: linear-gradient(45deg, #e0e0e0, #f5f5f5);
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: bold;
  letter-spacing: 4px;
  color: #303133;
  cursor: pointer;
  user-select: none;
  font-style: italic;
  text-decoration: line-through;
}

.login-btn {
  width: 100%;
}

.login-footer {
  margin-top: 20px;
  text-align: center;
}

.login-footer p {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.test-accounts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}

.test-accounts .el-tag {
  cursor: pointer;
}
</style>
