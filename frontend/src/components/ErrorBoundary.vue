<!-- ==== ErrorBoundary 错误边界 ==== -->
<!--
  职责：包裹任意页面内容，捕获后代组件在渲染、生命周期钩子中抛出的运行时错误，
        避免整页白屏，并在出错时展示统一的降级界面（刷新重试 / 恢复默认）。
  复用场景：App.vue 根级包裹 router-view；也可在页面内局部包裹高风险区块。
  外部契约：默认插槽承载正常内容；不接收 props、不对外 emit。
  注意事项：只降级代码级运行时错误（TypeError 等）；请求/业务类错误仅提示、不降级，
           避免接口异常误伤整页。捕获后返回 false，阻止错误继续向上冒泡。
  降级判定优先级：
    1. 文案命中 softPatterns（重复请求、未登录、权限不足、超时等）→ 不降级；
    2. AxiosError 或带 4xx/5xx 状态的错误 → 不降级；
    3. 原生代码错误类（TypeError/ReferenceError/SyntaxError/RangeError/EvalError/URIError）→ 降级；
    4. 其他未知错误默认不降级，宁可提示也不整页替换。
  恢复策略：
    "刷新重试"整页 reload；"恢复默认"仅清空 error 状态，让插槽重新挂载。
-->
<template>
  <div class="error-boundary">
    <!-- 正常路径：未捕获到需要降级的错误时，原样渲染子内容 -->
    <slot v-if="!error" />
    <!-- 降级路径：展示错误说明与恢复操作 -->
    <div v-else class="error-fallback">
      <el-empty description="页面出现异常">
        <template #image>
          <div class="error-icon">
            <svg width="120" height="120" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="60" cy="60" r="54" fill="#fef0f0" stroke="#f56c6c" stroke-width="3" />
              <path d="M44 44L76 76M76 44L44 76" stroke="#f56c6c" stroke-width="4" stroke-linecap="round" />
            </svg>
          </div>
        </template>
        <!-- 错误摘要：优先展示原始 message，过长时由样式做换行处理 -->
        <p class="error-message">{{ errorMessage }}</p>
        <div class="error-actions">
          <!-- 刷新重试：整页重新加载，适合运行时状态已不可恢复的场景 -->
          <el-button type="primary" @click="handleRefresh">
            <el-icon><Refresh /></el-icon>
            刷新重试
          </el-button>
          <!-- 恢复默认：仅清空错误状态并重新渲染插槽，不刷新浏览器 -->
          <el-button @click="handleReset">恢复默认</el-button>
        </div>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

// ==================== 错误状态 ====================
// error 为 null 表示工作正常；一旦赋值即切换到降级 UI。
const error = ref<Error | null>(null)
// 展示用错误文案，默认值兜底 message 为空的异常对象。
const errorMessage = ref('页面出现异常，请稍后重试')

// ==================== 降级判定 ====================

/**
 * 判断是否为"可忽略"的业务/请求错误（不该让整个页面降级崩溃）
 * 只对真正的代码级错误（TypeError / ReferenceError / SyntaxError / RangeError）
 * 或完全未知错误才触发降级
 */
function shouldDegrade(err: Error): boolean {
  // 文案统一转小写后做包含匹配，避免大小写导致的漏判
  const msg = (err.message || '').toLowerCase()
  // 1) 明确命中的请求类/业务类错误 -> 不降级
  // 这些文案来自 axios 封装与业务层主动抛错，属于可预期的失败，不应替换整页。
  const softPatterns = [
    '重复请求被拦截',
    '未登录',
    '权限不足',
    '请求失败',
    '网络异常',
    '登录已过期',
    '请求超时',
    'timeout',
    'cancel',
  ]
  if (softPatterns.some((p) => msg.includes(p.toLowerCase()))) return false
  // 2) AxiosError / 4xx/5xx HTTP 错误 -> 不降级（接口问题不该让页面白屏）
  if ((err as any).isAxiosError) return false
  const status = (err as any).response?.status
  if (typeof status === 'number' && status >= 400) return false
  // 3) 代码级原生错误类 -> 降级
  if (
    err instanceof TypeError ||
    err instanceof ReferenceError ||
    err instanceof SyntaxError ||
    err instanceof RangeError ||
    err instanceof EvalError ||
    err instanceof URIError
  ) {
    return true
  }
  // 4) 其他错误默认不降级，避免误伤；只有明确的运行时崩溃才降级
  return false
}

/**
 * 统一错误上报入口
 * 目前仅输出到控制台，便于开发期定位；上报失败时做二次兜底，避免上报逻辑本身再次抛出错误。
 * @param err  捕获到的错误对象
 * @param info 组件实例、生命周期钩子等上下文信息
 */
function reportError(err: Error, info: any) {
  try {
    console.error('[ErrorBoundary] 捕获到组件错误:', err)
    console.error('[ErrorBoundary] 错误详情:', info)
  } catch (e) {
    console.error('ErrorBoundary report failed:', e)
  }
}

// ==================== 错误捕获 ====================
// 捕获后代组件错误：先上报，再按判定结果决定是否进入降级 UI。
// 无论哪种分支都返回 false，防止错误继续向上冒泡导致应用卸载。
onErrorCaptured((err: Error, instance, info) => {
  reportError(err, { componentInstance: instance, lifecycleHook: info })
  if (shouldDegrade(err)) {
    // 代码级错误：锁定错误对象并切换降级 UI，同时给出全局提示
    error.value = err
    errorMessage.value = err.message || '页面出现异常，请稍后重试'
    ElMessage.error('页面出现异常，已切换到安全模式')
    return false
  }
  // 业务错误/请求错误仅警告，不阻断页面
  ElMessage.warning(err.message || '请求出现小问题，稍后再试')
  return false
})

// ==================== 降级交互 ====================
/** 整页刷新：丢弃已损坏的运行时状态，重新走一遍应用初始化流程。 */
function handleRefresh() {
  window.location.reload()
}

/** 仅重置错误状态：让插槽内容重新挂载，适合偶发错误或用户希望继续操作时使用。 */
function handleReset() {
  error.value = null
  errorMessage.value = '页面出现异常，请稍后重试'
}
</script>

<style scoped>
/* 占满父容器，保证降级内容在布局中垂直居中 */
.error-boundary {
  width: 100%;
  min-height: inherit;
}

/* 降级容器：最小高度 60vh，避免内容过少时视觉上塌陷 */
.error-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 40px 20px;
}

/* 错误图标：轻微透明，避免大面积红色过于刺眼 */
.error-icon {
  opacity: 0.9;
}

/* 错误文案：限制最大宽度并允许长单词换行，防止异常堆栈撑破布局 */
.error-message {
  color: #909399;
  font-size: 14px;
  margin: 12px 0 24px;
  max-width: 400px;
  word-break: break-all;
  line-height: 1.6;
}

/* 操作按钮组：居中排列，窄屏自动换行 */
.error-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
