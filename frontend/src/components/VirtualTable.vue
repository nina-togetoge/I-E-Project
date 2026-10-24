<!-- ==== VirtualTable 大数据量表格封装 ==== -->
<!--
  职责：在 PaginationTable 之上做的一层"虚拟滚动/大数据量"增强封装，
        以分页窗口作为实际渲染窗口，控制单次进入 DOM 的行数，缓解大数据量下的渲染卡顿。
  复用场景：项目列表、用户管理、日志、统计明细等可能超过 200 条记录的列表页。
  外部契约：props/emit 与 PaginationTable 保持一致（数据、列定义、总数、分页事件、排序、多选等），
            并把默认插槽与所有具名插槽原样透传，父组件无需感知内部封装。
  注意事项：
    1. 真正的"可视区计算"由本组件根据 total/data 长度决定分页容量完成，
       实际渲染行数 = 当前页数据量，页面滚动监听交给 el-table 自身，
       本组件不额外注册 scroll 监听，避免与表格内部滚动容器冲突。
    2. 数据量 > 200 时，PaginationTable 会展示"已启用虚拟滚动优化模式"提示，
       并放宽可选分页容量（最大 500），减少翻页次数。
    3. $attrs 透传用于兼容父组件直接传给内部表格的额外属性。
    4. 阈值 200 为经验值：低于该数量时普通分页已足够流畅，过高阈值会让单页 DOM 过重。
    5. 大数据量场景建议后端分页；本组件只优化单页渲染，不负责数据裁剪。
    6. 分页容量上限 500，避免单页渲染行数继续膨胀导致滚动与选择操作变慢。
-->
<template>
  <PaginationTable
    :data="data"
    :columns="columns"
    :total="total"
    :loading="loading"
    :selection="selection"
    :index="index"
    :action-width="actionWidth"
    :page-sizes="mergedPageSizes"
    :default-page-size="mergedDefaultPageSize"
    :virtualize="true"
    @page-change="(p, ps) => $emit('page-change', p, ps)"
    @size-change="(ps) => $emit('size-change', ps)"
    @selection-change="(rows) => $emit('selection-change', rows)"
    @sort-change="(s) => $emit('sort-change', s)"
    v-bind="$attrs"
  >
    <!-- 插槽透传：父组件声明的 default / actions / empty 等插槽原样转发给内部表格 -->
    <template v-for="(slot, name) in $slots" :key="name" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps || {}" />
    </template>
  </PaginationTable>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import PaginationTable from './PaginationTable.vue'
import type { TableColumn } from './PaginationTable.vue'

// ==================== 组件契约 ====================
// 与 PaginationTable 对齐的入参；未传时使用下方默认值，保证开箱即用。
// pageSizes / defaultPageSize 会在 computed 中按数据量二次合并。
const props = withDefaults(
  defineProps<{
    data: any[]
    columns: TableColumn[]
    total: number
    loading?: boolean
    selection?: boolean
    index?: boolean
    actionWidth?: number | string
    pageSizes?: number[]
    defaultPageSize?: number
  }>(),
  {
    loading: false,
    selection: false,
    index: true,
    actionWidth: 180,
    pageSizes: () => [10, 20, 50, 100, 200, 500],
    defaultPageSize: 10,
  }
)

// 事件签名与内部表格完全一致，父组件可直接监听分页、容量、多选与排序变化。
defineEmits<{
  'page-change': [page: number, pageSize: number]
  'size-change': [pageSize: number]
  'selection-change': [selection: any[]]
  'sort-change': [{ prop: string; order: string | null }]
}>()

// ==================== 大数据量判定 ====================
// 以"服务端总数"或"当前数据长度"任一超过 200 作为阈值；
// 该结果只影响分页容量与内部提示，不改变数据本身。
const isLargeDataset = computed(() => props.total > 200 || props.data.length > 200)

// 分页容量合并：父组件显式传入则尊重其配置；
// 否则大数据量放宽到 500，小数据量保持 100 上限。
const mergedPageSizes = computed(() => {
  if (props.pageSizes && props.pageSizes.length > 0) {
    return props.pageSizes
  }
  return isLargeDataset.value
    ? [10, 20, 50, 100, 200, 500]
    : [10, 20, 50, 100]
})

// 默认每页条数合并：显式传入优先；大数据量默认 50 条/页以减少翻页，
// 小数据量默认 10 条/页，兼顾首屏渲染量与阅读效率。
const mergedDefaultPageSize = computed(() => {
  if (props.defaultPageSize) return props.defaultPageSize
  return isLargeDataset.value ? 50 : 10
})
</script>
