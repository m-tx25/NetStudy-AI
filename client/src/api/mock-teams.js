/**
 * 团队 / 密钥的 Mock 实现（仅 VITE_USE_MOCK=true 时生效）。
 *
 * 真实模式（默认）走后端 /api/teams，功能完整；
 * 这里只做**最小可用**的内存实现，保证无后端时界面不报错、可点通主流程。
 * 数据不持久化，刷新页面即重置。
 */

const state = {
  teams: [
    {
      id: 'team_demo',
      name: '示例团队',
      description: 'Mock 模式下的演示团队',
      visibility: 'public',
      joinPolicy: 'approval',
      inviteCode: 'DEMO2024',
      ownerId: 'user_demo',
      owner: { id: 'user_demo', username: 'demo', nickname: '演示用户', avatar: '' },
      myRole: 'owner',
      memberCount: 1,
      knowledgeBaseCount: 0,
      pendingRequestCount: 0,
      myRequestStatus: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
  ],
  members: {},
  requests: {},
  userKeys: [],
  teamKeys: {},
}

state.members.team_demo = [
  {
    id: 'tm_demo',
    userId: 'user_demo',
    role: 'owner',
    joinedAt: new Date().toISOString(),
    user: { id: 'user_demo', username: 'demo', nickname: '演示用户', avatar: '' },
  },
]

const delay = (value) => new Promise((resolve) => setTimeout(() => resolve(value), 120))

export const mockTeams = {
  listMyTeams: () => delay(state.teams),
  searchTeams: (keyword) =>
    delay(
      state.teams.filter(
        (t) => !keyword || t.name.includes(keyword) || (t.description || '').includes(keyword),
      ),
    ),
  createTeam: (payload) => {
    const team = {
      id: `team_${Date.now()}`,
      name: payload.name,
      description: payload.description || '',
      visibility: payload.visibility || 'public',
      joinPolicy: payload.joinPolicy || 'approval',
      inviteCode: Math.random().toString(36).slice(2, 10).toUpperCase(),
      ownerId: 'user_demo',
      owner: { id: 'user_demo', username: 'demo', nickname: '演示用户', avatar: '' },
      myRole: 'owner',
      memberCount: 1,
      knowledgeBaseCount: 0,
      pendingRequestCount: 0,
      myRequestStatus: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    state.teams.push(team)
    state.members[team.id] = [
      {
        id: `tm_${Date.now()}`,
        userId: 'user_demo',
        role: 'owner',
        joinedAt: new Date().toISOString(),
        user: { id: 'user_demo', username: 'demo', nickname: '演示用户', avatar: '' },
      },
    ]
    return delay(team)
  },
  getTeam: (teamId) => {
    const team = state.teams.find((t) => t.id === teamId)
    return team ? delay(team) : Promise.reject(new Error('团队不存在'))
  },
  updateTeam: (teamId, payload) => {
    const team = state.teams.find((t) => t.id === teamId)
    if (!team) return Promise.reject(new Error('团队不存在'))
    Object.assign(team, payload, { updatedAt: new Date().toISOString() })
    return delay(team)
  },
  deleteTeam: (teamId) => {
    state.teams = state.teams.filter((t) => t.id !== teamId)
    return delay({ ok: true })
  },
  previewByInviteCode: (code) => {
    const team = state.teams.find((t) => t.inviteCode === String(code).toUpperCase())
    return team ? delay(team) : Promise.reject(new Error('邀请码无效'))
  },
  regenerateInviteCode: (teamId) => {
    const team = state.teams.find((t) => t.id === teamId)
    if (!team) return Promise.reject(new Error('团队不存在'))
    team.inviteCode = Math.random().toString(36).slice(2, 10).toUpperCase()
    return delay(team)
  },
  listTeamMembers: (teamId) => delay(state.members[teamId] || []),
  addTeamMember: (teamId, payload) => {
    const member = {
      id: `tm_${Date.now()}`,
      userId: `user_${Date.now()}`,
      role: payload.role || 'member',
      joinedAt: new Date().toISOString(),
      user: {
        id: `user_${Date.now()}`,
        username: payload.username,
        nickname: payload.username,
        avatar: '',
      },
    }
    state.members[teamId] = [...(state.members[teamId] || []), member]
    return delay(member)
  },
  setTeamMemberRole: (teamId, userId, role) => {
    const member = (state.members[teamId] || []).find((m) => m.userId === userId)
    if (member) member.role = role
    return delay(member || {})
  },
  removeTeamMember: (teamId, userId) => {
    state.members[teamId] = (state.members[teamId] || []).filter((m) => m.userId !== userId)
    return delay({ ok: true })
  },
  transferOwnership: (teamId, userId) => {
    const team = state.teams.find((t) => t.id === teamId)
    if (team) team.ownerId = userId
    return delay(team || {})
  },
  joinTeam: () => delay({ ok: true, status: 'pending', message: '申请已提交（Mock）' }),
  joinByInviteCode: () => delay({ ok: true, status: 'pending', message: '申请已提交（Mock）' }),
  listMyJoinRequests: () => delay([]),
  listJoinRequests: (teamId) => delay(state.requests[teamId] || []),
  handleJoinRequest: () => delay({ ok: true }),
  cancelJoinRequest: () => delay({ ok: true }),
}

/* ------------------------------ 密钥 ------------------------------ */
const PROVIDERS = [
  {
    id: 'zhipu',
    label: '智谱 AI（GLM）',
    capabilities: ['embedding', 'chat'],
    defaultBaseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    defaultEmbeddingModel: 'embedding-3',
    defaultChatModel: 'glm-4-flash',
    keyHint: '形如 xxxxxxxx.xxxxxxxx（带一个点），不是 sk- 开头',
    applyUrl: 'https://open.bigmodel.cn/',
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    capabilities: ['chat'],
    defaultBaseUrl: 'https://api.deepseek.com/v1',
    defaultEmbeddingModel: '',
    defaultChatModel: 'deepseek-chat',
    keyHint: '形如 sk-xxxxxxxx',
    applyUrl: 'https://platform.deepseek.com/',
  },
  {
    id: 'openai',
    label: 'OpenAI 兼容',
    capabilities: ['chat', 'embedding'],
    defaultBaseUrl: 'https://api.openai.com/v1',
    defaultEmbeddingModel: 'text-embedding-3-small',
    defaultChatModel: 'gpt-4o-mini',
    keyHint: '形如 sk-xxxxxxxx',
    applyUrl: '',
  },
  {
    id: 'custom',
    label: '自定义（Ollama / vLLM / One-API 等）',
    capabilities: ['chat', 'embedding'],
    defaultBaseUrl: '',
    defaultEmbeddingModel: '',
    defaultChatModel: '',
    keyHint: '本地服务可填任意非空值',
    applyUrl: '',
  },
]

function makeKey(scope, payload) {
  const meta = PROVIDERS.find((p) => p.id === payload.provider) || PROVIDERS[3]
  const secret = payload.secret || ''
  const masked =
    secret.length > 10 ? `${secret.slice(0, 6)}…${secret.slice(-4)}` : '*'.repeat(secret.length)
  return {
    id: `key_${scope}_${Date.now()}`,
    provider: payload.provider,
    providerLabel: meta.label,
    label: payload.label || meta.label,
    masked,
    model: payload.model || '',
    baseUrl: payload.baseUrl || '',
    enabled: payload.enabled !== false,
    capabilities: meta.capabilities,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    isActive: false,
  }
}

export const mockKeys = {
  listProviders: () => delay(PROVIDERS),
  overview: () =>
    delay({
      providers: PROVIDERS,
      userKeys: state.userKeys,
      teamKeys: [],
      effective: { activeSource: 'server', serverConfigured: { zhipu: true, deepseek: true } },
    }),
  teamOverview: (teamId) =>
    delay({
      providers: PROVIDERS,
      userKeys: [],
      teamKeys: state.teamKeys[teamId] || [],
      effective: { activeSource: 'server', serverConfigured: { zhipu: true, deepseek: true } },
    }),
  upsertUserKey: (payload) => {
    const existed = state.userKeys.find((k) => k.provider === payload.provider)
    const key = makeKey('user', payload)
    state.userKeys = existed
      ? state.userKeys.map((k) => (k.provider === payload.provider ? { ...key, id: k.id } : k))
      : [...state.userKeys, key]
    return delay(state.userKeys.find((k) => k.provider === payload.provider))
  },
  upsertTeamKey: (teamId, payload) => {
    const list = state.teamKeys[teamId] || []
    const existed = list.find((k) => k.provider === payload.provider)
    const key = makeKey('team', payload)
    state.teamKeys[teamId] = existed
      ? list.map((k) => (k.provider === payload.provider ? { ...key, id: k.id } : k))
      : [...list, key]
    return delay(state.teamKeys[teamId].find((k) => k.provider === payload.provider))
  },
  updateUserKey: () => delay({ ok: true }),
  updateTeamKey: () => delay({ ok: true }),
  deleteUserKey: (keyId) => {
    state.userKeys = state.userKeys.filter((k) => k.id !== keyId)
    return delay({ ok: true })
  },
  deleteTeamKey: (teamId, keyId) => {
    state.teamKeys[teamId] = (state.teamKeys[teamId] || []).filter((k) => k.id !== keyId)
    return delay({ ok: true })
  },
  listModels: () =>
    delay([
      { id: 'server:default', label: '服务端默认模型', model: 'deepseek-chat', configured: true, source: 'server' },
    ]),
}
