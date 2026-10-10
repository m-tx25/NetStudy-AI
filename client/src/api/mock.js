/**
 * 内置 Mock 数据层。
 *
 * 目的：在没有后端的情况下，也能完整体验登录注册、流式问答（打字机）、
 * 知识库与文档上传管理的全部交互。数据存在 localStorage，刷新不丢。
 *
 * 关闭方式：client/.env.development 里 VITE_USE_MOCK=false
 */
import { uid, titleFromQuestion } from '@/utils/format'

const DB_KEY = 'rag.mock.db.v1'

/* ------------------------------------------------------------------ *
 * 数据
 * ------------------------------------------------------------------ */
function seedDb() {
  const now = Date.now()
  const baseA = {
    id: 'kb_product',
    name: '产品需求文档库',
    description: '需求规格、产品路线图、竞品分析等产品侧资料',
    documentCount: 3,
    chunkCount: 486,
    embeddingModel: 'bge-large-zh-v1.5',
    createdAt: new Date(now - 86400000 * 12).toISOString(),
    updatedAt: new Date(now - 86400000 * 2).toISOString(),
  }
  const baseB = {
    id: 'kb_tech',
    name: '技术文档库',
    description: '系统架构、接口文档、部署运维手册',
    documentCount: 3,
    chunkCount: 731,
    embeddingModel: 'bge-large-zh-v1.5',
    createdAt: new Date(now - 86400000 * 20).toISOString(),
    updatedAt: new Date(now - 86400000).toISOString(),
  }
  const baseC = {
    id: 'kb_hr',
    name: '规章制度库',
    description: '员工手册、报销与审批流程',
    documentCount: 2,
    chunkCount: 264,
    embeddingModel: 'bge-large-zh-v1.5',
    createdAt: new Date(now - 86400000 * 5).toISOString(),
    updatedAt: new Date(now - 3600000 * 6).toISOString(),
  }

  const doc = (id, kbId, name, size, chunks, hoursAgo, status = 'ready') => ({
    id,
    knowledgeBaseId: kbId,
    name,
    size,
    chunks,
    status,
    enabled: true,
    uploadedAt: new Date(now - hoursAgo * 3600000).toISOString(),
  })

  const conversations = [
    {
      id: 'conv_demo',
      title: 'RAG 检索流程是怎样的',
      createdAt: new Date(now - 3600000 * 3).toISOString(),
      updatedAt: new Date(now - 3600000 * 3).toISOString(),
      messageCount: 2,
      knowledgeBaseIds: [baseB.id],
    },
    {
      id: 'conv_demo2',
      title: '报销流程说明',
      createdAt: new Date(now - 86400000).toISOString(),
      updatedAt: new Date(now - 86400000).toISOString(),
      messageCount: 2,
      knowledgeBaseIds: [baseC.id],
    },
  ]

  const messages = {
    conv_demo: [
      {
        id: uid('msg'),
        role: 'user',
        content: 'RAG 的检索流程是怎样的？',
        createdAt: new Date(now - 3600000 * 3).toISOString(),
      },
      {
        id: uid('msg'),
        role: 'assistant',
        content:
          'RAG（Retrieval-Augmented Generation）的核心是**先检索、再生成**，整体流程可以拆成离线与在线两个阶段：\n\n' +
          '### 一、离线索引阶段\n' +
          '1. **文档解析**：把 PDF / Word / Markdown 转成纯文本，保留标题层级。\n' +
          '2. **分块（Chunking）**：按 300~800 字滑窗切分，块之间保留重叠，避免语义被截断。\n' +
          '3. **向量化**：用 Embedding 模型把每个块编码成向量。\n' +
          '4. **入库**：向量与元数据（文件名、页码、块序号）一起写入向量数据库。\n\n' +
          '### 二、在线问答阶段\n' +
          '1. **问题向量化**：用同一个 Embedding 模型编码用户问题。\n' +
          '2. **相似度召回**：在向量库中取 Top-K（本项目默认 K=5）。\n' +
          '3. **重排与过滤**：按分数阈值剔除弱相关结果，可选 Cross-Encoder 精排。\n' +
          '4. **拼装 Prompt**：把命中的片段作为「参考资料」注入上下文，并约束模型「只依据资料回答」。\n' +
          '5. **流式生成**：大模型逐 token 输出，服务端通过 SSE 推给前端，形成打字机效果。\n\n' +
          '> 关键点：资料里没有的内容，应当明确回答「知识库中未找到相关依据」，而不是编造。',
        sources: [
          {
            id: 'chunk_1',
            documentId: 'doc_arch',
            documentName: '系统架构设计.docx',
            knowledgeBaseName: '技术文档库',
            score: 0.91,
            snippet:
              '检索增强生成（RAG）链路由文档解析、分块、向量化、向量检索与大模型生成五个环节组成……',
          },
          {
            id: 'chunk_2',
            documentId: 'doc_api',
            documentName: 'API 接口文档.md',
            knowledgeBaseName: '技术文档库',
            score: 0.83,
            snippet: 'POST /api/chat/stream 以 text/event-stream 返回增量内容，事件类型包含 delta、sources、done……',
          },
        ],
        createdAt: new Date(now - 3600000 * 3 + 2000).toISOString(),
        status: 'done',
      },
    ],
    conv_demo2: [
      {
        id: uid('msg'),
        role: 'user',
        content: '报销流程说明',
        createdAt: new Date(now - 86400000).toISOString(),
      },
      {
        id: uid('msg'),
        role: 'assistant',
        content:
          '根据《报销流程说明》，标准流程分为四步：\n\n' +
          '| 步骤 | 责任人 | 时限 |\n| --- | --- | --- |\n| 提交票据 | 申请人 | 费用发生后 15 日内 |\n| 直属主管审批 | 部门主管 | 2 个工作日 |\n| 财务复核 | 财务专员 | 3 个工作日 |\n| 打款 | 财务出纳 | 每月 15 日 / 30 日 |\n\n' +
          '需要注意：单张发票金额超过 **5000 元** 时，需额外附上采购申请单编号。',
        sources: [
          {
            id: 'chunk_3',
            documentId: 'doc_reimburse',
            documentName: '报销流程说明.docx',
            knowledgeBaseName: '规章制度库',
            score: 0.88,
            snippet: '申请人应在费用发生后 15 日内提交票据，逾期需部门主管书面说明……',
          },
        ],
        createdAt: new Date(now - 86400000 + 3000).toISOString(),
        status: 'done',
      },
    ],
  }

  return {
    // 账号资料与登录状态分开存：退出登录只清 session，资料保留，便于演示「改密码后重新登录」
    user: null,
    session: false,
    credentials: { username: 'demo', password: '123456' },
    conversations,
    messages,
    knowledgeBases: [baseA, baseB, baseC],
    documents: [
      doc('doc_prd', baseA.id, '需求规格说明书_v2.pdf', 4_512_000, 186, 30),
      doc('doc_roadmap', baseA.id, '产品路线图2025.md', 86_000, 42, 52),
      doc('doc_compete', baseA.id, '竞品分析报告.docx', 2_140_000, 258, 100),
      doc('doc_arch', baseB.id, '系统架构设计.docx', 3_260_000, 312, 12),
      doc('doc_api', baseB.id, 'API接口文档.md', 154_000, 97, 6),
      doc('doc_deploy', baseB.id, '部署运维手册.pdf', 6_880_000, 322, 48),
      doc('doc_staff', baseC.id, '员工手册2025.pdf', 5_120_000, 198, 70),
      doc('doc_reimburse', baseC.id, '报销流程说明.docx', 512_000, 66, 5),
    ],
  }
}

