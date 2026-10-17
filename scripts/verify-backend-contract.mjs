/**
 * 后端契约验证：逐项核对 FastAPI 实现与前端 client/src/api/* + mock.js 的约定。
 * 用法：node verify-backend-contract.mjs [baseUrl]
 */
const BASE = process.argv[2] || 'http://127.0.0.1:3000/api'
const results = []
let token = ''

function check(name, ok, note = '') {
  results.push({ name, ok: Boolean(ok), note })
}

/** 校验对象是否含全部期望字段 */
function hasKeys(obj, keys) {
  if (!obj || typeof obj !== 'object') return { ok: false, missing: keys }
  const missing = keys.filter((k) => !(k in obj))
  return { ok: missing.length === 0, missing }
}

async function call(method, path, { body, auth = true, raw = false, headers = {} } = {}) {
  const h = { ...headers }
  if (body !== undefined && !raw) h['Content-Type'] = 'application/json'
  if (auth && token) h.Authorization = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: h,
    body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
  })
  const text = await res.text()
  let json = null
  try {
    json = JSON.parse(text)
  } catch {
    /* 非 JSON（如 SSE） */
  }
  return { status: res.status, json, text, contentType: res.headers.get('content-type') || '' }
}

console.log(`\n目标：${BASE}\n${'='.repeat(72)}`)

/* ---------------- 1. 健康检查 ---------------- */
const health = await call('GET', '/health', { auth: false })
check('/health 返回 200', health.status === 200, `HTTP ${health.status}`)
check(
  '/health 保留前端依赖字段 ok/service/time',
  hasKeys(health.json, ['ok', 'service', 'time', 'llmConfigured', 'embeddingMode', 'queue']).ok,
  JSON.stringify(health.json?.queue || {}).slice(0, 80),
)

/* ---------------- 2. 鉴权 ---------------- */
const badLogin = await call('POST', '/auth/login', {
  auth: false,
  body: { username: 'demo', password: 'wrong-password' },
})
check('错误密码被拒（401）', badLogin.status === 401, `HTTP ${badLogin.status}`)

const noAuth = await call('GET', '/conversations', { auth: false })
check('未带 token 访问受保护接口返回 401', noAuth.status === 401, `HTTP ${noAuth.status}`)

const login = await call('POST', '/auth/login', {
  auth: false,
  body: { username: 'demo', password: '123456' },
})
check('演示账号登录成功', login.status === 200 && Boolean(login.json?.token), `HTTP ${login.status}`)
token = login.json?.token || ''
check(
  '登录返回 {token, user}',
  hasKeys(login.json, ['token', 'user']).ok &&
    hasKeys(login.json.user, ['id', 'username', 'nickname', 'email', 'avatar', 'role', 'createdAt', 'lastLoginAt']).ok,
  JSON.stringify(hasKeys(login.json?.user || {}, ['id', 'username', 'nickname', 'email', 'avatar', 'role', 'createdAt', 'lastLoginAt']).missing || []),
)

const me = await call('GET', '/auth/me')
check('/auth/me 返回当前用户', me.status === 200 && me.json?.username === 'demo', `HTTP ${me.status}`)

const dupRegister = await call('POST', '/auth/register', {
  auth: false,
  body: { username: 'demo', email: 'x@y.com', password: '123456' },
})
check('重复用户名注册被拒（409）', dupRegister.status === 409, `HTTP ${dupRegister.status}`)

const badName = await call('POST', '/auth/register', {
  auth: false,
  body: { username: 'a', email: 'x@y.com', password: '123456' },
})
check('用户名过短被拒（400）', badName.status === 400, `HTTP ${badName.status}`)

