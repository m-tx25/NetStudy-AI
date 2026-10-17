/**
 * 共享的 CDP（Chrome DevTools Protocol）小工具，供 scripts/ 下的校验脚本复用。
 * 只依赖 Node 18+ 的全局 fetch / WebSocket，无需安装任何依赖。
 */
import { spawn } from 'node:child_process'
import { setTimeout as delay } from 'node:timers/promises'

export const EDGE_CANDIDATES = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
]

export { delay }

/** 从 CDP 的 exceptionDetails 中提取可读错误（text 常只是一句 "Uncaught"）。 */
function _describe(details) {
  const desc =
    details?.exception?.description ||
    details?.exception?.value ||
    details?.text ||
    '未知错误'
  return String(desc).split('\n')[0]
}

export async function getJson(url, attempts = 40) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const res = await fetch(url)
      if (res.ok) return await res.json()
    } catch {
      /* 浏览器/服务还没起来，继续等 */
    }
    await delay(500)
  }
  throw new Error(`无法连接 ${url}`)
}

/** 极简 CDP 客户端 */
export class Cdp {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    this.listeners = []
    ws.addEventListener('message', (event) => {
      const msg = JSON.parse(event.data)
      if (msg.id !== undefined) {
        const entry = this.pending.get(msg.id)
        if (entry) {
          this.pending.delete(msg.id)
          msg.error ? entry.reject(new Error(JSON.stringify(msg.error))) : entry.resolve(msg.result)
        }
        return
      }
      this.listeners.forEach((fn) => fn(msg))
    })
  }

  send(method, params = {}) {
    const id = ++this.id
    this.ws.send(JSON.stringify({ id, method, params }))
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      setTimeout(() => {
        if (this.pending.delete(id)) reject(new Error(`CDP timeout: ${method}`))
      }, 30000)
    })
  }

  on(fn) {
    this.listeners.push(fn)
  }

  /**
   * 按「表达式」求值：expression 必须本身是个值（如 `document.title`）。
   * 不能写 `return xxx` —— 那会报 Illegal return statement。
   */
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    })
    if (result.exceptionDetails) {
      throw new Error(`evaluate failed: ${_describe(result.exceptionDetails)}`)
    }
    return result.result.value
  }

  /**
   * 按「语句」求值：内部自动包一层 IIFE，因此可以写 `return xxx;`
   * 以及多行语句。日常取值用它更顺手。
   */
  async evalStmt(code) {
    return this.evaluate(`(() => { ${code} })()`)
  }

  waitForEvent(method, timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`wait ${method} timeout`)), timeoutMs)
      const fn = (msg) => {
        if (msg.method === method) {
          clearTimeout(timer)
          this.listeners = this.listeners.filter((item) => item !== fn)
          resolve(msg.params)
        }
      }
      this.on(fn)
    })
  }

  async goto(url) {
    await this.send('Page.navigate', { url })
    await this.waitForEvent('Page.loadEventFired')
  }

  async screenshot(filePath) {
    const { data } = await this.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
    const { writeFileSync, mkdirSync } = await import('node:fs')
    const { dirname } = await import('node:path')
    mkdirSync(dirname(filePath), { recursive: true })
    writeFileSync(filePath, Buffer.from(data, 'base64'))
    return filePath
  }
}

/**
 * 启动无头浏览器并连上第一个 page target。
 * @returns {{ process: import('node:child_process').ChildProcess, cdp: Cdp, close: () => void }}
 */
export async function launchBrowser({ debugPort = 9333, windowSize = '1440,900' } = {}) {
  const { existsSync } = await import('node:fs')
  const executable = EDGE_CANDIDATES.find((item) => existsSync(item))
  if (!executable) throw new Error('未找到 Edge / Chrome 可执行文件')

  const child = spawn(
    executable,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      '--hide-scrollbars',
      `--window-size=${windowSize}`,
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${process.env.TEMP}\\rag-cdp-profile-${Date.now()}`,
      'about:blank',
    ],
    { stdio: 'ignore' },
  )

  await getJson(`http://127.0.0.1:${debugPort}/json/version`)
  const targets = await getJson(`http://127.0.0.1:${debugPort}/json/list`)
  const page = targets.find((t) => t.type === 'page')
  if (!page) throw new Error('未找到可用的页面 target')

  const ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true })
    ws.addEventListener('error', () => reject(new Error('WebSocket 连接失败')), { once: true })
  })

  const cdp = new Cdp(ws)
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')

  return {
    process: child,
    cdp,
    close: () => {
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      try {
        child.kill()
      } catch {
        /* ignore */
      }
    },
  }
}
