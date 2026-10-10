<template>
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
  <div class="password-strength" v-else>
    <div class="strength-bars">
      <div v-for="i in 4" :key="i" class="strength-bar" style="background-color: #e4e7ed;" />
    </div>
    <span class="strength-label" style="color: #909399;">请输入密码</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  password: string
}>()

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

function getBarColor(index: number) {
  if (index < score.value) {
    const colors = ['#F56C6C', '#E6A23C', '#F7BA2A', '#67C23A', '#52C41A']
    return colors[score.value]
  }
  return '#e4e7ed'
}

function getTextColor() {
  const colors = ['#F56C6C', '#E6A23C', '#F7BA2A', '#67C23A', '#52C41A']
  return colors[score.value]
}

function getLabel() {
  const labels = ['极弱', '弱', '中', '强', '极强']
  return labels[score.value]
}
</script>

<style scoped>
.password-strength {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.strength-bars {
  display: flex;
  gap: 4px;
}

.strength-bar {
  width: 36px;
  height: 6px;
  border-radius: 3px;
  transition: background-color 0.3s ease;
}

.strength-label {
  font-size: 12px;
  font-weight: 500;
}
</style>
