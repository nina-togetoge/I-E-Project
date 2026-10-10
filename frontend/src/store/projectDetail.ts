/**
 * 项目详情弹窗 Store
 * 全局控制项目详情弹窗的显示与项目 ID
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useProjectDetailStore = defineStore('projectDetail', () => {
  const visible = ref(false)
  const projectId = ref<number | null>(null)

  function open(id: number) {
    projectId.value = id
    visible.value = true
  }

  function close() {
    visible.value = false
    projectId.value = null
  }

  return { visible, projectId, open, close }
})