let db = load()

function load() {
  try {
    const raw = localStorage.getItem(DB_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && Array.isArray(parsed.conversations)) {
        // 注意：这里不能给模块级 db 赋值（此时它还在 TDZ 中），只做原地补全
        ensureAccountStateFor(parsed)
        return parsed
      }
    }
  } catch {
    /* ignore */
  }
  return seedDb()
}

function persist() {
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(db))
  } catch {
    /* ignore（隐私模式下可能失败） */
  }
}

export function resetMockDb() {
  db = seedDb()
  persist()
}

/* ------------------------------------------------------------------ *
 * 工具
 * ------------------------------------------------------------------ */
function abortError() {
  const error = new Error('Aborted')
  error.name = 'AbortError'
  return error
}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError())
      return
    }
    const onAbort = () => {
      clearTimeout(timer)
      reject(abortError())
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

function makeUser(username, email) {
  const name = username || 'demo'
  const now = new Date().toISOString()
  return {
    id: `user_${name}`,
    username: name,
    nickname: name === 'demo' ? '演示用户' : name,
    email: email || `${name}@example.com`,
    avatar: '',
    role: 'user',
    createdAt: now,
    lastLoginAt: now,
  }
}

function makeToken(user) {
  return `mock.${btoa(unescape(encodeURIComponent(JSON.stringify({ sub: user.id, t: Date.now() }))))}.token`
}

/**
 * 老版本的 Mock 数据里没有 session / credentials，读出来时补全，
 * 这样升级后刷新页面不会因为缺字段而报错。
 */
function ensureAccountStateFor(target) {
  if (typeof target.session !== 'boolean') target.session = Boolean(target.user)
  if (!target.credentials) {
    target.credentials = { username: target.user?.username || 'demo', password: '123456' }
  }
  return target
}

function ensureAccountState() {
  return ensureAccountStateFor(db)
}

const USERNAME_PATTERN = /^[A-Za-z0-9_\u4e00-\u9fa5-]{2,32}$/

function assertUsername(name) {
  if (!USERNAME_PATTERN.test(name)) {
    throw new Error('用户名需为 2~32 位的字母、数字、下划线、连字符或中文')
  }
}

function assertEmail(email) {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('邮箱格式不正确')
}

/* ------------------------------------------------------------------ *
 * 鉴权
 * ------------------------------------------------------------------ */
export const mockAuth = {
  async login({ username, password }) {
    await sleep(420)
    const name = String(username || '').trim()
    const pwd = String(password || '')
    if (!name || !pwd) throw new Error('请输入用户名和密码')

    ensureAccountState()

    if (db.credentials.username && name === db.credentials.username) {
      // 已存在的账号：必须用当前密码
      if (pwd !== db.credentials.password) throw new Error('用户名或密码不正确')
    } else if (pwd.length < 6) {
      throw new Error('密码至少 6 位')
    } else {
      // 演示模式：新用户名视为新账号，首次登录即记住该密码
      db.credentials = { username: name, password: pwd }
    }

    const base = db.user && db.user.username === name ? db.user : makeUser(name)
    db.user = { ...base, username: name, lastLoginAt: new Date().toISOString() }
    db.session = true
    persist()
    return { token: makeToken(db.user), user: clone(db.user) }
  },

  async register({ username, email, password }) {
    await sleep(520)
    const name = String(username || '').trim()
    const pwd = String(password || '')
    if (!name || !pwd) throw new Error('请填写完整的注册信息')
    assertUsername(name)
    if (pwd.length < 6) throw new Error('密码至少 6 位')

    db.user = makeUser(name, email)
    db.credentials = { username: name, password: pwd }
    db.session = true
    persist()
    return { token: makeToken(db.user), user: clone(db.user) }
  },

  async profile() {
    await sleep(120)
    ensureAccountState()
    if (!db.session || !db.user) throw new Error('未登录')
    return clone(db.user)
  },

  async logout() {
    await sleep(100)
    ensureAccountState()
    db.session = false
    persist()
    return { ok: true }
  },

  /** 修改账号资料：用户名 / 昵称 / 邮箱 / 头像 */
  async updateProfile(payload = {}) {
    await sleep(380)
    ensureAccountState()
    if (!db.user) throw new Error('未登录')

    const previousUsername = db.user.username
    const nextUsername =
      payload.username === undefined ? previousUsername : String(payload.username).trim()
    assertUsername(nextUsername)

    if (nextUsername !== previousUsername) {
      // 登录名一起变更，之后需要用新的用户名登录
      db.credentials.username = nextUsername
    }

    if (payload.email !== undefined) {
      const email = String(payload.email).trim()
      assertEmail(email)
      db.user.email = email
    }
    if (payload.nickname !== undefined) {
      const nickname = String(payload.nickname).trim()
      if (nickname.length > 32) throw new Error('昵称不能超过 32 个字符')
      db.user.nickname = nickname
    }
    if (payload.avatar !== undefined) db.user.avatar = payload.avatar

    db.user.username = nextUsername
    persist()
    return clone(db.user)
  },

  /** 修改密码：必须校验当前密码 */
  async changePassword({ currentPassword, newPassword } = {}) {
    await sleep(460)
    ensureAccountState()
    if (!db.user) throw new Error('未登录')

    const current = String(currentPassword || '')
    const next = String(newPassword || '')

    if (!current) throw new Error('请输入当前密码')
    if (current !== db.credentials.password) throw new Error('当前密码不正确')
    if (next.length < 6) throw new Error('新密码至少 6 位')
    if (next === current) throw new Error('新密码不能与当前密码相同')

    db.credentials.password = next
    persist()
    return { ok: true, changedAt: new Date().toISOString() }
  },

  /** 忘记密码：发送重置邮件（不暴露账号是否存在） */
  async forgotPassword({ username, email } = {}) {
    await sleep(650)
    if (!String(username || '').trim() || !String(email || '').trim()) {
      throw new Error('请填写用户名与注册邮箱')
    }
    return { ok: true }
  },
}

/* ------------------------------------------------------------------ *
 * 会话与消息
 * ------------------------------------------------------------------ */
export const mockChat = {
  async listConversations() {
    await sleep(180)
    return clone(
      [...db.conversations].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt)),
    )
  },

  async createConversation(payload = {}) {
    await sleep(120)
    const now = new Date().toISOString()
    const conversation = {
      id: uid('conv'),
      title: payload.title || '新的对话',
      createdAt: now,
      updatedAt: now,
      messageCount: 0,
      knowledgeBaseIds: payload.knowledgeBaseIds || [],
    }
    db.conversations.unshift(conversation)
    db.messages[conversation.id] = []
    persist()
    return clone(conversation)
  },

  async updateConversation(id, payload) {
    await sleep(120)
    const conversation = db.conversations.find((item) => item.id === id)
    if (!conversation) throw new Error('会话不存在')
    Object.assign(conversation, payload, { updatedAt: new Date().toISOString() })
    persist()
    return clone(conversation)
  },

  async deleteConversation(id) {
    await sleep(160)
    db.conversations = db.conversations.filter((item) => item.id !== id)
    delete db.messages[id]
    persist()
    return { ok: true }
  },

  async listMessages(conversationId) {
    await sleep(160)
    return clone(db.messages[conversationId] || [])
  },
}

