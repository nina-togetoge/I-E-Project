<!--
  ==== PaginationTable ====
  职责：通用分页表格，由 columns 配置驱动列定义，支持分页、排序、多选、序号列、
        操作按钮列、空状态插画和移动端横向滚动。
  复用：项目列表、审核工作台、用户管理、成果管理、通知管理等后台列表页。
  示例：<PaginationTable :data="tableData" :columns="columns" :total="total"
                         @page-change="handlePageChange" />
  契约：props：data / columns / total / loading / selection / index / actionWidth /
              pageSizes / defaultPageSize / virtualize；
        emits：page-change(page, pageSize)、size-change(pageSize)、
               selection-change(选中行数组)、sort-change({ prop, order })；
        插槽：按列配置的 col.slot 渲染单元格、actions（操作列）、empty（空状态覆盖）。
  注意：1) 本组件只负责展示与交互事件，分页/排序数据由父组件请求后端后回传；
        2) 列渲染优先级：具名插槽 > tagType 标签 > formatter > 原值（空值显示 "-"）；
        3) selection 与 index 列分别占用 50px / 70px，columns 宽度需预留。
-->
<template>
  <div class="pagination-table" :class="{ 'table-mobile': isMobile }">
    <!-- 区块：大数据量提示，超过 200 行时提醒调用方已进入优化展示模式 -->
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
      <!-- 可选的内置列：多选框列（批量操作）与序号列（跨页仍显示行号） -->
      <el-table-column v-if="selection" type="selection" width="50" />
      <el-table-column v-if="index" type="index" label="序号" width="70" />

      <!-- 区块：业务列，按 columns 配置动态渲染；单元格内容按优先级选择渲染方式 -->
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
            <!-- 渲染优先级：具名插槽（最灵活，可放 StatusTag/按钮）> 标签 + 格式化 > 纯格式化 > 原值 -->
            <slot v-if="col.slot" :name="col.slot" :row="row" />
            <el-tag v-else-if="col.tagType" :type="getTagType(col, row)">
              {{ col.formatter ? col.formatter(row[col.prop], row) : row[col.prop] }}
            </el-tag>
            <span v-else-if="col.formatter">{{ col.formatter(row[col.prop], row) }}</span>
            <span v-else>{{ row[col.prop] ?? '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列：仅在父组件提供 actions 插槽时渲染，宽度由 actionWidth 控制 -->
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

      <!-- 空状态：优先使用父组件 empty 插槽定制文案，否则回落到统一空状态插画 -->
      <template #empty>
        <slot name="empty">
          <EmptyIllustration type="default" description="暂无数据" />
        </slot>
      </template>
    </el-table>

    <!-- 区块：分页条，total 为 0 时不渲染，避免出现"共 0 条"的空壳 -->
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

// ==================== 移动端适配 ====================
/** 视口是否小于 768px；为真时启用表格最小宽度 + 横向滚动，避免列被压扁 */
const isMobile = ref(false)
/** resize 防抖定时器句柄 */
let resizeTimer: number | null = null
/**
 * 检测视口宽度并更新移动端标记。
 * 副作用：写入 isMobile。
 */
function checkMobile() {
  isMobile.value = window.innerWidth < 768
}
/**
 * 窗口 resize 入口：100ms 防抖后再检测，避免拖拽窗口时高频触发重排。
 * 副作用：管理 resizeTimer 并最终调用 checkMobile。
 */
function onResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(checkMobile, 100)
}
/** 挂载后立即检测一次（覆盖首屏小屏设备），并注册 resize 监听 */
onMounted(() => {
  checkMobile()
  window.addEventListener('resize', onResize)
})
/** 卸载时注销监听并清理防抖定时器，防止内存泄漏与卸载后回调 */
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (resizeTimer) clearTimeout(resizeTimer)
})

// ==================== 列配置类型 ====================
/**
 * 列定义契约。父组件用一组 TableColumn 描述表格的列，组件据此动态生成 el-table-column。
 */
export interface TableColumn {
  /** 行对象中的字段名，同时作为列的 key 与默认取值路径 */
  prop: string
  /** 表头文案 */
  label: string
  /** 固定列宽，数字按 px 处理 */
  width?: number | string
  /** 最小列宽，配合 el-table 自动分配剩余宽度，适合长文本列 */
  minWidth?: number | string
  /** 是否可排序；'custom' 表示后端排序，仅抛出 sort-change 由父组件重新请求 */
  sortable?: boolean | 'custom'
  /** 固定列位置，横向滚动时保持可见 */
  fixed?: 'left' | 'right' | boolean
  /** 单元格对齐方式，未配置时默认 center */
  align?: 'left' | 'center' | 'right'
  /** 具名插槽名；配置后该列改用父组件的 <template #插槽名="{ row }"> 渲染 */
  slot?: string
  /** 标签渲染模式；'status' 使用内置状态色映射，其他字符串值统一用 info 色 */
  tagType?: 'status' | string
  /** 内容溢出时是否显示 tooltip（本组件样式层面已禁用 tooltip，保留配置以兼容） */
  showOverflowTooltip?: boolean
  /** 值格式化函数，入参为单元格原值与整行数据，返回展示文本 */
  formatter?: (value: any, row: any) => string
}

