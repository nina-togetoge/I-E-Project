<template>
  <span>{{ displayValue }}</span>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import { animateNumber } from '@/utils/countup'

const props = withDefaults(
  defineProps<{
    value: number | string
    duration?: number
    decimals?: number
  }>(),
  {
    duration: 1500,
    decimals: 0,
  }
)

const current = ref(0)
let cancelFn: (() => void) | null = null

const displayValue = ref<string>('')

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

onMounted(() => {
  startAnimation()
})

watch(
  () => props.value,
  () => {
    startAnimation()
  }
)

onBeforeUnmount(() => {
  if (cancelFn) {
    cancelFn()
    cancelFn = null
  }
})
</script>