/* ------------------------------------------------------------------ *
 * 知识库与文档
 * ------------------------------------------------------------------ */
export const mockKnowledge = {
  async listKnowledgeBases() {
    await sleep(200)
    return clone(
      [...db.knowledgeBases].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt)),
    )
  },

  async createKnowledgeBase(payload) {
    await sleep(320)
    const now = new Date().toISOString()
    const base = {
      id: uid('kb'),
      name: payload.name,
      description: payload.description || '',
      documentCount: 0,
      chunkCount: 0,
      embeddingModel: payload.embeddingModel || 'bge-large-zh-v1.5',
      createdAt: now,
      updatedAt: now,
    }
    db.knowledgeBases.unshift(base)
    persist()
    return clone(base)
  },

  async updateKnowledgeBase(id, payload) {
    await sleep(200)
    const base = db.knowledgeBases.find((item) => item.id === id)
    if (!base) throw new Error('知识库不存在')
    Object.assign(base, payload, { updatedAt: new Date().toISOString() })
    persist()
    return clone(base)
  },

  async deleteKnowledgeBase(id) {
    await sleep(260)
    db.knowledgeBases = db.knowledgeBases.filter((item) => item.id !== id)
    db.documents = db.documents.filter((item) => item.knowledgeBaseId !== id)
    db.conversations.forEach((conversation) => {
      conversation.knowledgeBaseIds = (conversation.knowledgeBaseIds || []).filter(
        (kbId) => kbId !== id,
      )
    })
    persist()
    return { ok: true }
  },

  async listDocuments(knowledgeBaseId) {
    await sleep(200)
    return clone(
      db.documents
        .filter((item) => !knowledgeBaseId || item.knowledgeBaseId === knowledgeBaseId)
        .sort((a, b) => new Date(b.uploadedAt) - new Date(a.uploadedAt)),
    )
  },

  async uploadDocument(knowledgeBaseId, file, onProgress) {
    const document = {
      id: uid('doc'),
      knowledgeBaseId,
      name: file.name,
      size: file.size,
      chunks: 0,
      status: 'processing',
      enabled: true,
      uploadedAt: new Date().toISOString(),
    }
    db.documents.unshift(document)
    persist()

    // 模拟解析 + 分块 + 向量化进度
    const estimatedChunks = Math.max(8, Math.round(file.size / 4096))
    for (let percent = 10; percent <= 100; percent += 10) {
      await sleep(180)
      onProgress?.(percent)
      document.chunks = Math.round((estimatedChunks * percent) / 100)
      persist()
    }

    document.status = 'ready'
    document.chunks = estimatedChunks
    const base = db.knowledgeBases.find((item) => item.id === knowledgeBaseId)
    if (base) {
      base.documentCount = db.documents.filter((d) => d.knowledgeBaseId === base.id).length
      base.chunkCount = db.documents
        .filter((d) => d.knowledgeBaseId === base.id)
        .reduce((sum, d) => sum + (d.chunks || 0), 0)
      base.updatedAt = new Date().toISOString()
    }
    persist()
    return clone(document)
  },

  async updateDocument(id, payload) {
    await sleep(160)
    const document = db.documents.find((item) => item.id === id)
    if (!document) throw new Error('文档不存在')
    Object.assign(document, payload)
    persist()
    return clone(document)
  },

  async deleteDocument(id) {
    await sleep(220)
    const document = db.documents.find((item) => item.id === id)
    db.documents = db.documents.filter((item) => item.id !== id)
    if (document) {
      const base = db.knowledgeBases.find((item) => item.id === document.knowledgeBaseId)
      if (base) {
        base.documentCount = db.documents.filter((d) => d.knowledgeBaseId === base.id).length
        base.chunkCount = db.documents
          .filter((d) => d.knowledgeBaseId === base.id)
          .reduce((sum, d) => sum + (d.chunks || 0), 0)
      }
    }
    persist()
    return { ok: true }
  },

  async reindexDocument(id) {
    const document = db.documents.find((item) => item.id === id)
    if (!document) throw new Error('文档不存在')
    document.status = 'processing'
    persist()
    await sleep(1400)
    document.status = 'ready'
    document.chunks = Math.max(8, Math.round(document.size / 4096))
    persist()
    return clone(document)
  },
}

