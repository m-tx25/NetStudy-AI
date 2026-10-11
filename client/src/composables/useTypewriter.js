/**
 * 打字机效果。
 *
 * 后端 SSE 的数据块大小并不均匀（有时一次 1 个字，有时一次一整段），
 * 直接 append 会出现「一顿一顿」的观感。这里加一个字符缓冲队列，
 * 按固定节奏匀速吐出，并按积压量自动加速，保证既不卡顿也不会越落越远。
 */
export function createTypewriter(options = {}) {
  const {
    onUpdate = () => {},
    interval = 16,
    // 每 tick 最少/最多吐出的字符数
    minStep = 1,
    maxStep = 24,
    // 积压到多少字符开始加速
    rampAt = 40,
  } = options

  let buffer = ''
  let timer = null
  let stopped = false

  function stepSize() {
    if (buffer.length <= rampAt) return minStep
    const scaled = Math.ceil(buffer.length / rampAt)
    return Math.min(maxStep, Math.max(minStep, scaled))
  }

  function tick() {
    if (stopped) return
    if (!buffer) {
      timer = null
      return
    }
    const size = stepSize()
    onUpdate(buffer.slice(0, size))
    buffer = buffer.slice(size)
    timer = setTimeout(tick, interval)
  }

  return {
    /** 追加一段来自 SSE 的增量文本 */
    push(text) {
      if (stopped || !text) return
      buffer += text
      if (timer === null) timer = setTimeout(tick, interval)
    },
    /** 立刻把剩余内容一次性吐完（用户点「停止生成」时用） */
    flush() {
      if (buffer) {
        onUpdate(buffer)
        buffer = ''
      }
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
    },
    /** 等待缓冲区清空 */
    drain() {
      if (!buffer) return Promise.resolve()
      return new Promise((resolve) => {
        const check = () => {
          if (stopped || !buffer) resolve()
          else setTimeout(check, 16)
        }
        check()
      })
    },
    stop() {
      stopped = true
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
      buffer = ''
    },
    get pending() {
      return buffer.length
    },
  }
}
