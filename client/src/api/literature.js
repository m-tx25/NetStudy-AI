import request from './request'

/** 聚合检索外部学术论文 */
export function searchLiterature(params, config = {}) {
  return request.get('/literature/search', { params, ...config })
}

/** 可用数据源列表 */
export function fetchSources(config = {}) {
  return request.get('/literature/sources', config)
}

/** 按「数据源 + 内部 id」取单篇详情 */
export function fetchPaper(source, id, config = {}) {
  return request.get('/literature/paper', { params: { source, id }, ...config })
}

/** 按 DOI 精确取单篇 */
export function fetchPaperByDoi(doi, config = {}) {
  return request.get('/literature/doi', { params: { doi }, ...config })
}

/** 相关论文推荐 */
export function fetchRelated(source, id, limit = 8, config = {}) {
  return request.get('/literature/related', { params: { source, id, limit }, ...config })
}
