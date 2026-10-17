import request from './request'
import { isMockMode } from '@/config'
import { mockTeams } from './mock-teams'

/**
 * 团队（类群组）接口。
 *
 * 角色：owner（负责人）/ admin（管理员）/ member（成员）
 * 入队方式：
 *   1) 邀请码    joinByInviteCode()  —— open 策略直接进，approval 待审核
 *   2) 搜索申请  joinTeam()          —— 待 owner/admin 审批
 *   3) 管理员拉人 addTeamMember()     —— 免审批
 *
 * 说明：Mock 模式下后端不存在，团队相关能力仅做最小占位，
 * 便于无后端时界面不报错；接真实后端（VITE_USE_MOCK=false）才是完整功能。
 */

/* ------------------------------ 团队 ------------------------------ */
export function listMyTeams() {
  if (isMockMode) return mockTeams.listMyTeams()
  return request.get('/teams')
}

export function searchTeams(keyword, limit = 20) {
  if (isMockMode) return mockTeams.searchTeams(keyword)
  return request.get('/teams/search', { params: { q: keyword, limit } })
}

export function createTeam(payload) {
  if (isMockMode) return mockTeams.createTeam(payload)
  return request.post('/teams', payload)
}

export function getTeam(teamId) {
  if (isMockMode) return mockTeams.getTeam(teamId)
  return request.get(`/teams/${teamId}`)
}

export function updateTeam(teamId, payload) {
  if (isMockMode) return mockTeams.updateTeam(teamId, payload)
  return request.patch(`/teams/${teamId}`, payload)
}

/** 解散团队（仅负责人） */
export function deleteTeam(teamId) {
  if (isMockMode) return mockTeams.deleteTeam(teamId)
  return request.delete(`/teams/${teamId}`)
}

/** 用邀请码查看团队（加入前预览） */
export function previewByInviteCode(inviteCode) {
  if (isMockMode) return mockTeams.previewByInviteCode(inviteCode)
  return request.get(`/teams/invite/${encodeURIComponent(inviteCode)}`)
}

/** 重置邀请码（旧码立即失效，仅管理员以上） */
export function regenerateInviteCode(teamId) {
  if (isMockMode) return mockTeams.regenerateInviteCode(teamId)
  return request.post(`/teams/${teamId}/invite-code`)
}

/* ------------------------------ 成员 ------------------------------ */
export function listTeamMembers(teamId) {
  if (isMockMode) return mockTeams.listTeamMembers(teamId)
  return request.get(`/teams/${teamId}/members`)
}

/** 管理员直接拉人（免审批） */
export function addTeamMember(teamId, payload) {
  if (isMockMode) return mockTeams.addTeamMember(teamId, payload)
  return request.post(`/teams/${teamId}/members`, payload)
}

/** 设置成员角色（admin / member；owner 需用 transferOwnership） */
export function setTeamMemberRole(teamId, userId, role) {
  if (isMockMode) return mockTeams.setTeamMemberRole(teamId, userId, role)
  return request.patch(`/teams/${teamId}/members/${userId}`, { role })
}

/** 移除成员；移除自己即退队（负责人需先转让） */
export function removeTeamMember(teamId, userId) {
  if (isMockMode) return mockTeams.removeTeamMember(teamId, userId)
  return request.delete(`/teams/${teamId}/members/${userId}`)
}

/** 转让负责人 */
export function transferOwnership(teamId, userId) {
  if (isMockMode) return mockTeams.transferOwnership(teamId, userId)
  return request.post(`/teams/${teamId}/transfer`, { userId })
}

/* --------------------------- 入队与审核 --------------------------- */
export function joinTeam(teamId, message = '') {
  if (isMockMode) return mockTeams.joinTeam(teamId, message)
  return request.post(`/teams/${teamId}/join`, { message })
}

export function joinByInviteCode(inviteCode, message = '') {
  if (isMockMode) return mockTeams.joinByInviteCode(inviteCode, message)
  return request.post('/teams/join-by-code', { inviteCode, message })
}

/** 我提交的入队申请（含历史） */
export function listMyJoinRequests() {
  if (isMockMode) return mockTeams.listMyJoinRequests()
  return request.get('/teams/join-requests/mine')
}

/** 待审批申请列表（仅 owner/admin） */
export function listJoinRequests(teamId, status = 'pending') {
  if (isMockMode) return mockTeams.listJoinRequests(teamId, status)
  return request.get(`/teams/${teamId}/join-requests`, { params: { status_filter: status } })
}

/** 审批入队申请 */
export function handleJoinRequest(teamId, requestId, approve, role = 'member') {
  if (isMockMode) return mockTeams.handleJoinRequest(teamId, requestId, approve, role)
  return request.post(`/teams/${teamId}/join-requests/${requestId}`, { approve, role })
}

/** 撤回自己的申请 */
export function cancelJoinRequest(teamId, requestId) {
  if (isMockMode) return mockTeams.cancelJoinRequest(teamId, requestId)
  return request.delete(`/teams/${teamId}/join-requests/${requestId}`)
}