/* ------------------------------------------------------------------ *
 * 流式问答
 * ------------------------------------------------------------------ */
function pickSources(knowledgeBaseIds, topK) {
  const pool = db.documents.filter(
    (item) =>
      item.enabled &&
      item.status === 'ready' &&
      (!knowledgeBaseIds?.length || knowledgeBaseIds.includes(item.knowledgeBaseId)),
  )
  const baseNameOf = (id) => db.knowledgeBases.find((item) => item.id === id)?.name || '知识库'
  const snippets = [
    '本文档说明了整体设计目标、关键模块划分与各模块之间的数据流向，并给出了接口协议的字段定义……',
    '在检索阶段，系统会将用户问题编码为向量，并在向量库中执行近似最近邻搜索，返回 Top-K 相关片段……',
    '为控制延迟，服务端采用流式返回（Server-Sent Events），首字延迟通常控制在 500ms 以内……',
    '注意事项：当召回结果的相关度低于阈值时，应当明确告知用户「知识库中暂无相关依据」，避免模型臆造……',
    '配置项默认值：chunk_size=512、chunk_overlap=64、top_k=5、score_threshold=0.2，可按业务场景调整……',
  ]
  return pool.slice(0, Math.max(1, Math.min(topK || 5, pool.length || 1))).map((item, index) => ({
    id: `chunk_${item.id}_${index}`,
    documentId: item.id,
    documentName: item.name,
    knowledgeBaseId: item.knowledgeBaseId,
    knowledgeBaseName: baseNameOf(item.knowledgeBaseId),
    score: Number((0.93 - index * 0.06).toFixed(2)),
    page: 1 + index * 3,
    snippet: snippets[index % snippets.length],
  }))
}

