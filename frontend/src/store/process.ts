/**
 * 项目流程状态共享 store（Pinia）
 *
 * 用于在主侧边栏展示当前项目的「过程管理」流程阶段，并在点击阶段时
 * 通知项目详情页滚动到对应区域；同时让左右两侧共享「当前项目状态」。
 * 生命周期：进入项目详情/中期/结题/成果页时 setStatus，离开时 reset；
 * requestScroll 通过时间戳后缀保证同一阶段重复点击也能触发监听。
 * 不发起网络请求、不做持久化，仅内存共享。
 */
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

  /**
   * 设置当前项目状态
   * @param status 项目状态值（见 PROJECT_STATUS）；传 null 表示离开项目详情页。
   * 侧边栏据此高亮阶段并决定哪些阶段可点击。
   */
  function setStatus(status: number | null) {
    projectStatus.value = status
  }

  /**
   * 请求详情页滚动到指定阶段
   * @param stageKey 阶段锚点键（如 midterm/final/achievement）
   * 值追加时间戳，使相同 stageKey 的重复点击仍产生新值、触发 watch。
   * 调用方：layout 侧边栏过程管理菜单。
   */
  function requestScroll(stageKey: string) {
    // 用时间戳确保同一阶段重复点击也能触发
    scrollToStage.value = `${stageKey}:${Date.now()}`
  }

  /**
   * 重置流程状态：清空项目状态与滚动指令
   * 调用方：离开项目相关页面时（组件卸载），避免侧边栏残留上一个项目的阶段。
   */
  function reset() {
    projectStatus.value = null
    scrollToStage.value = ''
  }

  return { projectStatus, scrollToStage, setStatus, requestScroll, reset }
})
