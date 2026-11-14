import request from './request'

/** 学术研究辅助（模块七）接口 */

export function createBrief(payload) {
  return request.post('/research/briefs', payload)
}

export function listBriefs() {
  return request.get('/research/briefs')
}

export function getBrief(id) {
  return request.get(`/research/briefs/${id}`)
}

export function rerunBrief(id) {
  return request.post(`/research/briefs/${id}/rerun`)
}

export function deleteBrief(id) {
  return request.delete(`/research/briefs/${id}`)
}

export function downloadReport(id) {
  return request.get(`/research/briefs/${id}/report.md`, {
    responseType: 'blob',
    rawResponse: true,
  })
}
