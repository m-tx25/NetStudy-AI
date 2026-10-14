import request from './request'
import { isMockMode } from '@/config'
import { mockKeys } from './mock-teams'

/**
 * API 密钥接口（个人级 + 团队级）。
 *
 * 安全约定：
 *   - 密钥由后端加密落库，接口**只返回掩码**（如 sk-abc…f123），前端拿不到明文；
 *   - 更新时 `secret` 留空表示「不改密钥，只改其它字段」；
 *   - 团队密钥仅 owner/admin 可读写，普通成员请求会 403。
 *
 * 作用域与生效规则：
 *   - 个人密钥对自己的**个人知识库**生效；
 *   - 团队密钥对**团队知识库**生效（费用归团队）；
 *   - 都没配时回落到服务端 .env 的全局 Key。
 */

/* --------------------------- 个人密钥 --------------------------- */
export function listProviders() {
  if (isMockMode) return mockKeys.listProviders()
  return request.get('/keys/providers')
}

/** 个人密钥总览：供应商清单 + 我的密钥 + 当前生效情况 */
export function getKeyOverview() {
  if (isMockMode) return mockKeys.overview()
  return request.get('/keys')
}

/** 新增或覆盖个人密钥（同一 provider 只保留一条） */
export function saveUserKey(payload) {
  if (isMockMode) return mockKeys.upsertUserKey(payload)
  return request.post('/keys', payload)
}

export function updateUserKey(keyId, payload) {
  if (isMockMode) return mockKeys.updateUserKey(keyId, payload)
  return request.patch(`/keys/${keyId}`, payload)
}

export function deleteUserKey(keyId) {
  if (isMockMode) return mockKeys.deleteUserKey(keyId)
  return request.delete(`/keys/${keyId}`)
}

/* --------------------------- 团队密钥 --------------------------- */
export function getTeamKeyOverview(teamId) {
  if (isMockMode) return mockKeys.teamOverview(teamId)
  return request.get(`/teams/${teamId}/keys`)
}

export function saveTeamKey(teamId, payload) {
  if (isMockMode) return mockKeys.upsertTeamKey(teamId, payload)
  return request.post(`/teams/${teamId}/keys`, payload)
}

export function updateTeamKey(teamId, keyId, payload) {
  if (isMockMode) return mockKeys.updateTeamKey(teamId, keyId, payload)
  return request.patch(`/teams/${teamId}/keys/${keyId}`, payload)
}

export function deleteTeamKey(teamId, keyId) {
  if (isMockMode) return mockKeys.deleteTeamKey(teamId, keyId)
  return request.delete(`/teams/${teamId}/keys/${keyId}`)
}

/* --------------------------- 可用模型 --------------------------- */
/**
 * 可用于「生成」的模型清单：服务端 .env 配置的 + 用户/团队自配密钥。
 * 传给 teamId 时会把该团队的密钥也算进可选项。
 */
export function listAvailableModels(teamId) {
  if (isMockMode) return mockKeys.listModels()
  return request.get('/keys/models', { params: teamId ? { team_id: teamId } : {} })
}
