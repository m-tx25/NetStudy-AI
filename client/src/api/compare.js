import request from './request'

/**
 * 多篇论文对比相关接口。
 *
 * 对比是**后台任务**：create 只返回记录（status=pending），
 * 真正分析在服务端跑，前端拿 id 轮询 getComparison 直到 ready/failed。
 */

export function createComparison(payload) {
  return request.post('/comparisons', payload)
}

export function listComparisons() {
  return request.get('/comparisons')
}

export function getComparison(id) {
  return request.get(`/comparisons/${id}`)
}

export function rerunComparison(id) {
  return request.post(`/comparisons/${id}/rerun`)
}

export function deleteComparison(id) {
  return request.delete(`/comparisons/${id}`)
}

/** 下载 Markdown 报告（blob，交给页面触发保存） */
export function downloadReport(id) {
  return request.get(`/comparisons/${id}/report.md`, {
    responseType: 'blob',
    rawResponse: true,
  })
}

export function getPaperProfile(documentId) {
  return request.get(`/papers/${documentId}`)
}

export function refreshPaperProfile(documentId) {
  return request.post(`/papers/${documentId}/refresh`)
}