function buildAnswer(question, sources, kbNames) {
  if (!sources.length) {
    return (
      `当前没有可用的知识库内容，我无法基于资料回答「${question}」。\n\n` +
      '请先到 **知识库管理** 上传文档，并在输入框上方勾选要检索的知识库，然后再提问。'
    )
  }

  const scope = kbNames.length ? kbNames.join('、') : '全部知识库'
  const lines = [
    `根据 **${scope}** 中检索到的 ${sources.length} 个片段，回答如下：\n`,
    '### 结论',
    `针对「${question}」，知识库中的资料给出的要点是：`,
    '',
  ]

  sources.forEach((source, index) => {
    lines.push(
      `${index + 1}. ${source.snippet.replace(/^本文档说明了/, '文档说明')}（来源：**${source.documentName}** [${index + 1}]）`,
    )
  })

  lines.push('')
  lines.push('### 补充说明')
  lines.push(
    '- 以上内容全部来自知识库召回片段，未使用模型自身记忆进行补充；\n' +
      '- 若需要更精确的答案，建议在知识库中补充更细粒度的文档，或调大召回数量 Top-K；\n' +
      '- 每个回答下方的「引用来源」可以展开查看原文片段与相关度分数。',
  )

  if (/代码|示例|code|demo|实现|怎么用|如何调用/i.test(question)) {
    lines.push('')
    lines.push('### 调用示例')
    lines.push('下面是一个前端调用流式问答接口的等价写法：')
    lines.push('')
    lines.push('```js')
    lines.push("const res = await fetch('/api/chat/stream', {")
    lines.push("  method: 'POST',")
    lines.push("  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },")
    lines.push('  body: JSON.stringify({ content: question, knowledgeBaseIds }),')
    lines.push('})')
    lines.push('')
    lines.push('const reader = res.body.getReader()')
    lines.push("const decoder = new TextDecoder('utf-8')")
    lines.push('for (;;) {')
    lines.push('  const { done, value } = await reader.read()')
    lines.push('  if (done) break')
    lines.push('  // 逐块解析 data: {...}，把增量文本追加到界面上')
    lines.push('  console.log(decoder.decode(value, { stream: true }))')
    lines.push('}')
    lines.push('```')
  }

  return lines.join('\n')
}

