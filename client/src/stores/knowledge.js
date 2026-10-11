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
    // 切走时停止针对旧知识库的轮询，新知识库的轮询由 loadDocuments 触发
    stopPolling()
    activeBaseId.value = id
    keyword.value = ''
    // 文档加载交给视图层对 activeBaseId 的 watch 处理，避免重复请求
  }

  /* ---------------------------------------------------------------- *
   * 文档
   * ---------------------------------------------------------------- */
  /**
   * 拉取文档列表的内部实现：失败时向上抛出，供轮询判断是否需要放弃。
   * 对外请使用 loadDocuments（保持不抛错的既有语义）。
   */
  async function fetchDocuments(baseId) {
    documentsLoading.value = true
    try {
      const list = await listDocuments(baseId)
      // 竞态保护：请求期间用户可能已经切走，此时丢弃这次结果
      if (baseId !== activeBaseId.value) return documents.value
      documents.value = Array.isArray(list) ? list : []
      return documents.value
    } finally {
      documentsLoading.value = false
    }
  }

  /**
   * 加载文档列表（对外接口，失败时不抛错，只提示）。
   * @param {string} [baseId] 知识库 id，默认当前选中的
   */
  async function loadDocuments(baseId = activeBaseId.value) {
    if (!baseId) {
      documents.value = []
      return []
    }
    try {
      const list = await fetchDocuments(baseId)
      // 进入页面或切换知识库时，若已有未就绪文档（例如上次上传后离开），继续轮询
      if (hasPendingDocuments()) startPolling(baseId)
      return list
    } catch (error) {
      notifyError(error, '文档列表加载失败')
      return []
    }
  }

  /* ---------------------------------------------------------------- *
   * 文档解析状态轮询
   *
   * 背景：后端在异步队列模式下，上传接口只返回 status='processing'，
   * 真正的解析与向量化由 Celery worker 在后台完成。而前端拿到响应后
   * 不再查询，导致列表永远停在「解析中」（「重新索引」按钮也因此被禁用），
   * 必须手动刷新页面才能看到真实状态。
   *
   * 这里补一个轮询：只要列表里还有未就绪的文档，就周期性地重新拉取，
   * 直到全部落到终态（ready / failed）或超时。
   * ---------------------------------------------------------------- */
  const POLL_INTERVAL = 3000 // 轮询间隔
  const POLL_TIMEOUT = 5 * 60 * 1000 // 最长轮询时长，避免异常文档导致无限请求
  const POLL_MAX_ERRORS = 3 // 连续失败多少次后放弃

  const polling = ref(false)
  let pollTimer = null
  let pollStartedAt = 0
  let pollErrorCount = 0

  /** 是否还有文档处于「处理中」（pending / processing） */
  function hasPendingDocuments() {
    return documents.value.some(
      (doc) => doc.status === 'pending' || doc.status === 'processing',
    )
  }

  function stopPolling() {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
    polling.value = false
    pollStartedAt = 0
    pollErrorCount = 0
  }

  /**
   * 启动轮询。已在轮询中或没有待处理文档时不重复启动。
   * @param {string} [baseId] 要监控的知识库；默认当前选中的
   */
  function startPolling(baseId = activeBaseId.value) {
    if (!baseId) return
    if (!hasPendingDocuments()) return

    // 已在轮询同一个知识库，无需重启
    if (pollTimer !== null && baseId === activeBaseId.value) return

    stopPolling()
    pollStartedAt = Date.now()
    polling.value = true

    const tick = async () => {
      pollTimer = null

      // 用户切走了知识库：停止轮询，改由视图层的 watch 重新触发
      if (baseId !== activeBaseId.value) {
        stopPolling()
        return
      }
      // 超时保护
      if (Date.now() - pollStartedAt > POLL_TIMEOUT) {
        stopPolling()
        return
      }
      // 没有待处理文档了：正常结束
      if (!hasPendingDocuments()) {
        stopPolling()
        return
      }

      try {
        // 用会抛错的内部实现，才能感知连续失败并放弃
        await fetchDocuments(baseId)
        pollErrorCount = 0
      } catch {
        pollErrorCount += 1
        if (pollErrorCount >= POLL_MAX_ERRORS) {
          stopPolling()
          return
        }
      }

      // 状态可能刚刚全部就绪，再判断一次
      if (!hasPendingDocuments() || Date.now() - pollStartedAt > POLL_TIMEOUT) {
        stopPolling()
        return
      }
      pollTimer = setTimeout(tick, POLL_INTERVAL)
    }

    pollTimer = setTimeout(tick, POLL_INTERVAL)
  }

  /**
   * 批量上传。逐个串行上传，便于展示每个文件的进度，
   * 也避免同时打满后端解析资源。
   */
  async function uploadFiles(baseId, files) {
    if (!baseId || !files?.length) return []

    let serverParsing = false // 后端是否把解析留到了后台

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
        task.error = document?.error || ''
        documents.value.unshift(document)
        // 同步模式（CELERY_TASK_ALWAYS_EAGER）下返回时已是 ready，无需轮询
        if (document?.status === 'pending' || document?.status === 'processing') {
          serverParsing = true
        }
      } catch (error) {
        task.status = 'failed'
        task.error = error?.message || '上传失败'
        notifyError(error, `${file.name} 上传失败`)
      }
    }

    // 只保留最近 8 条任务记录，避免面板越堆越长
    uploadTasks.value = uploadTasks.value.slice(-8)
    await loadBases()
    // 后台在解析：开启轮询，等状态落地后自动停止
    if (serverParsing) startPolling(baseId)
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
      // 重新索引同样是异步的：返回 processing 时开启轮询等待落地
      if (updated?.status === 'pending' || updated?.status === 'processing') {
        startPolling()
      }
      return updated
    } catch (error) {
      if (index >= 0) documents.value[index] = { ...documents.value[index], status: 'failed' }
      notifyError(error, '重新索引失败')
      return null
    }
  }

  function reset() {
    stopPolling()
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
    /** 是否正在轮询文档解析状态，可用于界面提示 */
    polling,
    startPolling,
    stopPolling,
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
