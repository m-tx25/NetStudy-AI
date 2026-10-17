import { ElMessage } from 'element-plus'

/**
 * 统一的错误提示。
 *
 * axios 拦截器已经弹过的错误会带上 __notified 标记（见 api/request.js），
 * 这里直接跳过，避免同一条错误弹两次。
 * Mock 层抛出的原生 Error 没有标记，会在这里补弹一次。
 */
export function notifyError(error, fallback = '操作失败，请稍后重试') {
  if (!error) {
    ElMessage.error(fallback)
    return
  }
  if (error.__notified || error.code === 'CANCELLED') return
  ElMessage.error(error.message || fallback)
  error.__notified = true
}

export function notifySuccess(message) {
  if (message) ElMessage.success(message)
}
