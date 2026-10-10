<!--
  ECharts 图表封装组件
  支持自适应容器大小、窗口缩放重绘
  示例：<EChart :option="chartOption" height="400px" />
-->
<template>
  <div ref="chartRef" :style="{ width: '100%', height: height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = withDefaults(
  defineProps<{
    option: echarts.EChartsOption
    height?: string
    theme?: string
    clickable?: boolean
  }>(),
  {
    height: '350px',
    clickable: false,
  }
)

const emit = defineEmits<{
  click: [params: any]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, props.theme)
  chart.setOption(props.option)
  if (props.clickable) {
    chart.on('click', (params: any) => {
      emit('click', params)
    })
  }
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  nextTick(() => {
    initChart()
    window.addEventListener('resize', resize)
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})

watch(
  () => props.option,
  (newOption) => {
    chart?.setOption(newOption, true)
  },
  { deep: true }
)

watch(
  () => props.clickable,
  (clickable) => {
    if (!chart) return
    chart.off('click')
    if (clickable) {
      chart.on('click', (params: any) => {
        emit('click', params)
      })
    }
  }
)

defineExpose({ resize })
</script>
