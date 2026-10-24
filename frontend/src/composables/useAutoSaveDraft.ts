/**
 * 表单草稿自动保存组合式函数
 *
 * 模块职责：
 *  - 在用户填写长表单（项目申报、中期检查、结题材料等）时，把表单快照定时写入 localStorage，
 *    防止误刷新、浏览器崩溃或切换页面导致内容丢失。
 *  - 与后端保存的关系：草稿只存在本地，不会自动提交后端；用户点击“保存/提交”时仍走正常接口。
 *    正式保存成功后应主动调用 clearDraft()，避免下次进入时恢复出旧内容。
 *
 * 触发时机：
 *  - 监听表单深度变化，变化后延迟 interval 毫秒写入（防抖，连续输入只落盘一次）；
 *  - 组件卸载时取消防抖并立即补存一次，保证离开页面前的最后修改不丢。
 *
 * 存储 key 规则：localStorage 中的 key 固定为 `project_draft_` + 调用方传入的 key，
 * 调用方需保证 key 能唯一定位一份表单（例如 project_create、midterm_<项目id>）。
 */
import { ref, watch, onBeforeUnmount, isRef, isReactive, toRaw, type Ref } from 'vue'

/** 草稿在 localStorage 中的存储结构，savedAt 用于界面提示“上次保存时间” */
interface DraftData<T> {
  /** 表单快照（已 toRaw，去掉响应式代理） */
  data: T
  /** 保存时间戳（毫秒） */
  savedAt: number
}

/**
 * 创建草稿自动保存能力。
 * @param key 业务唯一标识，最终存储 key 为 `project_draft_${key}`
 * @param formData 表单对象，支持普通对象或 ref 包裹的对象
 * @param interval 防抖写入间隔（毫秒），默认 30000，即停止输入 30 秒后落盘
 * @returns savedAt 最近保存时间、hasDraft 是否存在草稿、以及手动保存/加载/清理方法
 * 注意：localStorage 容量有限且只存字符串，表单中的 File 等不可序列化字段不会被保留。
 */
export function useAutoSaveDraft<T extends Record<string, any>>(
  key: string,
  formData: T | Ref<T>,
  interval: number = 30000
) {
  // 统一前缀隔离业务草稿，避免与登录态、主题等其他 localStorage 键冲突
  const storageKey = 'project_draft_' + key
  /** 最近一次成功保存的时间戳，null 表示当前会话尚未保存过 */
  const savedAt = ref<number | null>(null)
  /** 是否存在可恢复的草稿，供页面决定是否弹出“恢复草稿”提示 */
  const hasDraft = ref(false)
  /** 防抖计时器句柄，避免连续输入时频繁写 localStorage */
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * 取表单原始对象：ref 取 .value，再用 toRaw 去掉响应式代理，
   * 防止 JSON.stringify 时把 Proxy 内部结构或循环引用写进草稿。
   */
  function getData(): T {
    if (isRef(formData)) {
      return toRaw(formData.value)
    }
    return toRaw(formData)
  }

  /**
   * 立即把当前表单快照写入 localStorage。
   * 写入失败（如超出配额、隐私模式禁用存储）只记录错误，不打断用户填写。
   * 副作用：成功后更新 savedAt 与 hasDraft 两个响应式状态。
   */
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

  /**
   * 读取并解析本地草稿。
   * @returns 草稿中的表单数据；无草稿或 JSON 损坏时返回 null（后者会记录错误）
   * 注意：本方法只读取，不会把数据写回表单，调用方需自行合并/替换表单字段。
   */
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

  /**
   * 清理本地草稿并复位状态。
   * 调用时机：正式提交/保存成功、用户明确选择“放弃草稿”、或进入已完成态页面。
   */
  function clearDraft() {
    localStorage.removeItem(storageKey)
    savedAt.value = null
    hasDraft.value = false
  }

  /**
   * 初始化探测：进入页面时检查是否已有草稿，仅同步 hasDraft/savedAt，不触发恢复动作。
   * 解析失败时静默忽略，避免损坏的旧数据阻塞页面加载。
   */
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

  /**
   * 防抖保存：每次表单变化都重置计时器，只有停止变化 interval 毫秒后才真正落盘，
   * 避免用户连续输入时每秒都写 localStorage。
   */
  function debouncedSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      saveDraft()
    }, interval)
  }

  // watch 的数据源：ref 直接监听；普通对象用 getter 包装，保证 watch 能追踪其属性访问
  const watchSource = isRef(formData)
    ? formData
    : (() => formData) as () => T

  // 深度监听表单，任意字段变化都走防抖保存（嵌套对象/数组的修改同样能捕获）
  watch(
    watchSource,
    () => {
      debouncedSave()
    },
    { deep: true }
  )

  // 组件卸载：取消尚未触发的防抖任务并立即补存，确保离开页面前的最后一次修改不丢失
  onBeforeUnmount(() => {
    if (debounceTimer) clearTimeout(debounceTimer)
    saveDraft()
  })

  // 创建时立即探测一次，供页面在挂载阶段决定是否提示恢复草稿
  checkDraft()

  return {
    /** 最近一次草稿保存时间戳，可用于展示“已于 xx 保存” */
    savedAt,
    /** 手动立即保存，通常绑定到“存草稿”按钮 */
    saveDraft,
    /** 读取本地草稿数据，调用方自行决定是否覆盖当前表单 */
    loadDraft,
    /** 删除本地草稿，正式保存成功后调用 */
    clearDraft,
    /** 是否存在草稿，用于控制“恢复草稿”入口显隐 */
    hasDraft,
  }
}
