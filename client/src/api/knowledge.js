import request from './request'
import { isMockMode } from '@/config'
import { mockKnowledge } from './mock'

/* ------------------------------------------------------------------ *
 * 知识库
 * ------------------------------------------------------------------ */
export function listKnowledgeBases() {
  if (isMockMode) return mockKnowledge.listKnowledgeBases()
  return request.get('/knowledge-bases')
}

export function createKnowledgeBase(payload) {
  if (isMockMode) return mockKnowledge.createKnowledgeBase(payload)
  return request.post('/knowledge-bases', payload)
}

export function updateKnowledgeBase(id, payload) {
  if (isMockMode) return mockKnowledge.updateKnowledgeBase(id, payload)
  return request.patch(`/knowledge-bases/${id}`, payload)
}

export function deleteKnowledgeBase(id) {
  if (isMockMode) return mockKnowledge.deleteKnowledgeBase(id)
  return request.delete(`/knowledge-bases/${id}`)
}

/* ------------------------------------------------------------------ *
 * 文档
 * ------------------------------------------------------------------ */
export function listDocuments(knowledgeBaseId) {
  if (isMockMode) return mockKnowledge.listDocuments(knowledgeBaseId)
  return request.get('/documents', { params: { knowledgeBaseId } })
}

/**
 * 上传文档（multipart/form-data）。
 * 注意：不要手工设置 Content-Type，交给浏览器/axios 自动补 boundary。
 */
export function uploadDocument(knowledgeBaseId, file, onProgress) {
  if (isMockMode) return mockKnowledge.uploadDocument(knowledgeBaseId, file, onProgress)

  const formData = new FormData()
  formData.append('file', file)
  formData.append('knowledgeBaseId', knowledgeBaseId)

  return request.post('/documents/upload', formData, {
    timeout: 0,
    onUploadProgress: (event) => {
      if (!onProgress) return
      const total = event.total || file.size || 0
      const percent = total ? Math.round((event.loaded / total) * 100) : 0
      onProgress(Math.max(0, Math.min(100, percent)))
    },
  })
}

export function updateDocument(id, payload) {
  if (isMockMode) return mockKnowledge.updateDocument(id, payload)
  return request.patch(`/documents/${id}`, payload)
}

export function deleteDocument(id) {
  if (isMockMode) return mockKnowledge.deleteDocument(id)
  return request.delete(`/documents/${id}`)
}

/** 重新解析 / 重新向量化 */
export function reindexDocument(id) {
  if (isMockMode) return mockKnowledge.reindexDocument(id)
  return request.post(`/documents/${id}/reindex`)
}
