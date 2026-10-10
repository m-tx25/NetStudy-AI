import request from './request'
import { isMockMode } from '@/config'
import { mockAuth } from './mock'

/** 登录 */
export function login(payload) {
  if (isMockMode) return mockAuth.login(payload)
  return request.post('/auth/login', payload)
}

/** 注册 */
export function register(payload) {
  if (isMockMode) return mockAuth.register(payload)
  return request.post('/auth/register', payload)
}

/** 获取当前登录用户信息 */
export function fetchProfile(options = {}) {
  if (isMockMode) return mockAuth.profile()
  return request.get('/auth/me', options)
}

/** 退出登录 */
export function logout() {
  if (isMockMode) return mockAuth.logout()
  return request.post('/auth/logout', {}, { silent: true })
}

/**
 * 修改账号资料（用户名 / 昵称 / 邮箱 / 头像）。
 * 只需传要修改的字段，返回更新后的完整用户对象。
 */
export function updateProfile(payload) {
  if (isMockMode) return mockAuth.updateProfile(payload)
  return request.patch('/auth/profile', payload)
}

/**
 * 修改密码。
 * 服务端应校验 currentPassword，并在成功后让其他已签发的 Token 失效。
 */
export function changePassword(payload) {
  if (isMockMode) return mockAuth.changePassword(payload)
  return request.put('/auth/password', payload)
}

/** 忘记密码：发送重置邮件 */
export function forgotPassword(payload) {
  if (isMockMode) return mockAuth.forgotPassword(payload)
  return request.post('/auth/forgot-password', payload)
}
