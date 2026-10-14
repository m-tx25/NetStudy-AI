import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  changePassword as changePasswordApi,
  fetchProfile,
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
  updateProfile as updateProfileApi,
} from '@/api/auth'
import { clearToken, getToken, resetUnauthorizedNotified, setToken } from '@/api/request'
import { STORAGE_KEYS } from '@/config'

function readStoredUser() {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.user)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function persistUser(user) {
  try {
    if (user) localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user))
    else localStorage.removeItem(STORAGE_KEYS.user)
  } catch {
    /* ignore */
  }
}

export const useUserStore = defineStore('user', () => {
  const token = ref(getToken())
  const profile = ref(readStoredUser())
  const loading = ref(false)
  const savingProfile = ref(false)
  const changingPassword = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))

  const displayName = computed(
    () => profile.value?.nickname || profile.value?.username || '未登录用户',
  )

  const avatarText = computed(() => {
    const name = displayName.value
    return name ? name.slice(0, 1).toUpperCase() : 'U'
  })

  const username = computed(() => profile.value?.username || '')
  const email = computed(() => profile.value?.email || '')
  const roleLabel = computed(() => {
    const role = profile.value?.role
    if (role === 'admin') return '管理员'
    if (role === 'owner') return '所有者'
    return '成员'
  })

  function setSession(payload) {
    token.value = payload?.token || ''
    profile.value = payload?.user || payload?.profile || null
    setToken(token.value)
    persistUser(profile.value)
    // 刚拿到的 token 一定是有效的，无需再校验
    sessionChecked.value = true
    // 允许下次失效时再次提示（否则本次登录失效的提示会被永久吞掉）
    resetUnauthorizedNotified()
  }

  function clearSession() {
    token.value = ''
    profile.value = null
    clearToken()
    persistUser(null)
    // 已清空，无需再校验；下次登录会重新置位
    sessionChecked.value = true
  }

  async function login(form) {
    loading.value = true
    try {
      const result = await loginApi(form)
      setSession(result)
      return result
    } finally {
      loading.value = false
    }
  }

  async function register(form) {
    loading.value = true
    try {
      const result = await registerApi(form)
      setSession(result)
      return result
    } finally {
      loading.value = false
    }
  }

  async function loadProfile() {
    if (!token.value) return null
    try {
      const user = await fetchProfile({ silent: true })
      profile.value = user
      persistUser(user)
      return user
    } catch (error) {
      // token 失效：清理会话，由路由守卫接管跳转
      if (error?.status === 401) {
        clearSession()
      }
      return null
    }
  }

  /**
   * 启动时校验本地 token 是否仍然有效。
   *
   * 为什么需要：路由守卫只能看到「本地有没有 token」，看不到它是否还有效。
   * 后端换过 SECRET_KEY、改过密码、或重建过数据库之后，旧 token 会失效，
   * 但守卫仍会放行到 /chat，页面随即并发发出多个请求全部 401，
   * 用户看到的就是「登录状态已失效」—— 其实他从未登录成功过。
   *
   * 这里在进入受保护路由之前先问一次后端（GET /auth/me，静默）：
   *   - 有效 → 标记已校验，守卫放行；
   *   - 失效 → 清掉本地会话，守卫自然跳到登录页。
   * 只做一次，登录成功后重置标记。
   */
  const sessionChecked = ref(false)
  let checking = null

  async function ensureSessionChecked() {
    if (sessionChecked.value) return
    if (!token.value) {
      sessionChecked.value = true
      return
    }
    // 并发调用时复用同一个校验，避免重复请求
    if (!checking) {
      checking = loadProfile().finally(() => {
        sessionChecked.value = true
        checking = null
      })
    }
    await checking
  }

  async function logout() {
    try {
      await logoutApi()
    } catch {
      /* 退出接口失败也要清本地状态 */
    }
    clearSession()
  }

  /**
   * 修改账号资料（用户名 / 昵称 / 邮箱）。
   * 成功后就地更新 profile 并落盘，侧边栏与头像会立即跟着变。
   */
  async function updateProfile(payload) {
    savingProfile.value = true
    try {
      const updated = await updateProfileApi(payload)
      const merged = { ...(profile.value || {}), ...(updated || {}) }
      profile.value = merged
      persistUser(merged)
      return merged
    } finally {
      savingProfile.value = false
    }
  }

  /** 修改密码：校验与提示交给调用方，这里只负责请求 */
  async function changePassword(payload) {
    changingPassword.value = true
    try {
      return await changePasswordApi(payload)
    } finally {
      changingPassword.value = false
    }
  }

  /** 修改完密码后强制重新登录（清掉本地会话） */
  function forceRelogin() {
    clearSession()
  }

  return {
    token,
    profile,
    loading,
    savingProfile,
    changingPassword,
    isAuthenticated,
    /** 启动时是否已校验过本地 token 的有效性 */
    sessionChecked,
    displayName,
    avatarText,
    username,
    email,
    roleLabel,
    setSession,
    clearSession,
    forceRelogin,
    login,
    register,
    updateProfile,
    changePassword,
    loadProfile,
    ensureSessionChecked,
    logout,
  }
})
