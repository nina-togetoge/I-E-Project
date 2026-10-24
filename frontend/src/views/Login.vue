<!--
  ==== 登录页 ====
  解决的问题：为四类角色（1学生 / 2教师 / 3专家 / 4管理员，超管=role4 且无 college_id，
    学院管理员=role4 且有 college_id）提供统一入口，登录后由路由守卫按角色下发菜单。
  对应角色与路由：公开路由 /login；已登录用户访问时通常会被守卫重定向到首页。
  依赖 API：userStore.login(username, password) 内部调用后端登录接口，
    成功后把 access_token 写入 sessionStorage 并加载用户信息。
  关键交互流程：
    - 账号密码 + 前端图形验证码校验 -> 提交登录 -> 按 query.redirect 或首页跳转；
    - 「记住账号」只缓存用户名，密码永不落盘（旧版本可逆密码缓存会被主动清理）；
    - 背景四张图每 3 秒轮播，离开页面时清除定时器，避免内存泄漏。
  说明：quickFill 为演示用的账号快捷填充能力，当前模板未挂载角色切换/快捷登录按钮，
    仅在调试或后续演示入口启用时使用。
-->
<template>
  <!-- 区块：页面整体布局，背景幻灯片铺满底层，登录卡片以更高层级浮在上方 -->
  <div class="login-container">
    <!-- 区块：背景幻灯片，四张校园图淡入淡出轮播，叠加遮罩保证表单可读性 -->
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

    <!-- 区块：登录卡片，包含标题、账号密码、验证码、记住账号与提交按钮 -->
    <div class="login-box">
      <!-- 区块：平台名称与英文副标题，仅作品牌展示，不参与校验 -->
      <div class="login-header">
        <h1 class="login-title">校园创新创业项目管理平台</h1>
        <p class="login-subtitle">Campus Innovation &amp; Entrepreneurship Project Management</p>
      </div>

      <!-- 区块：登录表单，统一由 el-form 管理校验；keyup.enter 让用户输完验证码直接回车登录 -->
      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        class="login-form"
        @keyup.enter="handleLogin"
      >
        <!-- 用户名：支持用户名/学号/手机号/邮箱，最长 64 位 -->
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
            maxlength="64"
          />
        </el-form-item>

        <!-- 密码：限制 6 位（与后端历史密码规则一致），可切换明文查看 -->
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

        <!-- 验证码：前端生成、前端比对，仅用于防误触与简单机器人提交，点击可刷新 -->
        <el-form-item prop="captcha">
          <!-- 验证码行：左侧输入框、右侧展示可点击刷新的图形码，两者并排 -->
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

        <!-- 记住账号：仅保存用户名，登录成功后写入或清除 localStorage -->
        <el-form-item>
          <el-checkbox v-model="rememberPassword" class="remember-check">记住账号</el-checkbox>
        </el-form-item>

        <!-- 提交：按钮 loading 防止重复点击；表单支持回车提交 -->
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
// ==================== 导入 ====================
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Key } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import bg1 from '@/assets/login-bg/bg1.jpg'
import bg2 from '@/assets/login-bg/bg2.jpg'
import bg3 from '@/assets/login-bg/bg3.jpg'
import bg4 from '@/assets/login-bg/bg4.jpg'

// ==================== 背景轮播 ====================
/** 背景图列表，按顺序循环播放 */
const backgrounds = [bg1, bg2, bg3, bg4]
/** 当前展示的幻灯片下标，与 .active 样式绑定实现淡入淡出 */
const currentSlide = ref(0)
/** 轮播定时器句柄，onUnmounted 时清理；用 let 保存以便解除引用 */
let slideTimer: ReturnType<typeof setInterval> | null = null

// ==================== 路由与登录状态 ====================
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

/** 登录表单实例，用于提交前统一校验 */
const loginFormRef = ref<FormInstance>()
/** 登录请求进行中标记，驱动按钮 loading */
const loading = ref(false)
/** 是否记住账号；只影响用户名的本地缓存，不涉及密码 */
const rememberPassword = ref(false)
/** 当前前端生成的 4 位验证码文本，点击验证码区域时刷新 */
const captchaText = ref('')

