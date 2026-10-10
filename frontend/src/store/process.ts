import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 项目流程状态共享 store
 * 用于在主侧边栏展示当前项目的"过程管理"流程阶段
 */
export const useProcessStore = defineStore('process', () => {
  /** 当前查看的项目状态，null 表示不在项目详情页 */
  const projectStatus = ref<number | null>(null)
  /** 侧边栏点击阶段后，详情页监听此值滚动到对应区域 */
  const scrollToStage = ref<string>('')

  function setStatus(status: number | null) {
    projectStatus.value = status
  }

  function requestScroll(stageKey: string) {
    // 用时间戳确保同一阶段重复点击也能触发
    scrollToStage.value = `${stageKey}:${Date.now()}`
  }

  function reset() {
    projectStatus.value = null
    scrollToStage.value = ''
  }

  return { projectStatus, scrollToStage, setStatus, requestScroll, reset }
})
