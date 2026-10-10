<template>
  <div class="page-skeleton">
    <div class="skeleton-header">
      <div class="skeleton-title shimmer" style="width: 220px; height: 24px;"></div>
      <div class="skeleton-subtitle shimmer" style="width: 320px; height: 14px; margin-top: 8px;"></div>
    </div>

    <div class="skeleton-stats">
      <div
        v-for="i in 4"
        :key="i"
        class="stat-card-skeleton"
      >
        <div class="shimmer" style="width: 60%; height: 22px; margin-bottom: 10px;"></div>
        <div class="shimmer" style="width: 35%; height: 14px;"></div>
      </div>
    </div>

    <div class="skeleton-card">
      <div class="skeleton-card-header">
        <div class="shimmer" style="width: 120px; height: 16px;"></div>
        <div class="shimmer" style="width: 80px; height: 16px;"></div>
      </div>

      <div class="skeleton-table">
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

      <div class="skeleton-pagination">
        <div class="shimmer" style="width: 200px; height: 14px;"></div>
        <div class="shimmer" style="width: 260px; height: 28px;"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.page-skeleton {
  width: 100%;
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.skeleton-header {
  margin-bottom: 20px;
}

.skeleton-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card-skeleton {
  background: var(--card-color, #fff);
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

.skeleton-card {
  background: var(--card-color, #fff);
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

.skeleton-card-header {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.skeleton-table {
  border: 1px solid var(--border-color-light, #ebeef5);
  border-radius: 6px;
  overflow: hidden;
}

.table-header-row,
.table-body-row {
  display: grid;
  grid-template-columns: 80px 1.5fr 1fr 1fr 1fr 1.2fr;
  gap: 12px;
  padding: 14px 16px;
}

.table-header-row {
  background: var(--table-header-bg, #f5f7fa);
  border-bottom: 1px solid var(--border-color-light, #ebeef5);
}

.table-body-row:not(:last-child) {
  border-bottom: 1px solid var(--border-color-light, #ebeef5);
}

.table-cell {
  height: 14px;
  border-radius: 3px;
}

.skeleton-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
  gap: 16px;
}

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
