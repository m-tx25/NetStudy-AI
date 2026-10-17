import { computed, ref } from 'vue'
import { STORAGE_KEYS } from '@/config'

/** 站点默认主题：深灰科技风 */
export const DEFAULT_THEME = 'dark'

const theme = ref(DEFAULT_THEME)

function readStoredTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEYS.theme)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* ignore */
  }
  // 没有历史选择时按产品设计走深色，而不是跟随系统
  return DEFAULT_THEME
}

/**
 * 把 html 上的 class 同步到当前主题（Tailwind darkMode: 'class' + Element Plus dark 变量）。
 * @param {'light'|'dark'} next
 * @param {{ persist?: boolean }} options persist=false 用于启动时套用默认主题，不写入 localStorage
 */
export function applyTheme(next, { persist = true } = {}) {
  theme.value = next === 'light' ? 'light' : 'dark'
  if (typeof document !== 'undefined') {
    const root = document.documentElement
    root.classList.toggle('dark', theme.value === 'dark')
    root.style.colorScheme = theme.value
  }
  if (!persist) return
  try {
    localStorage.setItem(STORAGE_KEYS.theme, theme.value)
  } catch {
    /* ignore */
  }
}

/** 应用启动时调用一次 */
export function applyStoredTheme() {
  applyTheme(readStoredTheme(), { persist: false })
}

export function useTheme() {
  return {
    theme,
    isDark: computed(() => theme.value === 'dark'),
    setTheme: (next) => applyTheme(next),
    toggleTheme: () => applyTheme(theme.value === 'dark' ? 'light' : 'dark'),
  }
}
