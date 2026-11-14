import request from './request'

/** 文献库列表（支持状态/标签/分类/关键词筛选） */
export function fetchLibrary(params, config = {}) {
  return request.get('/library/items', { params, ...config })
}

/** 收藏一篇外部检索到的论文 */
export function addLibraryItem(paper, config = {}) {
  return request.post('/library/items', { paper }, config)
}

/** 更新文献条目（状态/进度/分类/标签/笔记） */
export function updateLibraryItem(id, payload, config = {}) {
  return request.patch(`/library/items/${id}`, payload, config)
}

/** 移出文献库 */
export function deleteLibraryItem(id, config = {}) {
  return request.delete(`/library/items/${id}`, config)
}

/** 上传本地 PDF/Word 到文献库 */
export function uploadLibraryFile(file, extra = {}, config = {}) {
  const form = new FormData()
  form.append('file', file)
  if (extra.title) form.append('title', extra.title)
  if (extra.collectionId) form.append('collectionId', extra.collectionId)
  return request.post('/library/items/upload', form, config)
}

export function fetchCollections(config = {}) {
  return request.get('/library/collections', config)
}

export function createCollection(payload, config = {}) {
  return request.post('/library/collections', payload, config)
}

export function deleteCollection(id, config = {}) {
  return request.delete(`/library/collections/${id}`, config)
}

export function fetchTags(config = {}) {
  return request.get('/library/tags', config)
}

export function createTag(payload, config = {}) {
  return request.post('/library/tags', payload, config)
}

export function deleteTag(id, config = {}) {
  return request.delete(`/library/tags/${id}`, config)
}

export function fetchNotes(itemId, config = {}) {
  return request.get(`/library/items/${itemId}/notes`, config)
}

export function addNote(itemId, payload, config = {}) {
  return request.post(`/library/items/${itemId}/notes`, payload, config)
}

export function deleteNote(noteId, config = {}) {
  return request.delete(`/library/notes/${noteId}`, config)
}

export function exportCitation(itemId, format) {
  return request.get(`/library/items/${itemId}/citation`, { params: { format }, silent: true })
}
