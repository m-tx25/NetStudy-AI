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
