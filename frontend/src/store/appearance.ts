/**
 * 外观/主题状态管理（Pinia）
 *
 * 管理三类全局外观配置，并通过 watch 持久化到 localStorage：
 *   - 深色模式 isDark：给 <html> 加/移除 dark 类，驱动 Element Plus 暗色变量；
 *   - 主题色 themeColor：写入 --primary-color 与 --el-color-primary 两个 CSS 变量；
 *   - 盲审模式 isBlindMode：评审相关页面据此隐藏项目/人员身份信息（composable 使用）。
 * 生命周期：store 首次创建时恢复配置并立即应用；之后每次变更由 watch 自动落盘。
 * 调用方：App.vue、layout 顶栏 ThemeToggle/ThemePicker、Statistics/ExpertPending
 *         等需要读写盲审开关的页面。
 * 不发起网络请求，所有配置仅保存在本机浏览器。
 */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

/** localStorage 键：深色模式开关（'true'/'false'） */
const STORAGE_KEY_DARK = 'appearance_is_dark'
/** localStorage 键：主题色十六进制值 */
const STORAGE_KEY_THEME = 'appearance_theme_color'
/** localStorage 键：盲审模式开关（'true'/'false'） */
const STORAGE_KEY_BLIND = 'appearance_is_blind_mode'

/** 预设主题色：ThemePicker 色板使用，顺序即展示顺序 */
const PRESET_COLORS = [
  '#409EFF',
  '#FF6B35',
  '#52C41A',
  '#722ED1',
  '#13C2C2',
  '#EB2F96',
]

export const useAppearanceStore = defineStore('appearance', () => {
  /** 是否深色模式，初始值从 localStorage 恢复 */
  const isDark = ref<boolean>(localStorage.getItem(STORAGE_KEY_DARK) === 'true')
  /** 当前主题色，默认 Element Plus 蓝 #409EFF */
  const themeColor = ref<string>(localStorage.getItem(STORAGE_KEY_THEME) || '#409EFF')
  /** 是否开启盲审模式：开启后评审页面隐藏项目/人员身份 */
  const isBlindMode = ref<boolean>(localStorage.getItem(STORAGE_KEY_BLIND) === 'true')
  /** 可选主题色列表，供 ThemePicker 展示；运行时只读 */
  const presetColors = ref<string[]>(PRESET_COLORS)

  /**
   * 应用深色模式到 DOM：切换 <html> 的 dark 类
   * 只改类名，不负责持久化（持久化由下方 watch 完成）。
   */
  function applyDark(dark: boolean) {
    if (dark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  /**
   * 应用主题色：同时覆盖业务变量 --primary-color 与 Element Plus 的 --el-color-primary
   * 只改 CSS 变量，不负责持久化。
   */
  function applyThemeColor(color: string) {
    document.documentElement.style.setProperty('--primary-color', color)
    document.documentElement.style.setProperty('--el-color-primary', color)
  }

  /** 切换深色模式（顶栏 ThemeToggle 调用）；watch 会自动应用并落盘 */
  function toggleDark() {
    isDark.value = !isDark.value
  }

  /** 切换盲审模式（评审页开关调用）；watch 自动写入 localStorage */
  function toggleBlindMode() {
    isBlindMode.value = !isBlindMode.value
  }

  /** 设置主题色（ThemePicker 选色后调用）；非法值不做校验，由调用方保证 */
  function setThemeColor(color: string) {
    themeColor.value = color
  }

  // 初始化：立即把恢复出的配置应用到 DOM，避免首屏闪烁
  applyDark(isDark.value)
  applyThemeColor(themeColor.value)

  // 深色模式变更：先应用再持久化，保证刷新后与当前一致
  watch(isDark, (val) => {
    applyDark(val)
    localStorage.setItem(STORAGE_KEY_DARK, String(val))
  })

  // 主题色变更：覆盖 CSS 变量并写入 localStorage
  watch(themeColor, (val) => {
    applyThemeColor(val)
    localStorage.setItem(STORAGE_KEY_THEME, val)
  })

  // 盲审模式无 DOM 副作用，只需持久化，供各评审页下次进入时读取
  watch(isBlindMode, (val) => {
    localStorage.setItem(STORAGE_KEY_BLIND, String(val))
  })

  return {
    isDark,
    themeColor,
    isBlindMode,
    presetColors,
    toggleDark,
    toggleBlindMode,
    setThemeColor,
  }
})
