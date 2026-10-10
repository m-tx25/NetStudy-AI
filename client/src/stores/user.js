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
import { clearToken, getToken, setToken } from '@/api/request'
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
  }

  function clearSession() {
    token.value = ''
    profile.value = null
    clearToken()
    persistUser(null)
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
    logout,
  }
})
