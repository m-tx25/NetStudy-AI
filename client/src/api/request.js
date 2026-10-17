import axios from 'axios'
import { ElMessage } from 'element-plus'

import { API_BASE_URL, STORAGE_KEYS } from '@/config'

/* ------------------------------------------------------------------ *
 * 错误类型
 * ------------------------------------------------------------------ */
export class ApiError extends Error {
  constructor(message, meta = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = meta.code
    this.status = meta.status
    this.payload = meta.payload
  }
}

/* ------------------------------------------------------------------ *
 * Token 存取
 * ------------------------------------------------------------------ */
export function getToken() {
  try {
    return localStorage.getItem(STORAGE_KEYS.token) || ''
  } catch {
    return ''
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(STORAGE_KEYS.token, token)
    else localStorage.removeItem(STORAGE_KEYS.token)
  } catch {
    /* ignore */
  }
}

export function clearToken() {
  setToken('')
}

/** 供 fetch 流式请求复用的鉴权头 */
export function authHeaders(extra = {}) {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}`, ...extra } : { ...extra }
}

export function apiUrl(path) {
  const base = API_BASE_URL.replace(/\/$/, '')
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${base}${suffix}`
}

/* ------------------------------------------------------------------ *
 * 401 回调：由 router 注入，避免 api 层反向依赖 router 造成循环引用
 * ------------------------------------------------------------------ */
let unauthorizedHandler = null

/**
 * 是否已经就本次「登录失效」提示/跳转过。
 *
 * 页面初始化会并发发出多个请求，token 失效时它们会同时返回 401。
 * 若每个都弹提示、都跳转，用户会看到多条重复弹窗。
 * 登录成功或重新进入应用时由 setUnauthorizedHandler 的调用方重置。
 */
let unauthorizedNotified = false

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

/** 登录成功后调用，允许下一次失效时再次提示 */
export function resetUnauthorizedNotified() {
  unauthorizedNotified = false
}

/* ------------------------------------------------------------------ *
 * 响应体解包
 * 同时兼容两种后端风格：
 *   A. 裸返回        -> { id, name, ... }
 *   B. 统一信封      -> { code: 0, message: 'ok', data: { ... } }
 * ------------------------------------------------------------------ */
function unwrap(body) {
  if (
    body &&
    typeof body === 'object' &&
    !Array.isArray(body) &&
    Object.prototype.hasOwnProperty.call(body, 'code') &&
    Object.prototype.hasOwnProperty.call(body, 'data')
  ) {
    const ok = body.code === 0 || body.code === 200
    if (!ok) {
      throw new ApiError(body.message || body.msg || '请求失败', { code: body.code, payload: body })
    }
    return body.data
  }
  return body
}

/* ------------------------------------------------------------------ *
 * Axios 实例
 * ------------------------------------------------------------------ */
const request = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
})

request.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => {
    if (response.config?.rawResponse) return response
    return unwrap(response.data)
  },
  (error) => {
    if (axios.isCancel(error) || error.code === 'ERR_CANCELED') {
      return Promise.reject(new ApiError('请求已取消', { code: 'CANCELLED' }))
    }

    const status = error.response?.status
    const config = error.config || {}
    let message =
      error.response?.data?.message ||
      error.response?.data?.error ||
      error.message ||
      '网络异常，请稍后重试'

    if (status === 401) {
      clearToken()
      message = '登录状态已失效，请重新登录'
      // 并发请求会同时收到 401，这里只弹一次、只跳转一次，
      // 否则用户会被多条相同提示与重复跳转淹没。
      if (!unauthorizedNotified) {
        unauthorizedNotified = true
        if (typeof unauthorizedHandler === 'function') unauthorizedHandler()
      } else {
        // 已提示过：静默失败，不再弹窗
        const apiError = new ApiError(message, { status, payload: error.response?.data })
        apiError.__notified = true
        return Promise.reject(apiError)
      }
    } else if (status === 403) {
      message = '没有权限执行该操作'
    } else if (status === 404) {
      message = `接口不存在：${config.url || ''}`
    } else if (status === 413) {
      message = '文件过大，已超出服务端限制'
    } else if (status >= 500) {
      message = `服务端异常（HTTP ${status}）`
    } else if (!error.response) {
      message = '无法连接后端服务，请确认 server 已启动'
    }

    const apiError = new ApiError(message, { status, payload: error.response?.data })
    if (!config.silent) {
      ElMessage.error(message)
      // 标记已提示，避免上层 store 再弹一次
      apiError.__notified = true
    }
    return Promise.reject(apiError)
  },
)

export default request
