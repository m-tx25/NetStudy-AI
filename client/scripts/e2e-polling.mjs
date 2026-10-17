/**
 * 专门验证「文档解析状态轮询」——针对 client/src/stores/knowledge.js 的改动。
 *
 * 前置：
 *   1. 后端已启动（端口 3000）
 *   2. 前端以真实接口模式启动：VITE_USE_MOCK=false npm run dev
 *   3. 后端建议设置 PIPELINE_ARTIFICIAL_DELAY_SECONDS=12，以便观察到「解析中」阶段
 *
 * 运行：
 *   node e2e-polling.mjs [前端地址] [后端地址]
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP_ORIGIN = process.argv[2] || process.env.APP_ORIGIN || 'http://localhost:5174'
const API_ORIGIN = process.argv[3] || process.env.API_ORIGIN || 'http://127.0.0.1:3000'

const results = []
function check(name, ok, detail = '') {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  -> ${detail}` : ''}`)
}

/** 注入页面的通用工具 */
const HELPERS = `
  const setValue = (el, value) => {
    if (!el) return false
    const proto = el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  }
  const clickByText = (text) => {
    const el = [...document.querySelectorAll('button, a, li, span')]
      .find((node) => node.innerText && node.innerText.trim() === text)
      || [...document.querySelectorAll('button')]
        .find((node) => (node.innerText || '').includes(text))
    if (el) el.click()
    return !!el
  }
  /** 表格里某文档名所在行是否显示某状态文案 */
  const rowStatus = (fileName, statusText) => {
    const rows = [...document.querySelectorAll('tr')]
    const row = rows.find((tr) => (tr.innerText || '').includes(fileName))
    if (!row) return null
    return (row.innerText || '').includes(statusText)
  }
  /** 该行的「重新索引」按钮是否被禁用（processing 时前端会禁用）
   *  注意：该按钮是图标按钮（el-button + Refresh 图标），没有文字，
   *  因此按「行内最后一个按钮」定位，而不是按文本匹配。 */
  const rowReindexDisabled = (fileName) => {
    const rows = [...document.querySelectorAll('tr')]
    const row = rows.find((tr) => (tr.innerText || '').includes(fileName))
    if (!row) return null
    const buttons = [...row.querySelectorAll('button')]
    if (!buttons.length) return null
    // 行内按钮顺序：参与检索开关、重新索引、删除 → 取倒数第二个
    const btn = buttons.length >= 2 ? buttons[buttons.length - 2] : buttons[buttons.length - 1]
    return btn.disabled === true
  }
  /** 行内按钮总数，便于诊断 */
  const rowButtonCount = (fileName) => {
    const rows = [...document.querySelectorAll('tr')]
    const row = rows.find((tr) => (tr.innerText || '').includes(fileName))
    return row ? row.querySelectorAll('button').length : null
  }
`

const FILE_NAME = `polling-test-${Date.now()}.md`
const FILE_CONTENT = `# 轮询验证文档

本文档用于验证前端「解析中 → 已就绪」的状态轮询是否生效。

关键标记：翠绿色羚羊协议编号是 POLL-9527。

## 章节二
补充内容，确保切片数量大于一，便于观察 chunks 字段变化。
`

const browser = await launchBrowser({ debugPort: 9444, windowSize: '1440,1000' })
const { cdp } = browser

