import request from './request'

/** 读取一篇文档的结构解析结果（章节/元数据/参考文献/表格/质量） */
export function fetchPaperStructure(documentId, config = {}) {
  return request.get(`/papers/${documentId}/structure`, { silent: true, ...config })
}

/** 触发重新解析（复用文档接口） */
export function reindexPaper(documentId) {
  return request.post(`/documents/${documentId}/reindex`)
}

/** 可用的分析维度（9 类） */
export function fetchAnalysisKinds(config = {}) {
  return request.get('/papers/kinds', { silent: true, ...config })
}

/** 已生成的分析（用于标记「已有」） */
export function fetchAnalyses(documentId, config = {}) {
  return request.get(`/papers/${documentId}/analyses`, { silent: true, ...config })
}

/** 已缓存的分析内容 */
export function fetchAnalysis(documentId, kind, config = {}) {
  return request.get(`/papers/${documentId}/analysis/${kind}`, { silent: true, ...config })
}
