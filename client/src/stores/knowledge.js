import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  listDocuments,
  listKnowledgeBases,
  reindexDocument,
  updateDocument,
  updateKnowledgeBase,
  uploadDocument,
} from '@/api/knowledge'
import { notifyError } from '@/utils/notify'
import { uid } from '@/utils/format'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const bases = ref([])
  const basesLoading = ref(false)
  const activeBaseId = ref(null)
  const documents = ref([])
  const documentsLoading = ref(false)
  /** 上传任务队列：{ id, name, size, progress, status, error } */
  const uploadTasks = ref([])
  const keyword = ref('')

  const activeBase = computed(() => bases.value.find((item) => item.id === activeBaseId.value) || null)

  const filteredDocuments = computed(() => {
    const key = keyword.value.trim().toLowerCase()
    if (!key) return documents.value
    return documents.value.filter((doc) => doc.name.toLowerCase().includes(key))
  })

  const totalChunks = computed(() =>
    documents.value.reduce((sum, doc) => sum + (Number(doc.chunks) || 0), 0),
  )

  const activeUploading = computed(() =>
    uploadTasks.value.some((task) => task.status === 'uploading' || task.status === 'processing'),
  )

  /* ---------------------------------------------------------------- *
   * 知识库
   * ---------------------------------------------------------------- */
  async function loadBases() {
    basesLoading.value = true
    try {
      const list = await listKnowledgeBases()
      bases.value = Array.isArray(list) ? list : []
      if (!activeBaseId.value && bases.value.length) {
        activeBaseId.value = bases.value[0].id
      }
      return bases.value
    } catch (error) {
      notifyError(error, '知识库列表加载失败')
      return []
    } finally {
      basesLoading.value = false
    }
  }

  async function createBase(payload) {
    try {
      const base = await createKnowledgeBase(payload)
      bases.value.unshift(base)
      return base
    } catch (error) {
      notifyError(error, '创建知识库失败')
      return null
    }
  }

  async function renameBase(id, payload) {
    try {
      const base = await updateKnowledgeBase(id, payload)
      const index = bases.value.findIndex((item) => item.id === id)
      if (index >= 0) bases.value[index] = { ...bases.value[index], ...base }
      return base
    } catch (error) {
      notifyError(error, '保存知识库失败')
      return null
    }
  }

  async function removeBase(id) {
    try {
      await deleteKnowledgeBase(id)
      bases.value = bases.value.filter((item) => item.id !== id)
      if (activeBaseId.value === id) {
        activeBaseId.value = bases.value[0]?.id || null
        documents.value = []
      }
      return true
    } catch (error) {
      notifyError(error, '删除知识库失败')
      return false
    }
  }

  async function selectBase(id) {
    if (activeBaseId.value === id) return
    activeBaseId.value = id
    keyword.value = ''
    // 文档加载交给视图层对 activeBaseId 的 watch 处理，避免重复请求
  }

  /* ---------------------------------------------------------------- *
   * 文档
   * ---------------------------------------------------------------- */
  async function loadDocuments(baseId = activeBaseId.value) {
    if (!baseId) {
      documents.value = []
      return []
    }
    documentsLoading.value = true
    try {
      const list = await listDocuments(baseId)
      documents.value = Array.isArray(list) ? list : []
      return documents.value
    } catch (error) {
      notifyError(error, '文档列表加载失败')
      return []
    } finally {
      documentsLoading.value = false
    }
  }

  /**
   * 批量上传。逐个串行上传，便于展示每个文件的进度，
   * 也避免同时打满后端解析资源。
   */
  async function uploadFiles(baseId, files) {
    if (!baseId || !files?.length) return []

    for (const file of files) {
      const task = {
        id: uid('task'),
        name: file.name,
        size: file.size,
        progress: 0,
        status: 'uploading',
        error: '',
      }
      uploadTasks.value.push(task)

      try {
        const document = await uploadDocument(baseId, file, (percent) => {
          task.progress = percent
          if (percent >= 100) task.status = 'processing'
        })
        task.progress = 100
        task.status = 'done'
        documents.value.unshift(document)
      } catch (error) {
        task.status = 'failed'
        task.error = error?.message || '上传失败'
        notifyError(error, `${file.name} 上传失败`)
      }
    }

    // 只保留最近 8 条任务记录，避免面板越堆越长
    uploadTasks.value = uploadTasks.value.slice(-8)
    await loadBases()
    return uploadTasks.value
  }

  function clearFinishedTasks() {
    uploadTasks.value = uploadTasks.value.filter(
      (task) => task.status === 'uploading' || task.status === 'processing',
    )
  }

  async function removeDocument(id) {
    await deleteDocument(id)
    documents.value = documents.value.filter((item) => item.id !== id)
    await loadBases()
  }

  async function toggleDocument(id, enabled) {
    const updated = await updateDocument(id, { enabled })
    const index = documents.value.findIndex((item) => item.id === id)
    if (index >= 0) documents.value[index] = { ...documents.value[index], ...updated }
    return updated
  }

  async function reindex(id) {
    const index = documents.value.findIndex((item) => item.id === id)
    if (index >= 0) documents.value[index] = { ...documents.value[index], status: 'processing' }
    try {
      const updated = await reindexDocument(id)
      if (index >= 0) documents.value[index] = { ...documents.value[index], ...updated }
      return updated
    } catch (error) {
      if (index >= 0) documents.value[index] = { ...documents.value[index], status: 'failed' }
      notifyError(error, '重新索引失败')
      return null
    }
  }

  function reset() {
    bases.value = []
    documents.value = []
    uploadTasks.value = []
    activeBaseId.value = null
    keyword.value = ''
  }

  return {
    bases,
    basesLoading,
    activeBaseId,
    activeBase,
    documents,
    documentsLoading,
    filteredDocuments,
    totalChunks,
    uploadTasks,
    activeUploading,
    keyword,
    loadBases,
    createBase,
    renameBase,
    removeBase,
    selectBase,
    loadDocuments,
    uploadFiles,
    clearFinishedTasks,
    removeDocument,
    toggleDocument,
    reindex,
    reset,
  }
})