try {
  /* ---------------- 统计轮询请求 ---------------- */
  const documentRequests = []
  cdp.on((msg) => {
    if (msg.method === 'Network.requestWillBeSent') {
      const url = String(msg.params?.request?.url || '')
      if (url.includes('/api/documents') && !url.includes('/upload')) {
        documentRequests.push({ url, t: Date.now() })
      }
    }
  })
  await cdp.send('Network.enable')

  /* ---------------- 1. 登录 ---------------- */
  await cdp.goto(`${APP_ORIGIN}/login`)
  await delay(1200)
  const loginSubmit = await cdp.evaluate(`(() => {
    ${HELPERS}
    setValue(document.querySelector('input[autocomplete="username"]'), 'demo')
    setValue(document.querySelector('input[autocomplete="current-password"]'), '123456')
    return clickByText('登 录')
  })()`)
  check('提交登录表单', loginSubmit === true)
  await delay(2500)

  const afterLogin = await cdp.evaluate(`(() => ({
    path: location.pathname,
    token: localStorage.getItem('rag.access_token') ? 'yes' : 'no',
  }))()`)
  check('登录成功并拿到 token', afterLogin.token === 'yes', `path=${afterLogin.path}`)
  check('未停留在登录页', afterLogin.path !== '/login', `path=${afterLogin.path}`)

  /* ---------------- 2. 进入知识库页 ---------------- */
  await cdp.evaluate(`history.pushState({}, '', '/knowledge')`)
  await cdp.evaluate(`window.dispatchEvent(new PopStateEvent('popstate'))`)
  await delay(2500)

  const kbProbe = await cdp.evaluate(`(() => ({
    hasTitle: document.body.innerText.includes('知识库管理'),
    tableRows: document.querySelectorAll('table tr').length,
  }))()`)
  check('知识库页渲染', kbProbe.hasTitle === true)
  check('文档表格已渲染', kbProbe.tableRows > 1, `${kbProbe.tableRows} 行`)

  /* ---------------- 3. 打开上传弹窗 ---------------- */
  const opened = await cdp.evaluate(`(() => {
    ${HELPERS}
    return clickByText('上传文档')
  })()`)
  check('打开发上传弹窗', opened === true)
  await delay(1200)

  const hasUploader = await cdp.evaluate(
    `!!document.querySelector('input[type="file"]')`,
  )
  check('弹窗内存在文件选择控件', hasUploader === true)

  /* ---------------- 4. 注入文件 ---------------- */
  const injected = await cdp.evaluate(`(() => {
    const input = document.querySelector('input[type="file"]')
    if (!input) return false
    const file = new File([${JSON.stringify(FILE_CONTENT)}], ${JSON.stringify(FILE_NAME)}, { type: 'text/markdown' })
    const dt = new DataTransfer()
    dt.items.add(file)
    input.files = dt.files
    input.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  })()`)
  check('向文件控件注入文件', injected === true)
  await delay(1000)

  const filePicked = await cdp.evaluate(
    `document.body.innerText.includes(${JSON.stringify(FILE_NAME)})`,
  )
  check('弹窗内显示所选文件', filePicked === true)

  /* ---------------- 5. 提交上传并开始观察 ---------------- */
  const submitted = await cdp.evaluate(`(() => {
    ${HELPERS}
    return clickByText('开始上传')
  })()`)
  check('点击开始上传', submitted === true)

  const requestsBeforeUploadFinished = documentRequests.length

  // 等待列表中出现该文档（上传接口返回后才会插入）
  let appeared = false
  for (let i = 0; i < 30; i += 1) {
    await delay(1000)
    const probe = await cdp.evaluate(
      `document.body.innerText.includes(${JSON.stringify(FILE_NAME)})`,
    )
    if (probe) {
      appeared = true
      break
    }
  }
  check('上传后列表出现该文档', appeared === true)

  // 关闭弹窗，便于观察表格
  await cdp.evaluate(`(() => {
    ${HELPERS}
    const cancel = [...document.querySelectorAll('button')].find((b) => (b.innerText || '').trim() === '取消')
    if (cancel) cancel.click()
  })()`)
  await delay(800)

  /* ---------------- 6. 关键断言：是否显示「解析中」 ---------------- */
  let sawProcessing = false
  const processingDeadline = Date.now() + 15000
  while (Date.now() < processingDeadline) {
    const state = await cdp.evaluate(`(() => {
      ${HELPERS}
      return {
        processing: rowStatus(${JSON.stringify(FILE_NAME)}, '解析中'),
        ready: rowStatus(${JSON.stringify(FILE_NAME)}, '已就绪'),
      }
    })()`)
    if (state.processing === true || state.ready === true) {
      sawProcessing = state.processing === true
      break
    }
    await delay(500)
  }
  check(
    '处于「解析中」状态（后端已配置解析延迟）',
    sawProcessing === true,
    sawProcessing ? '' : '未观察到解析中（可能后端未配置延迟）',
  )

  const disabledWhileProcessing = await cdp.evaluate(`(() => {
    ${HELPERS}
    return rowReindexDisabled(${JSON.stringify(FILE_NAME)})
  })()`)

  const requestsAtProcessing = documentRequests.length

  /* ---------------- 7. 核心：不刷新页面，等待自动变为「已就绪」 ---------------- */
  let becameReady = false
  let firstReadyAt = 0
  const readyDeadline = Date.now() + 40000
  while (Date.now() < readyDeadline) {
    const ready = await cdp.evaluate(`(() => {
      ${HELPERS}
      return rowStatus(${JSON.stringify(FILE_NAME)}, '已就绪')
    })()`)
    if (ready === true) {
      becameReady = true
      firstReadyAt = Date.now()
      break
    }
    await delay(1000)
  }
  check('无需刷新页面，状态自动变为「已就绪」', becameReady === true)

  const requestsAtReady = documentRequests.length
  const pollCount = requestsAtReady - requestsAtProcessing
  check(
    '轮询确实发出了文档列表请求',
    pollCount >= 1,
    `解析期间共发出 ${pollCount} 次 /api/documents 请求`,
  )

  const disabledAfterReady = await cdp.evaluate(`(() => {
    ${HELPERS}
    return rowReindexDisabled(${JSON.stringify(FILE_NAME)})
  })()`)
  check(
    '就绪后「重新索引」按钮恢复可用',
    disabledAfterReady === false,
    `解析中时 disabled=${disabledWhileProcessing}，就绪后 disabled=${disabledAfterReady}`,
  )

  /* ---------------- 8. 轮询应当停止 ---------------- */
  await delay(8000)
  const requestsAfterStop = documentRequests.length
  const extraAfterReady = requestsAfterStop - requestsAtReady
  check(
    '到达终态后自动停止轮询',
    extraAfterReady <= 1,
    `就绪后又发出 ${extraAfterReady} 次请求（应为 0，容差 1 次在途请求）`,
  )
  check(
    '页面未被刷新（单页状态保持）',
    firstReadyAt > 0 && Date.now() > firstReadyAt,
    '',
  )

  const total = documentRequests.length - requestsBeforeUploadFinished
  console.log(`\n本次共观测到 /api/documents 请求 ${total} 次（含首次加载）`)
  await cdp.screenshot('D:/chuangzhibei/docs/screenshots/polling-verify.png')
  console.log('截图已保存：docs/screenshots/polling-verify.png')
} catch (error) {
  check('测试执行未抛异常', false, String(error?.message || error))
} finally {
  browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${'='.repeat(64)}`)
console.log(`${results.length - failed.length}/${results.length} 通过`)
process.exit(failed.length ? 1 : 0)
