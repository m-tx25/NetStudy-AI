import { computed, ref } from 'vue'
import { STORAGE_KEYS } from '@/config'

const theme = ref('light')

function readInitialTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEYS.theme)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* ignore */
  }
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  return prefersDark ? 'dark' : 'light'
}

/** 把 html 上的 class 同步到当前主题（Tailwind darkMode: 'class' + Element Plus dark 变量） */
export function applyTheme(next) {
  theme.value = next === 'dark' ? 'dark' : 'light'
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.classList.toggle('dark', theme.value === 'dark')
  root.style.colorScheme = theme.value
  try {
    localStorage.setItem(STORAGE_KEYS.theme, theme.value)
  } catch {
    /* ignore */
  }
}

/** 应用启动时调用一次 */
export function applyStoredTheme() {
  applyTheme(readInitialTheme())
}

export function useTheme() {
  return {
    theme,
    isDark: computed(() => theme.value === 'dark'),
    setTheme: applyTheme,
    toggleTheme: () => applyTheme(theme.value === 'dark' ? 'light' : 'dark'),
  }
}
