/**
 * 项目详情弹窗 Store
 *
 * 跨页面共享「项目详情」窗口的开合状态与当前项目 ID，
 * 让列表页（我的项目、审核待办、归档库、立项公示、专家任务、管理端项目库）
 * 无需各自维护弹窗实例，统一由 components/ProjectDetailDialog.vue 渲染。
 * 生命周期：open 写入 ID 并显示；close 清空 ID 并隐藏，弹窗内的详情数据由
 * ProjectDetail.vue 根据 projectId 自行请求，store 不缓存项目详情。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useProjectDetailStore = defineStore('projectDetail', () => {
  /** 弹窗是否显示，绑定到 ProjectDetailDialog 的 v-if */
  const visible = ref(false)
  /** 当前查看的项目 ID，为 null 时弹窗内容不应渲染 */
  const projectId = ref<number | null>(null)

  /**
   * 打开项目详情弹窗
   * @param id 项目主键；列表页点击项目名/「详情」时调用。
   * 会先设置 ID 再显示，确保子组件挂载时能拿到有效 projectId。
   */
  function open(id: number) {
    projectId.value = id
    visible.value = true
  }

  /**
   * 关闭项目详情弹窗并清空 ID
   * 调用方：ProjectDetailDialog 的遮罩点击、关闭按钮与底部「关闭」；
   * 清空 ID 可让弹窗内 ProjectDetail 在下次打开时重新初始化。
   */
  function close() {
    visible.value = false
    projectId.value = null
  }

  return { visible, projectId, open, close }
})
