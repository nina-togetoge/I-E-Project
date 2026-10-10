<!--
  通用分页表格组件
  支持分页、排序、多选、操作按钮列
  示例：<PaginationTable :data="tableData" :columns="columns" :total="total" @page-change="handlePageChange" />
-->
<template>
  <div class="pagination-table" :class="{ 'table-mobile': isMobile }">
    <el-alert
      v-if="virtualize && data.length > 200"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px;"
    >
      数据量大，已启用虚拟滚动优化模式（自动分页）
    </el-alert>

    <el-table
      :data="data"
      v-loading="loading"
      :row-class-name="tableRowClassName"
      @selection-change="$emit('selection-change', $event)"
      @sort-change="handleSortChange"
      style="width: 100%; --el-table-row-hover-bg-color: transparent;"
      :header-cell-style="{ background: 'var(--table-header-bg, #f5f7fa)' }"
    >
      <el-table-column v-if="selection" type="selection" width="50" />
      <el-table-column v-if="index" type="index" label="序号" width="70" />

      <template v-for="col in columns" :key="col.prop">
        <el-table-column
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
          :sortable="col.sortable"
          :fixed="col.fixed"
          :align="col.align || 'center'"
          :show-overflow-tooltip="col.showOverflowTooltip ?? false"
        >
          <template #default="{ row }">
            <slot v-if="col.slot" :name="col.slot" :row="row" />
            <el-tag v-else-if="col.tagType" :type="getTagType(col, row)">
              {{ col.formatter ? col.formatter(row[col.prop], row) : row[col.prop] }}
            </el-tag>
            <span v-else-if="col.formatter">{{ col.formatter(row[col.prop], row) }}</span>
            <span v-else>{{ row[col.prop] ?? '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column
        v-if="$slots.actions"
        label="操作"
        :width="actionWidth"
        align="center"
      >
        <template #default="{ row }">
          <slot name="actions" :row="row" />
        </template>
      </el-table-column>

      <template #empty>
        <EmptyIllustration type="default" description="暂无数据" />
      </template>
    </el-table>

    <div class="pagination-wrapper" v-if="total > 0">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="pageSizes"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import EmptyIllustration from '@/components/EmptyIllustration.vue'

const isMobile = ref(false)
let resizeTimer: number | null = null
function checkMobile() {
  isMobile.value = window.innerWidth < 768
}
function onResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(checkMobile, 100)
}
onMounted(() => {
  checkMobile()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (resizeTimer) clearTimeout(resizeTimer)
})

export interface TableColumn {
  prop: string
  label: string
  width?: number | string
  minWidth?: number | string
  sortable?: boolean | 'custom'
  fixed?: 'left' | 'right' | boolean
  align?: 'left' | 'center' | 'right'
  slot?: string
  tagType?: 'status' | string
  formatter?: (value: any, row: any) => string
}

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
    virtualize?: boolean
  }>(),
  {
    loading: false,
    selection: false,
    index: true,
    actionWidth: 180,
    pageSizes: () => [10, 20, 50, 100, 200, 500],
    defaultPageSize: 10,
    virtualize: true,
  }
)

const emit = defineEmits<{
  'page-change': [page: number, pageSize: number]
  'size-change': [pageSize: number]
  'selection-change': [selection: any[]]
  'sort-change': [{ prop: string; order: string | null }]
}>()

const currentPage = ref(1)
const pageSize = ref(props.defaultPageSize)

function tableRowClassName({ row, rowIndex }: { row: any; rowIndex: number }) {
  return 'pagination-table-row'
}

function getTagType(col: TableColumn, row: any) {
  if (typeof col.tagType === 'string' && col.tagType === 'status') {
    const statusTagMap: Record<number, string> = {
      0: 'info',
      1: 'success',
      10: 'warning',
      20: 'warning',
      30: 'warning',
      40: 'warning',
      50: 'success',
      60: 'danger',
      70: '',
      80: 'warning',
      90: 'success',
    }
    return statusTagMap[row[col.prop]] || 'info'
  }
  return 'info'
}

function handlePageChange(page: number) {
  currentPage.value = page
  emit('page-change', page, pageSize.value)
}

function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  emit('size-change', size)
  emit('page-change', 1, size)
}

function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
  emit('sort-change', { prop, order })
}
</script>

<style scoped>
.pagination-table {
  width: 100%;
}

/* 确保表格可以横向滚动（仅表体滚动，表头不显示独立滚动条） */
:deep(.el-table__body-wrapper) {
  flex: none !important;
  width: 100% !important;
  overflow-x: auto !important;
}

:deep(.el-table__header-wrapper) {
  flex: none !important;
  width: 100% !important;
  overflow-x: hidden !important;
}

:deep(.el-table__body),
:deep(.el-table__header) {
  width: max-content !important;
  min-width: 100%;
}

/* 确保横向滚动条可见 */
:deep(.el-scrollbar__bar.is-horizontal) {
  display: block !important;
  height: 6px !important;
}

:deep(.el-scrollbar__bar.is-horizontal .el-scrollbar__thumb) {
  background-color: rgba(144, 147, 153, 0.3) !important;
}

:deep(.el-scrollbar__wrap) {
  overflow-x: auto !important;
}

:deep(.el-table th) {
  position: sticky;
  top: 0;
  z-index: 10;
}

/* 完全禁用行悬停变色 */
:deep(.el-table__body tr.hover-row > td.el-table__cell),
:deep(.el-table__body tr:hover > td.el-table__cell),
:deep(.el-table--enable-row-hover .el-table__body tr:hover > td.el-table__cell),
:deep(.el-table__body tr.current-row > td.el-table__cell) {
  background-color: transparent !important;
}

/* 禁用单元格内容溢出时的悬停提示（show-overflow-tooltip 产生的 popper） */
:deep(.el-tooltip__popper) {
  display: none !important;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (max-width: 768px) {
  .table-mobile {
    overflow-x: auto;
  }
  .table-mobile :deep(.el-table) {
    min-width: 600px;
  }
}
</style>
