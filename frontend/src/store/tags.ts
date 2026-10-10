import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { RouteLocationNormalized } from 'vue-router'

export interface TagView {
  path: string
  title: string
  icon?: string
  affix?: boolean
}

export const useTagsStore = defineStore('tags', () => {
  const visitedViews = ref<TagView[]>([
    { path: '/dashboard', title: '首页', icon: 'HomeFilled', affix: true },
  ])

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

  function removeView(path: string) {
    const idx = visitedViews.value.findIndex((v) => v.path === path && !v.affix)
    if (idx > -1) {
      visitedViews.value.splice(idx, 1)
    }
  }

  function removeOthers(path: string) {
    visitedViews.value = visitedViews.value.filter(
      (v) => v.path === path || v.affix
    )
  }

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
