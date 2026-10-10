<!--
  虚拟滚动增强表格组件（扩展 PaginationTable）
  大数据量（>200条）时自动启用优化提示、增大分页选项
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
    <template v-for="(slot, name) in $slots" :key="name" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps || {}" />
    </template>
  </PaginationTable>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import PaginationTable from './PaginationTable.vue'
import type { TableColumn } from './PaginationTable.vue'

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

defineEmits<{
  'page-change': [page: number, pageSize: number]
  'size-change': [pageSize: number]
  'selection-change': [selection: any[]]
  'sort-change': [{ prop: string; order: string | null }]
}>()

const isLargeDataset = computed(() => props.total > 200 || props.data.length > 200)

const mergedPageSizes = computed(() => {
  if (props.pageSizes && props.pageSizes.length > 0) {
    return props.pageSizes
  }
  return isLargeDataset.value
    ? [10, 20, 50, 100, 200, 500]
    : [10, 20, 50, 100]
})

const mergedDefaultPageSize = computed(() => {
  if (props.defaultPageSize) return props.defaultPageSize
  return isLargeDataset.value ? 50 : 10
})
</script>
