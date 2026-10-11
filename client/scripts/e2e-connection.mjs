/**
 * 验证前端(5173)已连接真实后端：登录、加载真实数据、调用真实接口。
 * 与 mock 模式的区别：mock 模式下 localStorage 里会有 rag.mock.db.v1，且不发 /api 请求。
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP_ORIGIN = process.argv[2] || 'http://localhost:5173'
const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  -> ${detail}` : ''}`)
}

const browser = await launchBrowser({ debugPort: 9446 })
const { cdp } = browser

try {
  const apiCalls = []
  cdp.on((msg) => {
    if (msg.method === 'Network.requestWillBeSent') {
      const url = String(msg.params?.request?.url || '')
      if (!url.includes('/api/')) return
      const path = url.split('/api/')[1]
      // 排除 Vite 加载前端源码模块（src/api/*.js 会被解析为 /api/*.js）
      if (/\.(js|ts|vue|mjs|css)(\?|$)/.test(path)) return
      apiCalls.push({ url: path, t: Date.now() })
    }
  })
  await cdp.send('Network.enable')

  await cdp.goto(`${APP_ORIGIN}/login`)
  await delay(1500)

  const boot = await cdp.evaluate(`(() => ({
    path: location.pathname,
    hasMockDb: localStorage.getItem('rag.mock.db.v1') !== null,
    apiCallsSoFar: ${apiCalls.length},
  }))()`)
  check('登录页可访问', boot.path === '/login', `path=${boot.path}`)

  // 登录
  await cdp.evaluate(`(() => {
    const setValue = (el, v) => {
      if (!el) return false
      const proto = window.HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
      return true
    }
    setValue(document.querySelector('input[autocomplete="username"]'), 'demo')
    setValue(document.querySelector('input[autocomplete="current-password"]'), '123456')
    const btn = [...document.querySelectorAll('button')].find((b) => (b.innerText || '').includes('登'))
    if (btn) btn.click()
    return true
  })()`)
  await delay(3000)

  const loginCalls = apiCalls.filter((c) => c.url.startsWith('auth/login'))
  check('登录请求打到真实后端 /api/auth/login', loginCalls.length >= 1, `命中 ${loginCalls.length} 次`)

  const afterLogin = await cdp.evaluate(`(() => ({
    path: location.pathname,
    token: localStorage.getItem('rag.access_token') ? 'yes' : 'no',
    hasMockDb: localStorage.getItem('rag.mock.db.v1') !== null,
  }))()`)
  check('登录成功（拿到真实 JWT）', afterLogin.token === 'yes', `path=${afterLogin.path}`)
  check('未使用内置 Mock 数据', afterLogin.hasMockDb === false, `存在 rag.mock.db.v1=${afterLogin.hasMockDb}`)

  // 进入知识库页，验证读到的是后端真实数据
  await cdp.evaluate(`history.pushState({}, '', '/knowledge')`)
  await cdp.evaluate(`window.dispatchEvent(new PopStateEvent('popstate'))`)
  await delay(3000)

  const kbCalls = apiCalls.filter((c) => c.url.startsWith('knowledge-bases') || c.url.startsWith('documents'))
  check('知识库/文档数据来自后端', kbCalls.length >= 2, `命中 ${kbCalls.length} 次`)

  const kbProbe = await cdp.evaluate(`(() => {
    const text = document.body.innerText
    return {
      hasTitle: text.includes('知识库管理'),
      // 演示数据中的真实知识库名
      hasTech: text.includes('技术文档库'),
      hasHr: text.includes('规章制度库'),
      hasProduct: text.includes('产品需求文档库'),
      // mock 独有的假文档名（已从种子数据移除）
      hasMockOnlyDoc: text.includes('需求规格说明书_v2.pdf') && !text.includes('.md'),
    }
  })()`)
  check('页面渲染出后端种子数据（三个知识库）',
    kbProbe.hasTitle && kbProbe.hasTech && kbProbe.hasHr && kbProbe.hasProduct,
    JSON.stringify({ tech: kbProbe.hasTech, hr: kbProbe.hasHr, product: kbProbe.hasProduct }))

  // 问答页：验证会话/消息来自后端
  await cdp.evaluate(`history.pushState({}, '', '/chat')`)
  await cdp.evaluate(`window.dispatchEvent(new PopStateEvent('popstate'))`)
  await delay(3000)
  const convCalls = apiCalls.filter((c) => c.url.startsWith('conversations'))
  check('会话数据来自后端', convCalls.length >= 1, `命中 ${convCalls.length} 次`)

  check('全过程共发出真实 API 请求', apiCalls.length >= 4, `${apiCalls.length} 次`)

  console.log('\n实际请求的后端接口：')
  const seen = new Set()
  for (const call of apiCalls) {
    const key = call.url.split('?')[0]
    if (!seen.has(key)) {
      seen.add(key)
      console.log('  · /api/' + key)
    }
  }

  await cdp.screenshot('D:/chuangzhibei/docs/screenshots/frontend-connected.png')
  console.log('\n截图已保存：docs/screenshots/frontend-connected.png')
} catch (error) {
  check('测试执行未抛异常', false, String(error?.message || error))
} finally {
  browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${'='.repeat(60)}`)
console.log(`${results.length - failed.length}/${results.length} 通过`)
process.exit(failed.length ? 1 : 0)
