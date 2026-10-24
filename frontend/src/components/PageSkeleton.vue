<!-- ==== PageSkeleton 页面骨架屏 ==== -->
<!--
  职责：在路由切换或首屏数据未就绪时，用灰色占位块模拟"标题 + 统计卡 + 表格 + 分页"的页面结构，
        降低布局跳动与白屏带来的感知延迟。
  复用场景：App.vue 在路由切换超过 300ms 时作为全局加载占位；也可在单个页面数据加载时使用。
  外部契约：无 props、无 emit、无插槽，纯展示组件；尺寸与配色由内部样式和主题变量决定。
  注意事项：占位块数量（4 个统计卡、5 行 6 列表格）为固定值，仅用于视觉示意，不代表真实数据。
  设计原则：只占位、不请求、不联动业务数据；主要尺寸尽量接近真实页面，
            避免接口返回后内容高度突变、引发布局抖动与滚动位置跳动。
  可访问性：骨架块属于纯装饰信息，语义由加载完成后的真实内容提供，
            因此不额外添加 aria 属性；动画也只做视觉提示。
-->
<!--
  结构说明：
    1. skeleton-header：模拟页面标题区，两行不同宽度的占位条。
    2. skeleton-stats：4 列统计卡，展示"数值 + 说明"的典型组合。
    3. skeleton-card：主体卡片，内部再分卡片头、表格、分页三段。
    4. shimmer：动画类由全局样式提供（styles/index.css），本组件只负责尺寸与布局。
  样式约定：
    所有卡片背景使用 --card-color，边框使用 --border-color-light，
    表头使用 --table-header-bg，以便骨架屏与真实页面保持同一主题。
  可维护性：
    新增骨架区域时复用 shimmer 类即可获得统一动画；
    布局尺寸尽量使用固定高度 + 比例宽度，避免骨架块自身引发布局抖动；
    移动端断点统一为 768px，与布局侧边栏的移动端阈值保持一致。
-->
<template>
  <div class="page-skeleton">
    <!-- 页头占位：标题与副标题两行，宽度分别模拟真实标题长度 -->
    <div class="skeleton-header">
      <div class="skeleton-title shimmer" style="width: 220px; height: 24px;"></div>
      <div class="skeleton-subtitle shimmer" style="width: 320px; height: 14px; margin-top: 8px;"></div>
    </div>

    <!-- 统计卡占位：固定 4 列，对应常见的数据概览区域 -->
    <div class="skeleton-stats">
      <div
        v-for="i in 4"
        :key="i"
        class="stat-card-skeleton"
      >
        <!-- 上行模拟统计数值，下行模拟指标名称 -->
        <div class="shimmer" style="width: 60%; height: 22px; margin-bottom: 10px;"></div>
        <div class="shimmer" style="width: 35%; height: 14px;"></div>
      </div>
    </div>

    <!-- 主体卡片：卡片头 + 表格骨架 + 分页骨架 -->
    <div class="skeleton-card">
      <div class="skeleton-card-header">
        <div class="shimmer" style="width: 120px; height: 16px;"></div>
        <div class="shimmer" style="width: 80px; height: 16px;"></div>
      </div>

      <!-- 表格骨架：1 行表头 + 5 行数据，每行 6 个单元格 -->
      <div class="skeleton-table">
        <!-- 表头行：6 个等分占位条，对应真实表格的列标题 -->
        <div class="table-header-row">
          <div
            v-for="i in 6"
            :key="'h' + i"
            class="table-cell shimmer"
          ></div>
        </div>
        <div
          v-for="r in 5"
          :key="'r' + r"
          class="table-body-row"
        >
          <div
            v-for="i in 6"
            :key="'c' + r + '-' + i"
            class="table-cell shimmer"
          ></div>
        </div>
      </div>

      <!-- 分页区占位：左侧总数文案、右侧页码按钮 -->
      <div class="skeleton-pagination">
        <!-- 左侧：模拟"共 N 条"总数文案 -->
        <div class="shimmer" style="width: 200px; height: 14px;"></div>
        <!-- 右侧：模拟页码按钮组 -->
        <div class="shimmer" style="width: 260px; height: 28px;"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 纯静态骨架屏，无需响应式状态与逻辑；保留 script setup 以维持标准 SFC 结构。
</script>

<style scoped>
/* 骨架容器：与内容区保持一致的宽度与内边距，减少加载完成后的位置偏移 */
/* 宽度撑满内容区、最大 1400px 居中，避免超宽屏下骨架块被过度拉伸 */
.page-skeleton {
  width: 100%;
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

/* 页头与下方内容保持 20px 间距，与常见页面标题区一致 */
/* 标题区不设固定高度，完全由内部占位条撑开，便于按需增减行数 */
.skeleton-header {
  margin-bottom: 20px;
}

/* 统计卡区域：等宽 4 列，窄屏时在媒体查询中降为 2 列 */
/* gap 与真实统计卡栅格保持一致，避免加载完成后卡片位置发生横向位移 */
.skeleton-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

/* 单个统计卡：白底、圆角、轻阴影，模拟真实卡片容器 */
.stat-card-skeleton {
  background: var(--card-color, #fff);
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

/* 主体卡片：与统计卡相同的视觉规格，保证骨架屏整体一致 */
.skeleton-card {
  background: var(--card-color, #fff);
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

/* 卡片头：两个不同宽度的占位条横向排列 */
.skeleton-card-header {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

/* 表格容器：细边框包裹，overflow hidden 让圆角作用于内部第一行/最后一行 */
/* 表格区域由固定 6 列网格构成，列宽比例贴近常见"序号 + 名称 + 状态 + 时间 + 操作"表格 */
.skeleton-table {
  border: 1px solid var(--border-color-light, #ebeef5);
  border-radius: 6px;
  overflow: hidden;
}

/* 表格行列布局与真实表格保持相近比例：序号列 + 5 个内容列 */
.table-header-row,
.table-body-row {
  display: grid;
  grid-template-columns: 80px 1.5fr 1fr 1fr 1fr 1.2fr;
  gap: 12px;
  padding: 14px 16px;
}

/* 表头行：使用主题表头背景，与真实表格区分 */
.table-header-row {
  background: var(--table-header-bg, #f5f7fa);
  border-bottom: 1px solid var(--border-color-light, #ebeef5);
}

/* 数据行之间画分隔线，最后一行不画，避免与外框重叠 */
.table-body-row:not(:last-child) {
  border-bottom: 1px solid var(--border-color-light, #ebeef5);
}

/* 单元格占位条：统一高度与圆角，宽度由网格列自适应 */
/* 单元格只设高度不设宽度，列宽完全交给外层 grid-template-columns 控制 */
.table-cell {
  height: 14px;
  border-radius: 3px;
}

/* 分页占位：左右分布，模拟总数文案与页码控件 */
.skeleton-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  gap: 16px;
}

/* 移动端适配：统计卡 4 列改 2 列；表格只保留前 4 列，避免横向溢出 */
/* 窄屏下隐藏第 5、6 个单元格，保持骨架与真实表格的响应式列数一致 */
@media (max-width: 768px) {
  .skeleton-stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .table-header-row,
  .table-body-row {
    grid-template-columns: 60px 1fr 0.8fr 0.8fr;
  }

  .table-header-row .table-cell:nth-child(n+5),
  .table-body-row .table-cell:nth-child(n+5) {
    display: none;
  }
}
</style>
