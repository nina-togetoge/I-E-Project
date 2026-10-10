import { ref, watch, onBeforeUnmount, isRef, isReactive, toRaw, type Ref } from 'vue'

interface DraftData<T> {
  data: T
  savedAt: number
}

export function useAutoSaveDraft<T extends Record<string, any>>(
  key: string,
  formData: T | Ref<T>,
  interval: number = 30000
) {
  const storageKey = 'project_draft_' + key
  const savedAt = ref<number | null>(null)
  const hasDraft = ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  function getData(): T {
    if (isRef(formData)) {
      return toRaw(formData.value)
    }
    return toRaw(formData)
  }

  function saveDraft() {
    try {
      const data = getData()
      const draft: DraftData<T> = {
        data,
        savedAt: Date.now(),
      }
      localStorage.setItem(storageKey, JSON.stringify(draft))
      savedAt.value = draft.savedAt
      hasDraft.value = true
    } catch (e) {
      console.error('保存草稿失败:', e)
    }
  }

  function loadDraft(): T | null {
    try {
      const raw = localStorage.getItem(storageKey)
      if (!raw) return null
      const draft: DraftData<T> = JSON.parse(raw)
      savedAt.value = draft.savedAt
      hasDraft.value = true
      return draft.data
    } catch (e) {
      console.error('加载草稿失败:', e)
      return null
    }
  }

  function clearDraft() {
    localStorage.removeItem(storageKey)
    savedAt.value = null
    hasDraft.value = false
  }

  function checkDraft() {
    const raw = localStorage.getItem(storageKey)
    hasDraft.value = !!raw
    if (raw) {
      try {
        const draft: DraftData<T> = JSON.parse(raw)
        savedAt.value = draft.savedAt
      } catch (_) {}
    }
  }

  function debouncedSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      saveDraft()
    }, interval)
  }

  const watchSource = isRef(formData)
    ? formData
    : (() => formData) as () => T

  watch(
    watchSource,
    () => {
      debouncedSave()
    },
    { deep: true }
  )

  onBeforeUnmount(() => {
    if (debounceTimer) clearTimeout(debounceTimer)
    saveDraft()
  })

  checkDraft()

  return {
    savedAt,
    saveDraft,
    loadDraft,
    clearDraft,
    hasDraft,
  }
}
