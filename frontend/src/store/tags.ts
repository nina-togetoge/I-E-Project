/**
 * 多页签状态管理（Pinia）
 *
 * 维护顶栏下方的 TagsView 页签列表：访问过的路由、标题、图标与固定标记。
 * 生命周期：router.afterEach 每次导航后调用 addView 追加；页签右键菜单调用
 * removeView/removeOthers/removeAll 关闭；状态仅保存在内存，刷新页面后重置。
 * 不发起任何网络请求，也不持久化。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'

/** 单个页签：path 为唯一键，affix 的页签（首页）不可关闭 */
export interface TagView {
  /** 路由完整路径，作为去重与关闭的依据 */
  path: string
  /** 页签文案，优先取 route.meta.title */
  title: string
  /** Element Plus 图标名 */
  icon?: string
  /** 是否固定：固定页签不参与单条/全部关闭 */
  affix?: boolean
}

export const useTagsStore = defineStore('tags', () => {
  /** 已访问页签列表，初始只放固定的「首页」 */
  const visitedViews = ref<TagView[]>([
    { path: '/dashboard', title: '首页', icon: 'HomeFilled', affix: true },
  ])

  /**
   * 追加页签（不重复）
   * 由 router.afterEach 调用；登录/403/404 页在守卫处已跳过。
   * 标题取 meta.title → route.name → path 的兜底顺序。
   */
  function addView(route: RouteLocationNormalized) {
    if (!route.path) return
    if (visitedViews.value.some((v) => v.path === route.path)) return
    visitedViews.value.push({
      path: route.path,
      title: String(route.meta?.title || route.name || route.path),
      icon: route.meta?.icon as string | undefined,
      affix: false,
    })
  }

  /**
   * 关闭单个页签
   * @param path 目标页签路径；affix 固定页签不会被移除（findIndex 条件带 !affix）。
   * 调用方：TagsView 页签的关闭按钮。
   */
  function removeView(path: string) {
    const idx = visitedViews.value.findIndex((v) => v.path === path && !v.affix)
    if (idx > -1) {
      visitedViews.value.splice(idx, 1)
    }
  }

  /**
   * 关闭其它页签：只保留当前页签与所有 affix 固定页签
   * 调用方：TagsView 右键菜单「关闭其它」。
   */
  function removeOthers(path: string) {
    visitedViews.value = visitedViews.value.filter(
      (v) => v.path === path || v.affix
    )
  }

  /**
   * 关闭全部页签：仅保留 affix 固定页签
   * 调用方：TagsView 右键菜单「关闭全部」。
   */
  function removeAll() {
    visitedViews.value = visitedViews.value.filter((v) => v.affix)
  }

  return {
    visitedViews,
    addView,
    removeView,
    removeOthers,
    removeAll,
  }
})