/* ---------------- 3. 知识库 ---------------- */
const kbList = await call('GET', '/knowledge-bases')
check('知识库列表返回 200', kbList.status === 200 && Array.isArray(kbList.json), `HTTP ${kbList.status}`)
check('演示数据含 3 个知识库', kbList.json?.length === 3, `实际 ${kbList.json?.length}`)
check(
  '知识库字段与 mock 一致（camelCase）',
  hasKeys(kbList.json?.[0] || {}, [
    'id', 'name', 'description', 'documentCount', 'chunkCount', 'embeddingModel', 'createdAt', 'updatedAt',
  ]).ok,
  JSON.stringify(hasKeys(kbList.json?.[0] || {}, ['id', 'name', 'description', 'documentCount', 'chunkCount', 'embeddingModel', 'createdAt', 'updatedAt']).missing || []),
)
check(
  'documentCount 非零（冗余计数已维护）',
  (kbList.json || []).some((kb) => kb.documentCount > 0),
  (kbList.json || []).map((kb) => `${kb.name}:${kb.documentCount}doc/${kb.chunkCount}chunk`).join(' | '),
)

const kbCreated = await call('POST', '/knowledge-bases', {
  body: { name: '契约测试库', description: '由验证脚本创建' },
})
check('新建知识库成功', kbCreated.status === 200 && Boolean(kbCreated.json?.id), `HTTP ${kbCreated.status}`)
const testKbId = kbCreated.json?.id

const kbRenamed = await call('PATCH', `/knowledge-bases/${testKbId}`, { body: { name: '契约测试库-改名' } })
check('重命名知识库成功', kbRenamed.status === 200 && kbRenamed.json?.name === '契约测试库-改名', `HTTP ${kbRenamed.status}`)

/* ---------------- 4. 文档 ---------------- */
const docList = await call('GET', '/documents')
check('文档列表返回 200', docList.status === 200 && Array.isArray(docList.json), `HTTP ${docList.status}`)
check('演示数据含 8 份文档', docList.json?.length === 8, `实际 ${docList.json?.length}`)
check(
  '文档字段与 mock 一致',
  hasKeys(docList.json?.[0] || {}, [
    'id', 'knowledgeBaseId', 'name', 'size', 'chunks', 'status', 'enabled', 'uploadedAt',
  ]).ok,
  JSON.stringify(hasKeys(docList.json?.[0] || {}, ['id', 'knowledgeBaseId', 'name', 'size', 'chunks', 'status', 'enabled', 'uploadedAt']).missing || []),
)
check('文档状态为 ready', (docList.json || []).every((d) => d.status === 'ready'), (docList.json || []).map((d) => d.status).join(','))

const filtered = await call('GET', `/documents?knowledgeBaseId=kb_tech`)
check('按知识库过滤文档', filtered.status === 200 && filtered.json?.length === 3, `实际 ${filtered.json?.length}`)

// 上传一份真实文件，走完整解析 + 向量化链路。
// 注意：后端在异步模式下立即返回 status=processing，向量化在后台进行，
// 因此这里必须轮询等待文档落到 ready，否则后续检索断言必然失败。
const uploadBody = new FormData()
uploadBody.append('file', new Blob(['传智杯契约测试文档。本文件用于验证上传、解析、切片与向量化链路是否正常。系统应当能够检索到这句话：蓝色鲸鱼协议编号是 CZ-2025。'], { type: 'text/plain' }), 'contract-test.txt')
uploadBody.append('knowledgeBaseId', testKbId)
const uploaded = await call('POST', '/documents/upload', { body: uploadBody, raw: true })
check('上传文档成功', uploaded.status === 200 && Boolean(uploaded.json?.id), `HTTP ${uploaded.status} ${uploaded.json?.error || ''}`)
check(
  '上传返回合法状态（processing / pending / ready）',
  ['processing', 'pending', 'ready'].includes(uploaded.json?.status),
  `status=${uploaded.json?.status}`,
)
const testDocId = uploaded.json?.id

