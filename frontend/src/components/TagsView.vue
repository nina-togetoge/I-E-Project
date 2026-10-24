<!-- ==== TagsView 多标签页导航 ==== -->
<!--
  职责：展示用户访问过的路由标签，支持点击切换、单选关闭、关闭其他、关闭全部；
        标签数据集中保存在 Pinia 的 tags store 中，供布局层统一读取。
  复用场景：layout/index.vue 顶栏下方，登录后的主布局内固定展示。
  外部契约：无 props、无 emit；依赖 tagsStore.visitedViews 与当前 route/router。
  注意事项：当前布局未启用 keep-alive，标签仅表示"访问历史"，切换标签会重新渲染页面；
           affix 标签（如首页）不可关闭；store 未做持久化，刷新浏览器后回到初始标签。
  数据结构：visitedViews 为 TagView[]，每项含 path/title/icon/affix；
            path 作为唯一键，重复访问同一路由不会新增标签。
  交互约定：
    1. 点击标签 → router.push(view.path)，由路由守卫再次校验权限。
    2. 点击关闭 → 从 store 移除；若关闭的是当前页，跳到剩余最后一个标签。
    3. 关闭其他 → 保留当前页与 affix；关闭全部 → 只保留 affix。
  扩展提示：若后续启用 keep-alive，可在此组件增加"刷新当前标签"命令，
            通过 store 维护 refreshKey 强制重建组件。
-->
<template>
  <div class="tags-view">
    <!-- 标签列表：当前路由高亮，affix 标签隐藏关闭按钮 -->
    <div class="tags-wrapper">
      <!-- 每个标签以 path 为 key；affix 项无关闭按钮；
           激活项使用 primary + dark，非激活项使用 info + plain -->
      <el-tag
        v-for="view in tagsStore.visitedViews"
        :key="view.path"
        :closable="!view.affix"
        :type="route.path === view.path ? 'primary' : 'info'"
        :effect="route.path === view.path ? 'dark' : 'plain'"
        class="tag-item"
        @click="router.push(view.path)"
        @close="handleClose(view.path)"
      >
        <!-- 图标来自路由 meta.icon，动态组件渲染 -->
        <el-icon v-if="view.icon" class="tag-icon">
          <component :is="view.icon" />
        </el-icon>
        <!-- 标签标题来自路由 meta.title，store 在路由变化时写入 -->
        <span>{{ view.title }}</span>
      </el-tag>
    </div>
    <!-- 批量操作入口：关闭其他 / 关闭全部 -->
    <div class="tags-actions">
      <el-dropdown trigger="click" @command="handleCommand">
        <el-button size="small" plain>
          <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <!-- 保留当前路由与 affix 标签，其余移除 -->
            <el-dropdown-item command="others">关闭其他</el-dropdown-item>
            <!-- 仅保留 affix 标签；若当前页被关闭则跳转到剩余第一个标签 -->
            <el-dropdown-item command="all">关闭全部</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { useTagsStore } from '@/store/tags'

// ==================== 依赖注入 ====================
// route 用于判断当前激活标签；router 用于标签切换与关闭后的兜底跳转。
const route = useRoute()
const router = useRouter()
// 标签集合的唯一数据源，增删逻辑均在 store 内实现。
const tagsStore = useTagsStore()

// ==================== 关闭单个标签 ====================
/**
 * 关闭指定标签
 * 副作用：若关闭的是当前激活标签，则跳转到剩余标签的最后一个；
 *        若已无剩余标签（理论上有首页 affix 兜底），则不跳转。
 */
function handleClose(path: string) {
  // 当前页被关闭时需要记录，决定后续是否跳转
  const isActive = route.path === path
  tagsStore.removeView(path)
  if (isActive && tagsStore.visitedViews.length > 0) {
    const last = tagsStore.visitedViews[tagsStore.visitedViews.length - 1]
    router.push(last.path)
  }
}

// ==================== 批量关闭 ====================
/**
 * 处理下拉菜单命令
 * others：关闭除当前路由外的标签；all：关闭除 affix 外的全部标签。
 * 副作用：关闭全部后若当前页已被移除，跳转到剩余的第一个标签（通常是首页）。
 */
function handleCommand(cmd: string) {
  if (cmd === 'others') {
    tagsStore.removeOthers(route.path)
  } else if (cmd === 'all') {
    tagsStore.removeAll()
    if (tagsStore.visitedViews.length > 0) {
      router.push(tagsStore.visitedViews[0].path)
    }
  }
}
</script>

<style scoped>
/* 标签条：与顶栏同色，底部一条分隔线；颜色随主题平滑过渡 */
.tags-view {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--header-color, #fff);
  border-bottom: 1px solid var(--border-color-light, #ebeef5);
  transition: background 0.3s ease, border-color 0.3s ease;
}

/* 标签容器：占据剩余宽度；换行受限高 40px，超出部分横向滚动 */
.tags-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  overflow-x: auto;
  padding-right: 8px;
  max-height: 40px;
}

/* 单个标签：不收缩，避免空间不足时标题被压扁 */
/* 标签类型与效果由模板根据是否当前路由动态决定，此处只固定布局行为 */
.tag-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  flex-shrink: 0;
  margin-right: 0;
}

/* Element Plus 内部内容容器：改为 flex，保证图标与文字垂直居中 */
.tag-item :deep(.el-tag__content) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 标签内图标：略小于文字高度，避免标签整体过高 */
.tag-icon {
  font-size: 13px;
  line-height: 1;
}

/* 右侧操作区不参与收缩，始终完整显示 */
.tags-actions {
  flex-shrink: 0;
}

/* 移动端：压缩内边距，并截断过长标题，保证标签条不换行溢出 */
@media (max-width: 768px) {
  .tags-view {
    padding: 6px 12px;
  }
  .tag-item .el-tag__content span {
    max-width: 60px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
