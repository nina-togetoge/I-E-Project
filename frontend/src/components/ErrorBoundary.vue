<template>
  <div class="error-boundary">
    <slot v-if="!error" />
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
        <p class="error-message">{{ errorMessage }}</p>
        <div class="error-actions">
          <el-button type="primary" @click="handleRefresh">
            <el-icon><Refresh /></el-icon>
            刷新重试
          </el-button>
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

const error = ref<Error | null>(null)
const errorMessage = ref('页面出现异常，请稍后重试')

/**
 * 判断是否为"可忽略"的业务/请求错误（不该让整个页面降级崩溃）
 * 只对真正的代码级错误（TypeError / ReferenceError / SyntaxError / RangeError）
 * 或完全未知错误才触发降级
 */
function shouldDegrade(err: Error): boolean {
  const msg = (err.message || '').toLowerCase()
  // 1) 明确命中的请求类/业务类错误 -> 不降级
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

function reportError(err: Error, info: any) {
  try {
    console.error('[ErrorBoundary] 捕获到组件错误:', err)
    console.error('[ErrorBoundary] 错误详情:', info)
  } catch (e) {
    console.error('ErrorBoundary report failed:', e)
  }
}

onErrorCaptured((err: Error, instance, info) => {
  reportError(err, { componentInstance: instance, lifecycleHook: info })
  if (shouldDegrade(err)) {
    error.value = err
    errorMessage.value = err.message || '页面出现异常，请稍后重试'
    ElMessage.error('页面出现异常，已切换到安全模式')
    return false
  }
  // 业务错误/请求错误仅警告，不阻断页面
  ElMessage.warning(err.message || '请求出现小问题，稍后再试')
  return false
})

function handleRefresh() {
  window.location.reload()
}

function handleReset() {
  error.value = null
  errorMessage.value = '页面出现异常，请稍后重试'
}
</script>

<style scoped>
.error-boundary {
  width: 100%;
  min-height: inherit;
}

.error-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 40px 20px;
}

.error-icon {
  opacity: 0.9;
}

.error-message {
  color: #909399;
  font-size: 14px;
  margin: 12px 0 24px;
  max-width: 400px;
  word-break: break-all;
  line-height: 1.6;
}

.error-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
