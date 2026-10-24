<!--
  ==== CountNumber ====
  职责：数字滚动动画组件。挂载或 value 变化时，从 0 平滑过渡到目标值，
        并做千分位与固定小数位格式化；传入字符串时原样展示、不做动画。
  复用：数据看板 / 统计卡片中的项目数、经费总额、专家人数、评分等指标。
  契约：props：value（number | string，必填）、duration（动画时长 ms，默认 1500）、
              decimals（小数位，默认 0）；无 emit、无插槽。
  注意：1) 字符串值用于"暂无""待统计"等非数值占位，直接输出不参与动画；
        2) 动画取消句柄在卸载与重新触发前都会调用，避免遗留 rAF 回调；
        3) 千分位使用浏览器当前 locale 格式化，符号随系统语言变化。
-->
<template>
  <!-- 区块：仅输出格式化后的文本节点，不附加任何样式，便于父级控制排版 -->
  <span>{{ displayValue }}</span>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import { animateNumber } from '@/utils/countup'

// ==================== props ====================
/** 动画入参：目标值、时长与小数位。 */
const props = withDefaults(
  defineProps<{
    /** 目标值；number 触发滚动动画，string 原样展示（如"暂无数据"） */
    value: number | string
    /** 动画时长（毫秒），默认 1500；0 表示立即到达目标值 */
    duration?: number
    /** 保留小数位数，默认 0；金额类展示通常传 2 */
    decimals?: number
  }>(),
  {
    duration: 1500,
    decimals: 0,
  }
)

// ==================== 状态 ====================
/** 当前动画中间值，保留以便调试或后续扩展（模板实际使用 displayValue） */
const current = ref(0)
/** 当前动画的取消函数；重新触发动画或卸载时调用，防止 rAF 回调泄漏 */
let cancelFn: (() => void) | null = null

/** 最终展示文本，已做 locale 千分位与小数位格式化 */
const displayValue = ref<string>('')

// ==================== 方法 ====================
/**
 * 启动数字滚动动画。
 * 副作用：取消上一轮动画、更新 current / displayValue、注册新的 rAF 动画。
 * 规则：字符串值直接写入展示文本并返回；数字值从 0 缓动到目标值，每帧格式化一次。
 */
function startAnimation() {
  if (typeof props.value === 'string') {
    displayValue.value = props.value
    return
  }
  if (typeof props.value === 'number') {
    if (cancelFn) {
      cancelFn()
      cancelFn = null
    }
    cancelFn = animateNumber(props.value, props.duration, (v) => {
      current.value = v
      displayValue.value = v.toLocaleString(undefined, {
        minimumFractionDigits: props.decimals,
        maximumFractionDigits: props.decimals,
      })
    })
  }
}

// ==================== 生命周期 ====================
/** 首次挂载即开始动画，统计卡片进入视口时即可看到数字滚动效果 */
onMounted(() => {
  startAnimation()
})

/** 目标值变化时重新播放动画；重新触发前 startAnimation 内部会先取消旧动画 */
watch(
  () => props.value,
  () => {
    startAnimation()
  }
)

/** 卸载时取消动画，避免 rAF 回调继续写入已销毁组件的状态 */
onBeforeUnmount(() => {
  if (cancelFn) {
    cancelFn()
    cancelFn = null
  }
})
</script>
