<!--
  ==== EChart ====
  职责：ECharts 实例封装。负责初始化、option 更新、窗口缩放重绘、点击事件透传，
        以及组件卸载时销毁实例，避免内存泄漏。
  复用：数据看板中的项目趋势、经费分布、评审统计、成果分类等所有图表位。
        示例：<EChart :option="chartOption" height="400px" />
  契约：props：option（EChartsOption，必填）、height（默认 350px）、
              theme（可选主题名）、clickable（是否监听点击，默认 false）；
        emits：click(params)（仅在 clickable=true 时触发，载荷为 ECharts 点击参数）；
        暴露：resize()（容器尺寸变化但未触发 window resize 时手动调用）。
  注意：1) 容器宽度固定 100%，父级必须有确定宽度，否则图表宽度为 0；
        2) option 深度监听，变化时以 notMerge=true 全量替换，避免旧系列残留；
        3) 切换 clickable 时会先解绑再按需绑定，防止重复触发。
-->
<template>
  <!-- 区块：图表容器，ECharts 实例挂载在此；宽 100% 撑满父级，高度由 height 控制 -->
  <div ref="chartRef" :style="{ width: '100%', height: height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

// ==================== props / emits ====================
/** 图表配置。option 会被深度监听，新增/修改配置后组件自动重绘。 */
const props = withDefaults(
  defineProps<{
    /** ECharts 配置项，必填；变化时全量替换（notMerge） */
    option: echarts.EChartsOption
    /** 图表高度，默认 350px，需带单位（如 400px / 50vh） */
    height?: string
    /** 可选主题名；未传则使用 ECharts 默认主题 */
    theme?: string
    /** 是否监听图表点击，默认 false；仅需要下钻/跳转时才开启 */
    clickable?: boolean
  }>(),
  {
    height: '350px',
    clickable: false,
  }
)

/**
 * 图表点击事件：仅在 clickable=true 时触发。
 * 载荷为 ECharts 原始点击参数（含 seriesName、name、value、data 等），父组件据此做筛选或跳转。
 */
const emit = defineEmits<{
  click: [params: any]
}>()

// ==================== 实例状态 ====================
/** 图表容器 DOM 引用，echarts.init 的挂载点 */
const chartRef = ref<HTMLDivElement>()
/** ECharts 实例；未初始化或已销毁时为 null，所有操作前需判空 */
let chart: echarts.ECharts | null = null

// ==================== 方法 ====================
/**
 * 初始化 ECharts 实例并应用初始配置。
 * 副作用：创建实例、设置 option、按需绑定 click 事件。
 * 说明：容器必须有非零宽高，否则 ECharts 会以 0 尺寸初始化，因此调用方先 nextTick。
 */
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

/**
 * 手动重绘：容器尺寸变化但未触发 window resize 时调用（如侧栏折叠、弹窗展开）。
 * 副作用：调用 ECharts 的 resize 重新计算布局。
 */
function resize() {
  chart?.resize()
}

// ==================== 生命周期 ====================
/** 挂载后等 DOM 布局完成再初始化，并注册窗口 resize 监听 */
onMounted(() => {
  nextTick(() => {
    initChart()
    window.addEventListener('resize', resize)
  })
})

/**
 * 卸载时清理：注销 resize 监听并销毁 ECharts 实例。
 * 销毁是避免内存泄漏的关键——实例内部持有 DOM、事件与计时器，
 * 仅把 chart 置 null 而不 dispose 不会释放这些资源。
 */
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})

/**
 * 配置变化时重绘。
 * 使用 notMerge=true 全量替换配置，避免上一次的 series / 数据残留造成叠加显示；
 * 深度监听保证嵌套属性改动也能被捕获。
 */
watch(
  () => props.option,
  (newOption) => {
    chart?.setOption(newOption, true)
  },
  { deep: true }
)

/**
 * clickable 变化时重新绑定点击监听。
 * 副作用：先 off('click') 清空旧监听，再按新值决定是否绑定，防止事件重复触发。
 */
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

/** 暴露 resize 方法，供父组件在容器尺寸变化时主动触发重绘 */
defineExpose({ resize })
</script>