/** 轮询等待文档解析完成（最多 60 秒），返回最终文档对象 */
async function waitForReady(documentId, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs
  let last = null
  while (Date.now() < deadline) {
    const probe = await call('GET', `/documents/${documentId}`)
    last = probe.json
    if (last?.status === 'ready' || last?.status === 'failed') return last
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  return last
}

const readyDoc = testDocId ? await waitForReady(testDocId) : null
check(
  '异步解析最终完成（轮询到 ready）',
  readyDoc?.status === 'ready' && readyDoc?.chunks > 0,
  `status=${readyDoc?.status} chunks=${readyDoc?.chunks}${readyDoc?.error ? ' error=' + readyDoc.error : ''}`,
)

if (testDocId) {
  const toggled = await call('PATCH', `/documents/${testDocId}`, { body: { enabled: false } })
  check('停用文档成功', toggled.status === 200 && toggled.json?.enabled === false, `HTTP ${toggled.status}`)
  await call('PATCH', `/documents/${testDocId}`, { body: { enabled: true } })

  const reindexed = await call('POST', `/documents/${testDocId}/reindex`)
  check('重新向量化接口返回 200', reindexed.status === 200, `HTTP ${reindexed.status}`)
  // 重新索引同样走异步链路，需要等待
  const afterReindex = await waitForReady(testDocId)
  check(
    '重新向量化最终完成',
    afterReindex?.status === 'ready' && afterReindex?.chunks > 0,
    `status=${afterReindex?.status} chunks=${afterReindex?.chunks}`,
  )
}

/* ---------------- 5. 会话与消息 ---------------- */
const convList = await call('GET', '/conversations')
check('会话列表返回 200', convList.status === 200 && Array.isArray(convList.json), `HTTP ${convList.status}`)
check(
  '会话字段与 mock 一致',
  hasKeys(convList.json?.[0] || {}, ['id', 'title', 'createdAt', 'updatedAt', 'messageCount', 'knowledgeBaseIds']).ok,
  JSON.stringify(hasKeys(convList.json?.[0] || {}, ['id', 'title', 'createdAt', 'updatedAt', 'messageCount', 'knowledgeBaseIds']).missing || []),
)
check('演示会话含 2 条消息', convList.json?.[0]?.messageCount === 2, `messageCount=${convList.json?.[0]?.messageCount}`)

const messages = await call('GET', '/conversations/conv_demo/messages')
check('消息列表返回 200', messages.status === 200 && Array.isArray(messages.json), `HTTP ${messages.status}`)
check(
  '消息字段与 mock 一致（含 sources）',
  hasKeys(messages.json?.[0] || {}, ['id', 'role', 'content', 'sources', 'createdAt', 'status']).ok,
  `role=${messages.json?.[0]?.role}`,
)
const assistantMsg = (messages.json || []).find((m) => m.role === 'assistant')
check(
  '助手消息带引用来源',
  Array.isArray(assistantMsg?.sources) && assistantMsg.sources.length > 0,
  `sources=${assistantMsg?.sources?.length}`,
)
check(
  '引用字段与 mock 一致',
  hasKeys(assistantMsg?.sources?.[0] || {}, [
    'id', 'documentId', 'documentName', 'knowledgeBaseId', 'knowledgeBaseName', 'score', 'page', 'snippet',
  ]).ok,
  JSON.stringify(hasKeys(assistantMsg?.sources?.[0] || {}, ['id', 'documentId', 'documentName', 'knowledgeBaseId', 'knowledgeBaseName', 'score', 'page', 'snippet']).missing || []),
)

const convCreated = await call('POST', '/conversations', { body: { title: '契约测试会话', knowledgeBaseIds: [testKbId] } })
check('新建会话成功', convCreated.status === 200 && Boolean(convCreated.json?.id), `HTTP ${convCreated.status}`)
check('新建会话回填 knowledgeBaseIds', (convCreated.json?.knowledgeBaseIds || []).includes(testKbId), JSON.stringify(convCreated.json?.knowledgeBaseIds))
const testConvId = convCreated.json?.id

/* ---------------- 6. 流式问答（SSE 契约） ---------------- */
async function readStream(conversationId, content, kbIds) {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
    body: JSON.stringify({ conversationId, content, knowledgeBaseIds: kbIds }),
  })
  const events = []
  if (!res.ok) return { ok: false, status: res.status, events, contentType: '' }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const lines = block.split('\n')
      let eventName = ''
      const dataLines = []
      for (const line of lines) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (!dataLines.length) continue
      try {
        events.push({ event: eventName, data: JSON.parse(dataLines.join('\n')) })
      } catch {
        events.push({ event: eventName, data: null })
      }
    }
  }
  return { ok: true, status: res.status, events, contentType: res.headers.get('content-type') || '' }
}