export async function mockStreamChat(payload, { signal, onEvent } = {}) {
  const { conversationId, content, knowledgeBaseIds = [], topK = 5 } = payload || {}

  const kbNames = db.knowledgeBases
    .filter((item) => knowledgeBaseIds.includes(item.id))
    .map((item) => item.name)

  const sources = pickSources(knowledgeBaseIds, topK)
  const answer = buildAnswer(content, sources, kbNames)

  // 首字延迟，模拟检索耗时
  await sleep(320, signal)
  onEvent?.({ type: 'meta', conversationId, model: 'mock-rag-v1' })

  // 先推引用来源，再推正文，和真实后端推荐顺序一致
  await sleep(120, signal)
  onEvent?.({ type: 'sources', sources })

  // 按 1~6 个字符随机切片，制造不均匀的流式节奏（正好检验打字机缓冲）
  let cursor = 0
  while (cursor < answer.length) {
    const size = 1 + Math.floor(Math.random() * 6)
    const chunk = answer.slice(cursor, cursor + size)
    cursor += size
    onEvent?.({ type: 'delta', content: chunk })
    await sleep(14 + Math.random() * 26, signal)
  }

  onEvent?.({ type: 'done', messageId: uid('msg'), usage: { promptTokens: 812, completionTokens: 356 } })

  // 写入 mock 数据库，刷新后仍在
  if (conversationId && db.messages[conversationId]) {
    const now = new Date().toISOString()
    db.messages[conversationId].push(
      { id: uid('msg'), role: 'user', content, createdAt: now },
      { id: uid('msg'), role: 'assistant', content: answer, sources, createdAt: now, status: 'done' },
    )
    const conversation = db.conversations.find((item) => item.id === conversationId)
    if (conversation) {
      conversation.updatedAt = now
      conversation.messageCount = db.messages[conversationId].length
      if (!conversation.title || conversation.title === '新的对话') {
        conversation.title = titleFromQuestion(content)
      }
    }
    persist()
  }
}