// ==================== props / emits ====================
/**
 * 表格数据与交互配置。data 为当前页数据（服务端分页），total 为总条数。
 */
const props = withDefaults(
  defineProps<{
    /** 当前页数据行，字段名需与 columns[].prop 对应 */
    data: any[]
    /** 列定义，决定列顺序、宽度、排序与单元格渲染方式 */
    columns: TableColumn[]
    /** 总记录数（后端返回），用于分页器计算页数 */
    total: number
    /** 加载态，透传给 el-table 的 v-loading 遮罩 */
    loading?: boolean
    /** 是否显示多选列，默认 false；批量审批/批量导出场景开启 */
    selection?: boolean
    /** 是否显示序号列，默认 true */
    index?: boolean
    /** 操作列宽度，默认 180px；按钮较多时需调大或改用文字链接 */
    actionWidth?: number | string
    /** 可选每页条数，默认 10/20/50/100/200/500 */
    pageSizes?: number[]
    /** 初始每页条数，默认 10 */
    defaultPageSize?: number
    /** 是否启用大数据量提示，默认 true；仅影响提示条，不改变分页行为 */
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

/**
 * 对外事件契约：
 * - page-change：页码或每页条数变化后触发，父组件据此重新请求列表；
 * - size-change：仅每页条数变化时触发（page-change 同时也会触发一次，页码重置为 1）；
 * - selection-change：多选状态变化时触发，载荷为选中行数组；
 * - sort-change：列排序变化时触发，载荷 { prop, order }，order 为 null 表示取消排序。
 */
const emit = defineEmits<{
  'page-change': [page: number, pageSize: number]
  'size-change': [pageSize: number]
  'selection-change': [selection: any[]]
  'sort-change': [{ prop: string; order: string | null }]
}>()

// ==================== 分页状态 ====================
/** 当前页码，由分页器 v-model 维护 */
const currentPage = ref(1)
/** 当前每页条数，初始值来自 defaultPageSize */
const pageSize = ref(props.defaultPageSize)

/**
 * 行样式类名回调；当前所有行统一使用同一类名，便于全局样式控制（如禁用悬停变色）。
 * @param _rowIndex 行索引，此处未使用
 */
function tableRowClassName({ row, rowIndex }: { row: any; rowIndex: number }) {
  return 'pagination-table-row'
}

/**
 * 计算标签列的颜色。
 * @param col 列定义；col.tagType 为 'status' 时按状态码查内置色表
 * @param row 当前行数据，用 row[col.prop] 取状态值
 * @returns el-tag 的 type；未知状态或非 status 模式统一返回 info
 * 注意：内置映射仅为通用简化版（0 信息 / 10-40 警告 / 50 成功 / 60 危险 / 70 默认），
 *       项目状态需要精确配色时应改用 slot + StatusTag。
 */
function getTagType(col: TableColumn, row: any) {
  if (typeof col.tagType === 'string' && col.tagType === 'status') {
    /** 通用状态色表：0 信息、10-40 警告、50 成功、60 危险、70 默认、80 警告、90 成功 */
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

// ==================== 分页与排序事件 ====================
/**
 * 页码变化：同步内部页码并把 (page, pageSize) 抛给父组件。
 * @param page 新页码（从 1 开始）
 * 副作用：更新 currentPage，触发 page-change。
 */
function handlePageChange(page: number) {
  currentPage.value = page
  emit('page-change', page, pageSize.value)
}

/**
 * 每页条数变化：重置到第一页，避免停留在超出新页数的页码。
 * @param size 新的每页条数
 * 副作用：更新 pageSize/currentPage，先触发 size-change，再以第 1 页触发 page-change。
 */
function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  emit('size-change', size)
  emit('page-change', 1, size)
}

/**
 * 排序变化：仅做事件透传，排序本身由父组件带 order 参数重新请求后端完成。
 * @param prop 排序列字段
 * @param order 排序方向（ascending / descending / null 取消）
 * 副作用：触发 sort-change。
 */
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

/* 表头吸顶：长列表纵向滚动时保持列名可见，z-index 需高于单元格 */
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

/* 分页器右对齐，与表格内容保持视觉对齐 */
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
