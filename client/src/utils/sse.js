/**
 * SSE（Server-Sent Events）客户端。
 *
 * 为什么不用浏览器原生 EventSource：
 *   1. EventSource 只支持 GET，无法把「问题 + 知识库范围」放进请求体；
 *   2. 无法自定义 Authorization 头；
 *   3. 无法中途 abort（只能 close 后重连）。
 * 因此这里用 fetch + ReadableStream 手工解析 text/event-stream，
 * 既保留流式能力，又能带鉴权头、支持 POST 与主动中断。
 */

/**
 * @param {string} url
 * @param {object} options
 * @param {'GET'|'POST'} [options.method]
 * @param {object} [options.headers]
 * @param {any}    [options.body]       会被 JSON.stringify
 * @param {AbortSignal} [options.signal]
 * @param {(event: {event: string, data: any, raw: string, id?: string}) => void} options.onEvent
 * @returns {Promise<void>} 流结束时 resolve
 */
export async function fetchEventStream(url, options = {}) {
  const { method = 'POST', headers = {}, body, signal, onEvent } = options

  const response = await fetch(url, {
    method,
    headers: {
      Accept: 'text/event-stream',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
    // 某些部署下需要带上 Cookie 会话，可按需改为 include
    credentials: 'same-origin',
  })

  if (!response.ok) {
    throw new Error(await buildHttpError(response))
  }

  const contentType = String(response.headers.get('content-type') || '')

  // 兜底：后端没走 SSE，直接回了一整段 JSON，则退化成「一次性输出」
  if (!contentType.includes('text/event-stream') || !response.body) {
    const text = await response.text()
    emitWholeResponse(text, onEvent)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')

  let pending = ''
  let dataLines = []
  let eventName = ''
  let lastId

  const dispatch = () => {
    const raw = dataLines.join('\n')
    const name = eventName
    dataLines = []
    eventName = ''
    if (!raw) return

    if (raw === '[DONE]') {
      onEvent({ event: 'done', data: { type: 'done' }, raw, id: lastId })
      return
    }

    let data
    try {
      data = JSON.parse(raw)
    } catch {
      data = { content: raw }
    }
    onEvent({ event: name || data?.type || 'message', data, raw, id: lastId })
  }

  const handleLine = (line) => {
    // 空行 = 一个事件结束
    if (line === '') {
      dispatch()
      return
    }
    // 以冒号开头是注释（常用于心跳保活）
    if (line.startsWith(':')) return

    const colonIndex = line.indexOf(':')
    const field = colonIndex === -1 ? line : line.slice(0, colonIndex)
    let value = colonIndex === -1 ? '' : line.slice(colonIndex + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'data') dataLines.push(value)
    else if (field === 'event') eventName = value
    else if (field === 'id') lastId = value
    // retry / 其他字段忽略
  }

  const handleChunk = (chunk, flush = false) => {
    pending += chunk
    const parts = pending.split(/\r\n|\n|\r/)
    if (flush) {
      // 流结束时，最后一段（可能没有换行结尾）也要当成一整行处理
      pending = ''
      for (const line of parts) handleLine(line)
      // 数据行还没有遇到空行时，兜底 dispatch 一次
      dispatch()
    } else {
      pending = parts.pop() ?? ''
      for (const line of parts) handleLine(line)
    }
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      handleChunk(decoder.decode(value, { stream: true }))
    }
    handleChunk(decoder.decode(), true)
  } catch (error) {
    // onEvent 里抛错（例如后端下发 error 事件）时，及时断开底层流
    try {
      await reader.cancel(error)
    } catch {
      /* ignore */
    }
    throw error
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* ignore */
    }
  }
}

function emitWholeResponse(text, onEvent) {
  const trimmed = text.trim()
  if (!trimmed) return

  // 可能是 SSE 文本但没带正确 content-type，这里再兜底解析一次
  if (trimmed.startsWith('data:') || trimmed.startsWith('event:')) {
    for (const block of trimmed.split(/\r?\n\r?\n/)) {
      const dataLines = []
      let eventName = ''
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
        else if (line.startsWith('event:')) eventName = line.slice(6).trim()
      }
      if (!dataLines.length) continue
      const raw = dataLines.join('\n')
      let data
      try {
        data = JSON.parse(raw)
      } catch {
        data = { content: raw }
      }
      onEvent({ event: eventName || data?.type || 'message', data, raw })
    }
    return
  }

  let data
  try {
    data = JSON.parse(trimmed)
  } catch {
    data = { content: trimmed }
  }
  onEvent({ event: 'message', data, raw: trimmed })
}

async function buildHttpError(response) {
  let detail = ''
  try {
    const text = await response.text()
    if (text) {
      try {
        const json = JSON.parse(text)
        detail = json.message || json.error || text
      } catch {
        detail = text
      }
    }
  } catch {
    /* ignore */
  }
  const suffix = detail ? `：${String(detail).slice(0, 200)}` : ''
  if (response.status === 401) return `登录状态已失效，请重新登录${suffix}`
  if (response.status === 404) return `流式接口不存在（404）${suffix}`
  return `流式请求失败（HTTP ${response.status}）${suffix}`
}
