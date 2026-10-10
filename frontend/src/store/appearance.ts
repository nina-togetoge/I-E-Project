import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY_DARK = 'appearance_is_dark'
const STORAGE_KEY_THEME = 'appearance_theme_color'
const STORAGE_KEY_BLIND = 'appearance_is_blind_mode'

const PRESET_COLORS = [
  '#409EFF',
  '#FF6B35',
  '#52C41A',
  '#722ED1',
  '#13C2C2',
  '#EB2F96',
]

export const useAppearanceStore = defineStore('appearance', () => {
  const isDark = ref<boolean>(localStorage.getItem(STORAGE_KEY_DARK) === 'true')
  const themeColor = ref<string>(localStorage.getItem(STORAGE_KEY_THEME) || '#409EFF')
  const isBlindMode = ref<boolean>(localStorage.getItem(STORAGE_KEY_BLIND) === 'true')
  const presetColors = ref<string[]>(PRESET_COLORS)

  function applyDark(dark: boolean) {
    if (dark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  function applyThemeColor(color: string) {
    document.documentElement.style.setProperty('--primary-color', color)
    document.documentElement.style.setProperty('--el-color-primary', color)
  }

  function toggleDark() {
    isDark.value = !isDark.value
  }

  function toggleBlindMode() {
    isBlindMode.value = !isBlindMode.value
  }

  function setThemeColor(color: string) {
    themeColor.value = color
  }

  applyDark(isDark.value)
  applyThemeColor(themeColor.value)

  watch(isDark, (val) => {
    applyDark(val)
    localStorage.setItem(STORAGE_KEY_DARK, String(val))
  })

  watch(themeColor, (val) => {
    applyThemeColor(val)
    localStorage.setItem(STORAGE_KEY_THEME, val)
  })

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