/** 登录表单模型：用户名 + 密码 + 验证码 */
const loginForm = reactive({
  username: '',
  password: '',
  captcha: '',
})

// ==================== 校验规则 ====================
/** 三项均只校验非空；账号形式多样、密码历史格式不一，故不做格式限制 */
const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名/学号/手机号/邮箱', trigger: 'blur' }],
  // 登录不强制密码格式（历史用户密码可能为字母数字组合，如 admin123），仅校验非空
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}

// ==================== 验证码 ====================
/**
 * 生成 4 位验证码。
 * 字符集剔除了 0/O/1/I 等易混淆字符，减少用户输入歧义。
 * 副作用：写入 captchaText。
 */
function generateCaptcha() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  let result = ''
  for (let i = 0; i < 4; i++) {
    result += chars[Math.floor(Math.random() * chars.length)]
  }
  captchaText.value = result
}

/**
 * 点击验证码区域刷新，或登录失败后自动刷新，避免复用旧码。
 */
function refreshCaptcha() {
  generateCaptcha()
}

// ==================== 演示用快捷填充 ====================
/**
 * 快捷填充账号密码，便于演示不同角色登录。
 * 当前模板未提供入口，保留供调试或后续角色切换面板调用。
 * @param username 账号
 * @param password 密码
 */
function quickFill(username: string, password: string) {
  loginForm.username = username
  loginForm.password = password
}

// ==================== 登录流程 ====================
/**
 * 执行登录。
 * 流程：表单校验 -> 前端比对验证码（忽略大小写）-> userStore.login ->
 *   按「记住账号」写入/清除用户名缓存 -> 跳转 query.redirect 或首页。
 * 副作用：发起登录请求、写提示、写 localStorage、路由跳转；
 *   失败时刷新验证码并清空输入，但不主动提示后端错误（由请求拦截器统一提示）。
 */
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

      // 只记住账号，不落盘密码（btoa 可逆，等同明文，存在被窃取风险）
      if (rememberPassword.value) {
        localStorage.setItem('saved_username', loginForm.username)
      } else {
        localStorage.removeItem('saved_username')
      }
      localStorage.removeItem('saved_password')

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

// ==================== 生命周期 ====================
/**
 * 挂载时：生成首个验证码、回填上次记住的账号、清理旧版密码缓存、启动背景轮播。
 */
onMounted(() => {
  generateCaptcha()
  const savedUsername = localStorage.getItem('saved_username')
  if (savedUsername) {
    loginForm.username = savedUsername
    rememberPassword.value = true
  }
  // 清理旧版本遗留的可逆密码缓存
  localStorage.removeItem('saved_password')
  // 启动背景幻灯片，每 3 秒切换一次
  slideTimer = setInterval(() => {
    currentSlide.value = (currentSlide.value + 1) % backgrounds.length
  }, 3000)
})

/**
 * 卸载时清除轮播定时器并置空句柄，防止组件销毁后仍触发状态更新。
 */
onUnmounted(() => {
  if (slideTimer) {
    clearInterval(slideTimer)
    slideTimer = null
  }
})
</script>

<style scoped>
/* 全屏容器：居中登录卡片，overflow:hidden 防止轮播图切换时出现滚动条 */
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

/* 单张背景图：绝对定位铺满，opacity 过渡实现 1.5 秒淡入淡出 */
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

/* 浅色遮罩：降低背景图对比度，保证表单文字可读；深色主题下改为深色遮罩 */
.slideshow-overlay {
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.25);
}

:deep(html.dark) .slideshow-overlay {
  background: rgba(0, 0, 0, 0.45);
}

/* 登录卡片：半透明背景 + backdrop-filter 毛玻璃，避免背景图干扰输入 */
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

/* 验证码行布局：输入框自适应剩余宽度，图形码固定 120px 放在右侧 */
.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
}

/* 图形验证码外观：斜体、删除线与加大字距模拟验证码图片，cursor:pointer 提示可点击刷新 */
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

/* 主按钮全宽，与输入框对齐，强化单一主操作 */
.login-btn {
  width: 100%;
}

/* 旧版演示账号区域样式，当前模板未挂载对应结构，保留以兼容后续快捷登录入口 */
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
