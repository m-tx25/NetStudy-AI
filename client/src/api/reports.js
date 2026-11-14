import request from './request'

/** 学术成果生成与导出（模块八）接口 */

export function createReport(payload) {
  return request.post('/reports', payload)
}

export function listReports() {
  return request.get('/reports')
}

export function getReport(id) {
  return request.get(`/reports/${id}`)
}

export function rerunReport(id) {
  return request.post(`/reports/${id}/rerun`)
}

export function deleteReport(id) {
  return request.delete(`/reports/${id}`)
}

/** 下载导出文件：format = md | docx */
export function downloadExport(id, format) {
  return request.get(`/reports/${id}/export`, {
    params: { format },
    responseType: 'blob',
    rawResponse: true,
  })
}

/** 取打印用 HTML（PDF 由浏览器「另存为 PDF」生成） */
export function fetchPrintHtml(id) {
  return request.get(`/reports/${id}/export`, {
    params: { format: 'html' },
    responseType: 'text',
    rawResponse: true,
  })
}
