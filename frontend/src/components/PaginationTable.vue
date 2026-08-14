<!--
  通用分页表格组件
  支持分页、排序、多选、操作按钮列
  示例：<PaginationTable :data="tableData" :columns="columns" :total="total" @page-change="handlePageChange" />
-->
<template>
  <div class="pagination-table">
    <!-- 表格 -->
    <el-table
      :data="data"
      v-loading="loading"
      @selection-change="$emit('selection-change', $event)"
      @sort-change="handleSortChange"
      style="width: 100%"
      :header-cell-style="{ background: '#f5f7fa' }"
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
        >
          <template #default="{ row }">
            <!-- 自定义渲染 -->
            <slot v-if="col.slot" :name="col.slot" :row="row" />
            <!-- Tag 标签 -->
            <el-tag v-else-if="col.tagType" :type="getTagType(col, row)">
              {{ col.formatter ? col.formatter(row[col.prop], row) : row[col.prop] }}
            </el-tag>
            <!-- 格式化函数 -->
            <span v-else-if="col.formatter">{{ col.formatter(row[col.prop], row) }}</span>
            <!-- 普通文本 -->
            <span v-else>{{ row[col.prop] ?? '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column
        v-if="$slots.actions"
        label="操作"
        :width="actionWidth"
        fixed="right"
        align="center"
      >
        <template #default="{ row }">
          <slot name="actions" :row="row" />
        </template>
      </el-table-column>

      <!-- 空状态 -->
      <template #empty>
        <el-empty description="暂无数据" />
      </template>
    </el-table>

    <!-- 分页 -->
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
import { ref, computed, watch } from 'vue'

/** 列定义 */
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
  }>(),
  {
    loading: false,
    selection: false,
    index: true,
    actionWidth: 180,
    pageSizes: () => [10, 20, 50, 100],
    defaultPageSize: 10,
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
.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
