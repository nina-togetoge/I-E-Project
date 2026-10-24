<!-- ==== PasswordStrength 密码强度提示 ==== -->
<!--
  职责：根据输入的密码文本实时计算强度分（0~4），以 4 段色条和文字标签反馈给用户。
  复用场景：登录/注册、个人中心修改密码、首次登录强制改密等需要输入新密码的表单。
  外部契约：唯一 prop 为 password（字符串，必填）；纯受控展示组件，不做校验、不 emit 事件。
  注意事项：强度仅作前端提示，真正的密码策略仍以服务端校验为准；空密码时展示中性占位态。
  分级可视化：4 段色条对应 4 个得分项，得分越高点亮段数越多；
              颜色从红→橙→黄→绿递进，文字与色条同色，降低理解成本。
  边界说明：得分 0 时仍渲染 4 段灰条并显示"极弱"；密码为空时显示"请输入密码"。
  使用方式：<PasswordStrength :password="form.newPassword" />
  响应式说明：score 为 computed，password 变化时色条与文字自动重算，无需手动刷新。
  性能说明：仅 4 个正则测试，输入过程开销可忽略，不需要额外防抖。
-->
<template>
  <!-- 有输入：按得分点亮色条，并用对应颜色渲染强度文案 -->
  <div class="password-strength" v-if="password">
    <div class="strength-bars">
      <div
        v-for="i in 4"
        :key="i"
        class="strength-bar"
        :style="{ backgroundColor: getBarColor(i - 1) }"
      />
    </div>
    <span class="strength-label" :style="{ color: getTextColor() }">
      {{ getLabel() }}
    </span>
  </div>
  <!-- 无输入：全部色条置灰，提示用户先输入密码 -->
  <div class="password-strength" v-else>
    <div class="strength-bars">
      <div v-for="i in 4" :key="i" class="strength-bar" style="background-color: #e4e7ed;" />
    </div>
    <span class="strength-label" style="color: #909399;">请输入密码</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// ==================== 组件契约 ====================
// password 由父组件通过 v-model 绑定的表单值传入，组件内部只读不改。
const props = defineProps<{
  password: string
}>()

// ==================== 强度计算 ====================
// 分级规则（每满足一项加 1 分，满分 4 分）：
//   1. 长度 >= 8
//   2. 同时包含小写与大写字母
//   3. 包含数字
//   4. 包含常见特殊字符（!@#$%^&*）
// 得分 0 极弱 / 1 弱 / 2 中 / 3 强 / 4 极强。
const score = computed(() => {
  let s = 0
  const pwd = props.password
  if (!pwd) return 0
  if (pwd.length >= 8) s++
  if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) s++
  if (/\d/.test(pwd)) s++
  if (/[!@#$%^&*]/.test(pwd)) s++
  return s
})

// ==================== 展示映射 ====================
// 色条索引从 0 开始；索引小于当前得分即点亮，使用与得分对应的颜色。
function getBarColor(index: number) {
  if (index < score.value) {
    const colors = ['#F56C6C', '#E6A23C', '#F7BA2A', '#67C23A', '#52C41A']
    return colors[score.value]
  }
  return '#e4e7ed'
}

// 文字颜色与当前得分颜色一致，保持色条与标签的视觉统一。
function getTextColor() {
  const colors = ['#F56C6C', '#E6A23C', '#F7BA2A', '#67C23A', '#52C41A']
  return colors[score.value]
}

// 文字标签：数组下标即得分，0 分对应"极弱"。
function getLabel() {
  const labels = ['极弱', '弱', '中', '强', '极强']
  return labels[score.value]
}
</script>

<style scoped>
/* 整体横向排列：4 段色条 + 强度文字 */
.password-strength {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

/* 色条容器：段间留 4px 间隔 */
.strength-bars {
  display: flex;
  gap: 4px;
}

/* 单段色条：固定 36x6，颜色变化带过渡动画 */
.strength-bar {
  width: 36px;
  height: 6px;
  border-radius: 3px;
  transition: background-color 0.3s ease;
}

/* 强度文字：小号加粗，颜色由内联样式按得分注入 */
.strength-label {
  font-size: 12px;
  font-weight: 500;
}
</style>
