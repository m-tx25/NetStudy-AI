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

/** 导出 md / docx */
export function downloadExport(id, format) {
  return request.get(`/research/briefs/${id}/export`, {
    params: { format },
    responseType: 'blob',
    rawResponse: true,
  })
}

/** 取打印用 HTML（PDF 由浏览器「另存为 PDF」生成） */
export function fetchPrintHtml(id) {
  return request.get(`/research/briefs/${id}/export`, {
    params: { format: 'html' },
    responseType: 'text',
    rawResponse: true,
  })
}
