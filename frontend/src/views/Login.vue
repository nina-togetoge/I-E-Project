<!--
  登录页
  支持账号密码登录、记住密码、验证码
-->
<template>
  <div class="login-container">
    <!-- 背景幻灯片 -->
    <div class="slideshow">
      <div
        v-for="(img, idx) in backgrounds"
        :key="idx"
        class="slide"
        :class="{ active: currentSlide === idx }"
        :style="{ backgroundImage: `url(${img})` }"
      />
      <div class="slideshow-overlay" />
    </div>

    <div class="login-box">
      <div class="login-header">
        <h1 class="login-title">校园创新创业项目管理平台</h1>
        <p class="login-subtitle">Campus Innovation &amp; Entrepreneurship Project Management</p>
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
            maxlength="64"
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
            maxlength="6"
          />
        </el-form-item>

        <el-form-item prop="captcha">
          <div class="captcha-row">
            <el-input
              v-model="loginForm.captcha"
              placeholder="请输入验证码"
              size="large"
              :prefix-icon="Key"
              maxlength="4"
            />
            <div class="captcha-box" @click="refreshCaptcha">
              {{ captchaText }}
            </div>
          </div>
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="rememberPassword" class="remember-check">记住密码</el-checkbox>
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

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Key } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import bg1 from '@/assets/login-bg/bg1.jpg'
import bg2 from '@/assets/login-bg/bg2.jpg'
import bg3 from '@/assets/login-bg/bg3.jpg'
import bg4 from '@/assets/login-bg/bg4.jpg'

const backgrounds = [bg1, bg2, bg3, bg4]
const currentSlide = ref(0)
let slideTimer: ReturnType<typeof setInterval> | null = null

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
  username: [{ required: true, message: '请输入用户名/学号/手机号/邮箱', trigger: 'blur' }],
  // 登录不强制密码格式（历史用户密码可能为字母数字组合，如 admin123），仅校验非空
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}

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
  const savedUsername = localStorage.getItem('saved_username')
  const savedPassword = localStorage.getItem('saved_password')
  if (savedUsername && savedPassword) {
    loginForm.username = savedUsername
    loginForm.password = atob(savedPassword)
    rememberPassword.value = true
  }
  // 启动背景幻灯片，每 3 秒切换一次
  slideTimer = setInterval(() => {
    currentSlide.value = (currentSlide.value + 1) % backgrounds.length
  }, 3000)
})

onUnmounted(() => {
  if (slideTimer) {
    clearInterval(slideTimer)
    slideTimer = null
  }
})
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

/* 背景幻灯片 */
.slideshow {
  position: absolute;
  inset: 0;
  z-index: 0;
}

.slide {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  opacity: 0;
  transition: opacity 1.5s ease-in-out;
}

.slide.active {
  opacity: 1;
}

.slideshow-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.25);
}

:deep(html.dark) .slideshow-overlay {
  background: rgba(0, 0, 0, 0.45);
}

.login-box {
  width: 420px;
  padding: 40px 44px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(235, 239, 245, 0.8);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  position: relative;
  z-index: 1;
  backdrop-filter: blur(10px);
}

:deep(html.dark) .login-box {
  background: #1f1f1f;
  border-color: #2b2b2b;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.4);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-title {
  font-size: 22px;
  color: #303133;
  margin-bottom: 8px;
  font-weight: 600;
}

:deep(html.dark) .login-title {
  color: #e5eaf3;
}

.login-subtitle {
  font-size: 12px;
  color: #909399;
  letter-spacing: 0.5px;
}

:deep(html.dark) .login-subtitle {
  color: #a3a6ad;
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
  background: #f2f6fc;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: bold;
  letter-spacing: 4px;
  color: #409eff;
  cursor: pointer;
  user-select: none;
  font-style: italic;
  text-decoration: line-through;
}

:deep(html.dark) .captcha-box {
  background: #2b2b2b;
  border-color: #3a3a3a;
  color: #79bbff;
}

.login-btn {
  width: 100%;
}

.login-footer {
  margin-top: 22px;
  text-align: center;
}

.login-footer p {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

:deep(html.dark) .login-footer p {
  color: #a3a6ad;
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

:deep(.remember-check .el-checkbox__label) {
  color: #606266;
}

:deep(html.dark .remember-check .el-checkbox__label) {
  color: #cfd3dc;
}
</style>
