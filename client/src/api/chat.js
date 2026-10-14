import request, { apiUrl, authHeaders } from './request'
import { fetchEventStream } from '@/utils/sse'
import { isMockMode } from '@/config'
import { mockChat, mockStreamChat } from './mock'

/** 会话相关接口 */
export function listConversations() {
  if (isMockMode) return mockChat.listConversations()
  return request.get('/conversations')
}

export function createConversation(payload = {}) {
  if (isMockMode) return mockChat.createConversation(payload)
  return request.post('/conversations', payload)
}

export function updateConversation(id, payload) {
  if (isMockMode) return mockChat.updateConversation(id, payload)
  return request.patch(`/conversations/${id}`, payload)
}

export function deleteConversation(id) {
  if (isMockMode) return mockChat.deleteConversation(id)
  return request.delete(`/conversations/${id}`)
}

export function listMessages(conversationId) {
  if (isMockMode) return mockChat.listMessages(conversationId)
  return request.get(`/conversations/${conversationId}/messages`)
}

/* ------------------------------------------------------------------ *
 * 生成模型（与向量化模型无关：这里只影响回答由谁生成）
 * ------------------------------------------------------------------ */

/**
 * 可用生成模型清单。后端不会下发密钥，只告知每个模型是否可用。
 * 返回：{ models: [{id,label,model,kind,configured,isDefault}], defaultId, fallbackToModel }
 */
export function listModels() {
  if (isMockMode) return mockListModels()
  return request.get('/chat/models')
}

/** 服务端检索与 RAG 参数（含是否允许无依据回退到模型自身知识） */
export function fetchChatConfig() {
  if (isMockMode) return mockChatConfig()
  return request.get('/chat/config')
}

/* ------------------------------------------------------------------ *
 * 用户自带模型（BYOM）
 *
 * 密钥由用户在前端填写，提交给后端**加密存储**，之后不会再下发回来；
 * 因此编辑时若密钥留空，表示「沿用原密钥」。
 * ------------------------------------------------------------------ */

/** 新增一个模型（本地部署或云端 API） */
export function createModel(payload) {
  if (isMockMode) return mockCreateModel(payload)
  return request.post('/chat/models', payload)
}

/** 修改模型；payload.apiKey 留空表示不修改密钥 */
export function updateModel(id, payload) {
  if (isMockMode) return mockUpdateModel(id, payload)
  return request.patch(`/chat/models/${id}`, payload)
}

export function deleteModel(id) {
  if (isMockMode) return mockDeleteModel(id)
  return request.delete(`/chat/models/${id}`)
}

/** 连通性自检：发一次极小请求，立刻知道模型能不能用 */
export function probeModel(id) {
  if (isMockMode) return Promise.resolve({ ok: true, note: 'Mock 模式无需探测' })
  // 探测可能等待 15 秒（本地服务未启动时要等超时），单独放宽超时
  return request.post(`/chat/models/${id}/probe`, {}, { timeout: 25000, silent: true })
}

function mockCreateModel(payload) {
  return Promise.resolve({
    id: `user:mock_${Date.now()}`,
    label: payload.label,
    model: payload.model,
    kind: payload.isLocal ? 'local' : 'api',
    configured: true,
  })
}

function mockUpdateModel(id, payload) {
  return Promise.resolve({ id, label: payload.label, model: payload.model, configured: true })
}

function mockDeleteModel() {
  return Promise.resolve({ ok: true })
}

/** Mock 模式下的模型清单：与后端结构保持一致，便于两种模式无差别对接 */
function mockListModels() {
  return Promise.resolve({
    models: [
      {
        id: 'default',
        label: '演示模型（Mock）',
        model: 'mock-rag-v1',
        kind: 'api',
        configured: true,
        isDefault: true,
      },
    ],
    defaultId: 'default',
    fallbackToModel: true,
  })
}

function mockChatConfig() {
  return Promise.resolve({
    topK: 5,
    scoreThreshold: 0.2,
    chunkSize: 500,
    chunkOverlap: 50,
    memoryTurns: 6,
    maxUploadSizeMB: 50,
    fallbackToModel: true,
  })
}

/* ------------------------------------------------------------------ *
 * 流式问答
 * ------------------------------------------------------------------ */

/**
 * 把后端可能出现的各种事件风格归一化成前端统一事件：
 *   { type: 'delta',   content }
 *   { type: 'sources', sources: [] }
 *   { type: 'done',    messageId, usage }
 *   { type: 'error',   message }
 *   { type: 'meta' | 'title' | ... }
 */
export function normalizeStreamEvent({ event, data }) {
  if (data === undefined || data === null) return null

  // 兼容 OpenAI 风格： data: {"choices":[{"delta":{"content":"x"}}]}
  const choiceDelta = data?.choices?.[0]?.delta
  if (choiceDelta && typeof choiceDelta.content === 'string') {
    return { type: 'delta', content: choiceDelta.content }
  }

  const type = String(data.type || event || 'message').toLowerCase()

  switch (type) {
    case 'delta':
    case 'message':
    case 'chunk':
    case 'token':
    case 'content': {
      const content = data.content ?? data.delta ?? data.text ?? data.token ?? ''
      return content ? { type: 'delta', content: String(content) } : null
    }
    case 'sources':
    case 'source':
    case 'references':
    case 'reference':
    case 'citations':
      return { type: 'sources', sources: data.sources || data.references || data.citations || [] }
    case 'done':
    case 'end':
    case 'finish':
    case 'finished':
      return { type: 'done', messageId: data.messageId || data.id, usage: data.usage }
    case 'error':
      return { type: 'error', message: data.message || data.error || '生成回答失败' }
    case 'title':
      return { type: 'title', title: data.title }
    case 'meta':
    case 'start':
      return { type: 'meta', ...data }
    default:
      if (typeof data.content === 'string' && data.content) {
        return { type: 'delta', content: data.content }
      }
      return null
  }
}

/**
 * 发起流式问答。
 *
 * @param {object} payload  { conversationId, content, knowledgeBaseIds, topK, scoreThreshold }
 * @param {object} handlers { signal, onEvent, onError }
 */
export async function streamChat(payload, handlers = {}) {
  const { signal, onEvent = () => {} } = handlers

  if (isMockMode) {
    return mockStreamChat(payload, { signal, onEvent })
  }

  return fetchEventStream(apiUrl('/chat/stream'), {
    method: 'POST',
    headers: authHeaders(),
    body: payload,
    signal,
    onEvent: (raw) => {
      const normalized = normalizeStreamEvent(raw)
      if (normalized) onEvent(normalized)
    },
  })
}