const stream = await readStream(testConvId, '蓝色鲸鱼协议编号是多少？', [testKbId])
check('SSE 返回 200 且 Content-Type 正确', stream.ok && stream.contentType.includes('text/event-stream'), `HTTP ${stream.status} ct=${stream.contentType}`)
check('推送了 meta 事件', stream.events.some((e) => e.event === 'meta'), `事件序列: ${stream.events.map((e) => e.event).join(',')}`)
check('推送了 sources 事件且先于正文/结束', (() => {
  const si = stream.events.findIndex((e) => e.event === 'sources')
  if (si < 0) return false
  // 未配置大模型时不会产生 delta，此时 sources 应当先于 error/done
  const after = stream.events.findIndex(
    (e, i) => i > si && (e.event === 'delta' || e.event === 'done' || e.event === 'error'),
  )
  return after > si
})(), `事件序列: ${stream.events.map((e) => e.event).join(',')}`)
check('推送了 done 事件且带 messageId', stream.events.some((e) => e.event === 'done' && e.data?.messageId), '')

const sourcesEvent = stream.events.find((e) => e.event === 'sources')
check(
  'sources 事件字段与前端 normalizeStreamEvent 匹配',
  Array.isArray(sourcesEvent?.data?.sources) &&
    hasKeys(sourcesEvent.data.sources[0] || {}, ['id', 'documentName', 'score', 'snippet']).ok,
  `sources=${sourcesEvent?.data?.sources?.length}`,
)

// 检索是否真的命中刚上传的内容
const hit = (sourcesEvent?.data?.sources || []).some((s) => s.documentName === 'contract-test.txt')
check('检索命中刚上传的文档（向量化链路可用）', hit, (sourcesEvent?.data?.sources || []).map((s) => `${s.documentName}@${s.score}`).join(', '))

// 未配置 LLM 时应给出可读的 error 事件，而不是静默失败
const errorEvent = stream.events.find((e) => e.event === 'error')
check(
  '未配置大模型时返回可读 error 事件',
  !errorEvent || /LLM_API_KEY|未配置/.test(errorEvent.data?.message || ''),
  errorEvent ? errorEvent.data.message.slice(0, 60) : '（已配置 LLM，无 error 事件）',
)

// 多轮记忆：第二轮应能带上历史（此处只验证接口可用且回答被持久化）
const after = await call('GET', `/conversations/${testConvId}/messages`)
check('问答后消息已持久化', after.status === 200 && after.json?.length >= 2, `消息数=${after.json?.length}`)

/* ---------------- 7. 清理与错误码 ---------------- */
if (testDocId) {
  const del = await call('DELETE', `/documents/${testDocId}`)
  check('删除文档成功', del.status === 200 && del.json?.ok === true, `HTTP ${del.status}`)
}
if (testConvId) {
  const del = await call('DELETE', `/conversations/${testConvId}`)
  check('删除会话成功', del.status === 200 && del.json?.ok === true, `HTTP ${del.status}`)
}
if (testKbId) {
  const del = await call('DELETE', `/knowledge-bases/${testKbId}`)
  check('删除知识库成功', del.status === 200 && del.json?.ok === true, `HTTP ${del.status}`)
}

const notFound = await call('GET', '/documents/doc_not_exists')
check('不存在的资源返回 404（前端有专门文案）', notFound.status === 404, `HTTP ${notFound.status}`)
const okAfter = await call('GET', '/health', { auth: false })
check('清理后服务仍健康', okAfter.status === 200, `HTTP ${okAfter.status}`)

/* ---------------- 输出 ---------------- */
const pad = (s, n) => String(s).padEnd(n)
console.log('结果'.padEnd(58) + '状态')
console.log('-'.repeat(72))
for (const r of results) {
  console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${pad(r.name, 52)} ${r.ok ? '' : r.note}`)
}
const failed = results.filter((r) => !r.ok)
console.log('-'.repeat(72))
console.log(`${results.length - failed.length}/${results.length} 通过`)
process.exit(failed.length ? 1 : 0)
