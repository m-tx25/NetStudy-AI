import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createConversation,
  createModel,
  deleteConversation,
  deleteModel,
  fetchChatConfig,
  listConversations,
  listMessages,
  listModels,
  probeModel,
  streamChat,
  updateConversation,
  updateModel,
} from '@/api/chat'
import { createTypewriter } from '@/composables/useTypewriter'
import { RAG_DEFAULTS, STORAGE_KEYS } from '@/config'
import { notifyError } from '@/utils/notify'
import { titleFromQuestion, uid } from '@/utils/format'
import router from '@/router'

function readSelectedBases() {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.activeKnowledgeBases)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function persistSelectedBases(ids) {
  try {
    localStorage.setItem(STORAGE_KEYS.activeKnowledgeBases, JSON.stringify(ids))
  } catch {
    /* ignore */
  }
}

function readSelectedModel() {
  try {
    return localStorage.getItem(STORAGE_KEYS.selectedModel) || ''
  } catch {
    return ''
  }
}

function persistSelectedModel(id) {
  try {
    if (id) localStorage.setItem(STORAGE_KEYS.selectedModel, id)
    else localStorage.removeItem(STORAGE_KEYS.selectedModel)
  } catch {
    /* ignore */
  }
}

export const useChatStore = defineStore('chat', () => {
  /* ---------------------------------------------------------------- *
   * 会话列表
   * ---------------------------------------------------------------- */
  const conversations = ref([])
  const conversationsLoading = ref(false)

  /* ---------------------------------------------------------------- *
   * 当前会话
   * ---------------------------------------------------------------- */
  const activeConversationId = ref(null)
  const messages = ref([])
  const messagesLoading = ref(false)

  /* ---------------------------------------------------------------- *
   * 流式状态
   * ---------------------------------------------------------------- */
  const streaming = ref(false)
  const streamingMessageId = ref(null)
  const lastError = ref('')

  /* ---------------------------------------------------------------- *
   * 检索参数
   * ---------------------------------------------------------------- */
  const selectedKnowledgeBaseIds = ref(readSelectedBases())
  const topK = ref(RAG_DEFAULTS.topK)
  const scoreThreshold = ref(RAG_DEFAULTS.scoreThreshold)

  /* ---------------------------------------------------------------- *
   * 生成模型（与向量化模型无关）
   *
   * 说明：知识库里检索不到依据时，后端会改用模型自身知识作答，
   * 并在回答前加「非知识库依据」标注。这里负责模型选择与来源状态。
   * ---------------------------------------------------------------- */
  const models = ref([])
  const modelsLoading = ref(false)
  const selectedModelId = ref(readSelectedModel())
  /** 服务端是否允许「无依据时回退到模型自身知识」 */
  const fallbackToModel = ref(true)
  /** 本地模型预设（Ollama / vLLM / LM Studio），供一键填入 */
  const modelPresets = ref([])

  const activeModel = computed(
    () => models.value.find((item) => item.id === selectedModelId.value) || models.value[0] || null,
  )

  async function loadModels() {
    modelsLoading.value = true
    try {
      const data = await listModels()
      models.value = Array.isArray(data?.models) ? data.models : []
      modelPresets.value = Array.isArray(data?.presets) ? data.presets : []
      if (typeof data?.fallbackToModel === 'boolean') fallbackToModel.value = data.fallbackToModel
      // 本地存的模型可能已从服务端移除，或首次使用未选择 → 回落到默认模型
      const exists = models.value.some((item) => item.id === selectedModelId.value)
      if (!exists) selectModel(data?.defaultId || models.value[0]?.id || '')
      return models.value
    } catch (error) {
      notifyError(error, '模型列表加载失败')
      return []
    } finally {
      modelsLoading.value = false
    }
  }

  function selectModel(id) {
    selectedModelId.value = id || ''
    persistSelectedModel(selectedModelId.value)
  }

  /* ---------------- 用户自带模型的管理 ---------------- */

  /** 新增模型；成功后自动选中它 */
  async function addModel(payload) {
    const created = await createModel(payload)
    await loadModels()
    if (created?.id) selectModel(created.id)
    return created
  }

  /** 修改模型；payload.apiKey 留空表示不修改密钥 */
  async function editModel(id, payload) {
    const updated = await updateModel(id, payload)
    await loadModels()
    return updated
  }

  /** 删除模型；若删的是当前选中项，自动切回默认模型 */
  async function removeModel(id) {
    await deleteModel(id)
    if (selectedModelId.value === id) selectModel('')
    await loadModels()
    return true
  }

  /** 连通性自检 */
  async function checkModel(id) {
    return probeModel(id)
  }

  /** 读取服务端 RAG 参数（Top-K / 阈值 / 回退开关），避免两端各写一份 */
  async function loadChatConfig() {
    try {
      const config = await fetchChatConfig()
      if (typeof config?.fallbackToModel === 'boolean') fallbackToModel.value = config.fallbackToModel
      return config
    } catch {
      // 拿不到就用本地默认值，不打断使用
      return null
    }
  }

  const activeConversation = computed(
    () => conversations.value.find((item) => item.id === activeConversationId.value) || null,
  )

  const isEmptyConversation = computed(() => messages.value.length === 0)

  let abortController = null
  let typewriter = null
  /** 已经加载过消息的会话 id，避免重复请求 */
  let loadedConversationId = null

  function sortConversations() {
    conversations.value.sort(
      (a, b) => new Date(b.updatedAt || 0).getTime() - new Date(a.updatedAt || 0).getTime(),
    )
  }

  /* ---------------------------------------------------------------- *
   * 会话列表与切换
   * ---------------------------------------------------------------- */
  async function loadConversations() {
    conversationsLoading.value = true
    try {
      const list = await listConversations()
      conversations.value = Array.isArray(list) ? list : []
      sortConversations()
      return conversations.value
    } catch (error) {
      notifyError(error, '会话列表加载失败')
      return []
    } finally {
      conversationsLoading.value = false
    }
  }

  /** 打开会话（由路由参数驱动）；传 null 表示「新对话」 */
  async function openConversation(id) {
    const nextId = id || null

    // 切到别的会话时先中断当前流，避免增量继续写向已经离开的界面
    if (nextId !== activeConversationId.value && streaming.value) stopStreaming()

    if (nextId === null) {
      activeConversationId.value = null
      messages.value = []
      loadedConversationId = null
      return
    }

    if (nextId === loadedConversationId) {
      activeConversationId.value = nextId
      return
    }

    activeConversationId.value = nextId
    loadedConversationId = nextId
    messagesLoading.value = true
    try {
      const list = await listMessages(nextId)
      // 加载期间用户可能已经切走
      if (loadedConversationId !== nextId) return
      messages.value = Array.isArray(list) ? list.map((item) => ({ status: 'done', ...item })) : []
    } catch (error) {
      notifyError(error, '对话记录加载失败')
      if (loadedConversationId === nextId) messages.value = []
    } finally {
      if (loadedConversationId === nextId) messagesLoading.value = false
    }
  }

  /** 新建对话：先清空界面，真正的会话记录在首次提问时落库 */
  function startNewConversation() {
    stopStreaming()
    activeConversationId.value = null
    messages.value = []
    loadedConversationId = null
    lastError.value = ''
    if (router.currentRoute.value.name !== 'chat-new') {
      router.push({ name: 'chat-new' })
    }
  }

  async function renameConversation(id, title) {
    const previous = conversations.value.find((item) => item.id === id)
    const previousTitle = previous?.title
    if (previous) previous.title = title
    try {
      const updated = await updateConversation(id, { title })
      if (previous && updated) Object.assign(previous, updated)
      return true
    } catch (error) {
      if (previous) previous.title = previousTitle
      notifyError(error, '重命名失败')
      return false
    }
  }

  async function removeConversation(id) {
    try {
      await deleteConversation(id)
      conversations.value = conversations.value.filter((item) => item.id !== id)
      if (activeConversationId.value === id) {
        stopStreaming()
        activeConversationId.value = null
        messages.value = []
        loadedConversationId = null
        if (router.currentRoute.value.name !== 'chat-new') {
          router.push({ name: 'chat-new' })
        }
      }
      return true
    } catch (error) {
      notifyError(error, '删除会话失败')
      return false
    }
  }

  /* ---------------------------------------------------------------- *
   * 检索范围与参数
   * ---------------------------------------------------------------- */
  function toggleKnowledgeBase(id) {
    const set = new Set(selectedKnowledgeBaseIds.value)
    if (set.has(id)) set.delete(id)
    else set.add(id)
    selectedKnowledgeBaseIds.value = [...set]
    persistSelectedBases(selectedKnowledgeBaseIds.value)
  }

  function setSelectedKnowledgeBases(ids) {
    selectedKnowledgeBaseIds.value = [...new Set(ids || [])]
    persistSelectedBases(selectedKnowledgeBaseIds.value)
  }

  /* ---------------------------------------------------------------- *
   * 流式问答
   * ---------------------------------------------------------------- */
  function stopStreaming() {
    const controller = abortController
    abortController = null
    if (controller) controller.abort()

    if (typewriter) {
      // 保留已经吐出的内容，把剩余缓冲立刻补全
      typewriter.flush()
      typewriter.stop()
      typewriter = null
    }

    streaming.value = false
    streamingMessageId.value = null
  }

  /**
   * 发送提问并消费 SSE 流。
   * 用户气泡与空的助手气泡会立即渲染，随后边收边用打字机输出。
   * @param {string} text
   */
  async function sendMessage(text) {
    const content = String(text ?? '').trim()
    if (!content || streaming.value) return

    lastError.value = ''

    /* 1. 先建好中断控制器与打字机，保证「停止生成」第一时刻就有效 */
    const assistant = reactive({
      id: uid('msg'),
      serverId: '',
      role: 'assistant',
      content: '',
      sources: [],
      createdAt: new Date().toISOString(),
      status: 'streaming',
      error: '',
      // knowledge_base（有检索依据）/ model（模型自身知识）/ none（未生成）
      source: 'knowledge_base',
      // 本次回答使用的模型（展示用）
      modelLabel: '',
      /** 是否知识库中未检索到依据（用于显示醒目提示） */
      grounded: true,
    })

    const writer = createTypewriter({
      onUpdate: (chunk) => {
        assistant.content += chunk
      },
    })
    const controller = new AbortController()
    abortController = controller
    typewriter = writer

    /** 当前这次流是否还是「正在进行且未被停止」的那一次 */
    const isCurrentStream = () => abortController === controller && !controller.signal.aborted

    messages.value.push(
      {
        id: uid('msg'),
        role: 'user',
        content,
        createdAt: new Date().toISOString(),
        status: 'done',
      },
      assistant,
    )

    streaming.value = true
    streamingMessageId.value = assistant.id

    /** 会话 id：没有会话时在下面按需创建 */
    let conversationId = activeConversationId.value

    try {
      /* 2. 首次提问：创建会话并同步路由 */
      if (!conversationId) {
        const created = await createConversation({
          title: titleFromQuestion(content),
          knowledgeBaseIds: [...selectedKnowledgeBaseIds.value],
        })
        if (!isCurrentStream()) return

        conversationId = created.id
        conversations.value.unshift(created)
        sortConversations()
        activeConversationId.value = conversationId
        loadedConversationId = conversationId
        if (router.currentRoute.value.name !== 'chat') {
          router.replace({ name: 'chat', params: { id: conversationId } })
        }
      }

      /* 3. 消费 SSE */
      await streamChat(
        {
          conversationId,
          content,
          knowledgeBaseIds: [...selectedKnowledgeBaseIds.value],
          topK: topK.value,
          scoreThreshold: scoreThreshold.value,
          // 生成模型（不影响检索用的向量化模型）
          modelId: selectedModelId.value || undefined,
        },
        {
          signal: controller.signal,
          onEvent(event) {
            if (!isCurrentStream()) return

            switch (event.type) {
              case 'meta':
                // 后端在正文之前就告知本次是否有知识库依据，前端可即时提示
                if (typeof event.grounded === 'boolean') assistant.grounded = event.grounded
                if (event.answerSource) assistant.source = event.answerSource
                if (event.modelLabel) assistant.modelLabel = event.modelLabel
                break
              case 'delta':
                assistant.status = 'streaming'
                writer.push(event.content)
                break
              case 'sources':
                assistant.sources = Array.isArray(event.sources) ? event.sources : []
                break
              case 'done':
                assistant.serverId = event.messageId || assistant.serverId
                if (event.source) assistant.source = event.source
                if (typeof event.grounded === 'boolean') assistant.grounded = event.grounded
                if (event.modelLabel) assistant.modelLabel = event.modelLabel
                break
              case 'title': {
                const conversation = conversations.value.find((item) => item.id === conversationId)
                if (event.title && conversation) {
                  conversation.title = event.title
                  conversation.updatedAt = new Date().toISOString()
                  sortConversations()
                }
                break
              }
              case 'error':
                throw new Error(event.message || '生成回答失败')
              default:
                break
            }
          },
        },
      )

      await writer.drain()
      assistant.status = assistant.content ? 'done' : 'error'
      if (!assistant.content) {
        assistant.error = '没有收到任何回答内容，请检查后端流式接口。'
        lastError.value = assistant.error
        notifyError(new Error(assistant.error))
      }
    } catch (error) {
      if (error?.name === 'AbortError' || error?.code === 'CANCELLED') {
        // 用户主动停止：保留已产出的内容
        assistant.status = assistant.content ? 'stopped' : 'error'
        if (!assistant.content) assistant.error = '生成已中断'
      } else {
        assistant.status = 'error'
        assistant.error = error?.message || '生成回答失败'
        lastError.value = assistant.error
        notifyError(error, '生成回答失败')
      }
    } finally {
      writer.flush()
      writer.stop()
      if (typewriter === writer) typewriter = null
      if (abortController === controller) abortController = null

      streaming.value = false
      streamingMessageId.value = null

      const conversation = conversations.value.find((item) => item.id === conversationId)
      if (conversation) {
        conversation.updatedAt = new Date().toISOString()
        // 只有仍停留在该会话时，messages 才属于它
        if (activeConversationId.value === conversationId) {
          conversation.messageCount = messages.value.length
        }
        if (!conversation.title || conversation.title === '新的对话') {
          conversation.title = titleFromQuestion(content)
        }
        sortConversations()
      }
    }
  }

  /** 重新生成最后一条回答 */
  async function regenerate() {
    if (streaming.value) return
    const lastUser = [...messages.value].reverse().find((item) => item.role === 'user')
    if (!lastUser) return

    // 丢弃最后一条助手消息与对应的提问，再重发
    const lastIndex = messages.value.length - 1
    if (messages.value[lastIndex]?.role === 'assistant') messages.value.splice(lastIndex, 1)
    const userIndex = messages.value.findIndex((item) => item.id === lastUser.id)
    if (userIndex >= 0) messages.value.splice(userIndex, 1)

    await sendMessage(lastUser.content)
  }

  function reset() {
    stopStreaming()
    conversations.value = []
    messages.value = []
    activeConversationId.value = null
    loadedConversationId = null
    lastError.value = ''
  }

  return {
    conversations,
    conversationsLoading,
    activeConversationId,
    activeConversation,
    messages,
    messagesLoading,
    streaming,
    streamingMessageId,
    lastError,
    isEmptyConversation,
    selectedKnowledgeBaseIds,
    topK,
    scoreThreshold,
    // 生成模型与回退状态
    models,
    modelsLoading,
    modelPresets,
    selectedModelId,
    activeModel,
    fallbackToModel,
    loadModels,
    selectModel,
    addModel,
    editModel,
    removeModel,
    checkModel,
    loadChatConfig,
    loadConversations,
    openConversation,
    startNewConversation,
    sendMessage,
    regenerate,
    stopStreaming,
    renameConversation,
    removeConversation,
    toggleKnowledgeBase,
    setSelectedKnowledgeBases,
    reset,
  }
})
