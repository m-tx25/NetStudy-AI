import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  addTeamMember,
  cancelJoinRequest,
  createTeam,
  deleteTeam,
  getTeam,
  handleJoinRequest,
  joinByInviteCode,
  joinTeam,
  listJoinRequests,
  listMyJoinRequests,
  listMyTeams,
  listTeamMembers,
  previewByInviteCode,
  regenerateInviteCode,
  removeTeamMember,
  searchTeams,
  setTeamMemberRole,
  transferOwnership,
  updateTeam,
} from '@/api/teams'
import { notifyError, notifySuccess } from '@/utils/notify'

/**
 * 团队状态。
 *
 * 权限判定集中在 isOwner / isAdmin 两个 computed，界面据此决定显示哪些操作，
 * 但**真正的权限校验在后端**（前端只做展示层优化，不承担安全职责）。
 */
export const useTeamStore = defineStore('team', () => {
  const teams = ref([])
  const teamsLoading = ref(false)

  const activeTeamId = ref(null)
  const activeTeam = ref(null)
  const teamLoading = ref(false)

  const members = ref([])
  const membersLoading = ref(false)

  /** 待审批申请（仅 owner/admin 能拉到） */
  const joinRequests = ref([])
  const requestsLoading = ref(false)

  /** 我提交的入队申请（含历史） */
  const myRequests = ref([])

  /** 搜索可加入的团队 */
  const searchResults = ref([])
  const searching = ref(false)

  /** 邀请码预览到的团队（加入前） */
  const invitePreview = ref(null)

  const myRole = computed(() => activeTeam.value?.myRole || null)
  const isOwner = computed(() => myRole.value === 'owner')
  const isAdmin = computed(() => myRole.value === 'owner' || myRole.value === 'admin')
  const isMember = computed(() => Boolean(myRole.value))
  const pendingCount = computed(() => activeTeam.value?.pendingRequestCount || 0)

  /* ---------------------------------------------------------------- *
   * 团队列表
   * ---------------------------------------------------------------- */
  async function loadTeams() {
    teamsLoading.value = true
    try {
      const list = await listMyTeams()
      teams.value = Array.isArray(list) ? list : []
      return teams.value
    } catch (error) {
      notifyError(error, '团队列表加载失败')
      return []
    } finally {
      teamsLoading.value = false
    }
  }

  async function create(payload) {
    try {
      const team = await createTeam(payload)
      teams.value.unshift(team)
      return team
    } catch (error) {
      notifyError(error, '创建团队失败')
      return null
    }
  }

  async function update(id, payload) {
    try {
      const team = await updateTeam(id, payload)
      const index = teams.value.findIndex((item) => item.id === id)
      if (index >= 0) teams.value[index] = { ...teams.value[index], ...team }
      if (activeTeamId.value === id) activeTeam.value = { ...activeTeam.value, ...team }
      return team
    } catch (error) {
      notifyError(error, '保存团队信息失败')
      return null
    }
  }

  async function remove(id) {
    try {
      await deleteTeam(id)
      teams.value = teams.value.filter((item) => item.id !== id)
      if (activeTeamId.value === id) reset()
      return true
    } catch (error) {
      notifyError(error, '解散团队失败')
      return false
    }
  }

  /* ---------------------------------------------------------------- *
   * 团队详情
   * ---------------------------------------------------------------- */
  async function loadTeam(teamId) {
    teamLoading.value = true
    try {
      const team = await getTeam(teamId)
      activeTeam.value = team
      activeTeamId.value = teamId
      return team
    } catch (error) {
      notifyError(error, '团队详情加载失败')
      activeTeam.value = null
      return null
    } finally {
      teamLoading.value = false
    }
  }

  async function selectTeam(teamId) {
    activeTeamId.value = teamId
    await Promise.all([loadTeam(teamId), loadMembers(teamId)])
    if (isAdmin.value) await loadJoinRequests(teamId)
  }

  /* ---------------------------------------------------------------- *
   * 成员
   * ---------------------------------------------------------------- */
  async function loadMembers(teamId) {
    membersLoading.value = true
    try {
      const list = await listTeamMembers(teamId)
      members.value = Array.isArray(list) ? list : []
      return members.value
    } catch (error) {
      notifyError(error, '成员列表加载失败')
      members.value = []
      return []
    } finally {
      membersLoading.value = false
    }
  }

  /** 管理员直接拉人（免审批） */
  async function addMember(teamId, payload) {
    try {
      const member = await addTeamMember(teamId, payload)
      members.value.push(member)
      if (activeTeam.value) {
        activeTeam.value.memberCount = members.value.length
      }
      notifySuccess('已添加成员')
      return member
    } catch (error) {
      notifyError(error, '添加成员失败')
      return null
    }
  }

  async function changeRole(teamId, userId, role) {
    try {
      const updated = await setTeamMemberRole(teamId, userId, role)
      const index = members.value.findIndex((item) => item.userId === userId)
      if (index >= 0) members.value[index] = { ...members.value[index], ...updated }
      notifySuccess(role === 'admin' ? '已设为管理员' : '已取消管理员')
      return updated
    } catch (error) {
      notifyError(error, '修改角色失败')
      return null
    }
  }

  async function removeMember(teamId, userId) {
    try {
      await removeTeamMember(teamId, userId)
      members.value = members.value.filter((item) => item.userId !== userId)
      if (activeTeam.value) {
        activeTeam.value.memberCount = members.value.length
      }
      return true
    } catch (error) {
      notifyError(error, '移除成员失败')
      return false
    }
  }

  /** 退出团队（负责人需先转让，后端会拒绝） */
  async function leaveTeam(teamId, userId) {
    const ok = await removeMember(teamId, userId)
    if (ok) {
      teams.value = teams.value.filter((item) => item.id !== teamId)
      if (activeTeamId.value === teamId) reset()
      notifySuccess('已退出团队')
    }
    return ok
  }

  async function transfer(teamId, userId) {
    try {
      const team = await transferOwnership(teamId, userId)
      activeTeam.value = team
      await loadMembers(teamId)
      notifySuccess('已转让负责人')
      return team
    } catch (error) {
      notifyError(error, '转让失败')
      return null
    }
  }

  /* ---------------------------------------------------------------- *
   * 入队与审核
   * ---------------------------------------------------------------- */
  async function searchTeamsByKeyword(keyword) {
    searching.value = true
    try {
      const list = await searchTeams(keyword)
      searchResults.value = Array.isArray(list) ? list : []
      return searchResults.value
    } catch (error) {
      notifyError(error, '搜索团队失败')
      searchResults.value = []
      return []
    } finally {
      searching.value = false
    }
  }

  /** 申请加入（搜索入口）；open 策略会直接加入 */
  async function applyJoin(teamId, message = '') {
    try {
      const result = await joinTeam(teamId, message)
      notifySuccess(result?.message || '申请已提交')
      await refreshAfterJoin(teamId)
      return result
    } catch (error) {
      notifyError(error, '申请加入失败')
      return null
    }
  }

  /** 用邀请码加入 */
  async function applyByInviteCode(inviteCode, message = '') {
    try {
      const result = await joinByInviteCode(inviteCode, message)
      notifySuccess(result?.message || '申请已提交')
      await loadTeams()
      return result
    } catch (error) {
      notifyError(error, '邀请码无效或加入失败')
      return null
    }
  }

  async function previewInvite(inviteCode) {
    try {
      invitePreview.value = await previewByInviteCode(inviteCode)
      return invitePreview.value
    } catch (error) {
      invitePreview.value = null
      notifyError(error, '邀请码无效')
      return null
    }
  }

  /** 加入/申请后刷新本地状态（列表与搜索结果里的角色会变） */
  async function refreshAfterJoin(teamId) {
    await loadTeams()
    const inList = teams.value.some((item) => item.id === teamId)
    if (inList) await loadTeam(teamId)
    if (searchResults.value.length) {
      await searchTeamsByKeyword('')
    }
    await loadMyRequests()
  }

  async function loadJoinRequests(teamId, status = 'pending') {
    requestsLoading.value = true
    try {
      const list = await listJoinRequests(teamId, status)
      joinRequests.value = Array.isArray(list) ? list : []
      return joinRequests.value
    } catch (error) {
      // 普通成员会 403：这是预期情况，不弹错误提示
      joinRequests.value = []
      return []
    } finally {
      requestsLoading.value = false
    }
  }

  async function approveRequest(teamId, requestId, role = 'member') {
    try {
      await handleJoinRequest(teamId, requestId, true, role)
      joinRequests.value = joinRequests.value.filter((item) => item.id !== requestId)
      await loadMembers(teamId)
      if (activeTeam.value) {
        activeTeam.value.pendingRequestCount = Math.max(0, pendingCount.value - 1)
        activeTeam.value.memberCount = members.value.length
      }
      notifySuccess('已同意加入')
      return true
    } catch (error) {
      notifyError(error, '审批失败')
      return false
    }
  }

  async function rejectRequest(teamId, requestId) {
    try {
      await handleJoinRequest(teamId, requestId, false)
      joinRequests.value = joinRequests.value.filter((item) => item.id !== requestId)
      if (activeTeam.value) {
        activeTeam.value.pendingRequestCount = Math.max(0, pendingCount.value - 1)
      }
      notifySuccess('已拒绝申请')
      return true
    } catch (error) {
      notifyError(error, '审批失败')
      return false
    }
  }

  async function loadMyRequests() {
    try {
      const list = await listMyJoinRequests()
      myRequests.value = Array.isArray(list) ? list : []
      return myRequests.value
    } catch {
      myRequests.value = []
      return []
    }
  }

  async function cancelMyRequest(teamId, requestId) {
    try {
      await cancelJoinRequest(teamId, requestId)
      myRequests.value = myRequests.value.filter((item) => item.id !== requestId)
      notifySuccess('已撤回申请')
      return true
    } catch (error) {
      notifyError(error, '撤回失败')
      return false
    }
  }

  async function resetInviteCode(teamId) {
    try {
      const team = await regenerateInviteCode(teamId)
      if (activeTeam.value) activeTeam.value = { ...activeTeam.value, ...team }
      notifySuccess('邀请码已重置')
      return team
    } catch (error) {
      notifyError(error, '重置邀请码失败')
      return null
    }
  }

  function reset() {
    activeTeamId.value = null
    activeTeam.value = null
    members.value = []
    joinRequests.value = []
  }

  function resetAll() {
    reset()
    teams.value = []
    searchResults.value = []
    myRequests.value = []
    invitePreview.value = null
  }

  return {
    teams,
    teamsLoading,
    activeTeamId,
    activeTeam,
    teamLoading,
    members,
    membersLoading,
    joinRequests,
    requestsLoading,
    myRequests,
    searchResults,
    searching,
    invitePreview,
    myRole,
    isOwner,
    isAdmin,
    isMember,
    pendingCount,
    loadTeams,
    create,
    update,
    remove,
    loadTeam,
    selectTeam,
    loadMembers,
    addMember,
    changeRole,
    removeMember,
    leaveTeam,
    transfer,
    searchTeamsByKeyword,
    applyJoin,
    applyByInviteCode,
    previewInvite,
    loadJoinRequests,
    approveRequest,
    rejectRequest,
    loadMyRequests,
    cancelMyRequest,
    resetInviteCode,
    reset,
    resetAll,
  }
})
