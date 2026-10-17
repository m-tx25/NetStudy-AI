/**
 * 验证「模型选择」与「非知识库依据标注」已接到界面。
 * 前置：后端(3000) + 前端(5173) 已启动。
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.argv[2] || 'http://localhost:5173'
const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  -> ${detail}` : ''}`)
}

const browser = await launchBrowser({ debugPort: 9448, windowSize: '1440,1000' })
const { cdp } = browser

try {
  const calls = []
  cdp.on((msg) => {
    if (msg.method === 'Network.requestWillBeSent') {
      const url = String(msg.params?.request?.url || '')
      if (!url.includes('/api/')) return
      const path = url.split('/api/')[1]
      if (/\.(js|ts|vue|mjs|css)(\?|$)/.test(path)) return
      calls.push(path)
    }
  })
  await cdp.send('Network.enable')

  // 登录
  await cdp.goto(`${APP}/login`)
  await delay(1500)
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
  await delay(3500)

  check(
    '前端调用了模型清单接口',
    calls.some((c) => c.startsWith('chat/models')),
    calls.filter((c) => c.startsWith('chat/')).join(', ') || '未调用',
  )
  check(
    '前端调用了 RAG 配置接口',
    calls.some((c) => c.startsWith('chat/config')),
    '',
  )

  // 界面是否出现模型选择器
  const ui = await cdp.evaluate(`(() => {
    const buttons = [...document.querySelectorAll('button')]
    const modelBtn = buttons.find((b) => (b.getAttribute('title') || '').includes('当前生成模型'))
    const kbBtn = buttons.find((b) => (b.innerText || '').trim().startsWith('知识库'))
    return {
      hasModelButton: Boolean(modelBtn),
      modelText: modelBtn ? modelBtn.innerText.trim() : '',
      hasKbButton: Boolean(kbBtn),
    }
  })()`)
  check('头部出现模型选择器', ui.hasModelButton === true, `显示为「${ui.modelText}」`)
  check('知识库选择器仍在（两者并存）', ui.hasKbButton === true)

  // 打开下拉，确认列出多个模型
  const opened = await cdp.evaluate(`(() => {
    const btn = [...document.querySelectorAll('button')]
      .find((b) => (b.getAttribute('title') || '').includes('当前生成模型'))
    if (!btn) return false
    btn.click()
    return true
  })()`)
  check('可以点开模型下拉', opened === true)
  await delay(1200)

  const panel = await cdp.evaluate(`(() => {
    const text = document.body.innerText
    return {
      hasTitle: text.includes('生成模型'),
      hasDefault: text.includes('默认'),
      hasLocalHint: text.includes('本地部署') || text.includes('API'),
      hasFallbackNote: text.includes('非知识库依据') || text.includes('严格模式'),
    }
  })()`)
  check('下拉面板列出模型', panel.hasTitle === true)
  check('展示了模型来源提示（本地/API）', panel.hasLocalHint === true)
  check('说明了无依据时的回退策略', panel.hasFallbackNote === true)

  await cdp.screenshot('D:/chuangzhibei/docs/screenshots/model-selector.png')
  console.log('\n截图：docs/screenshots/model-selector.png')
} catch (error) {
  check('测试执行未抛异常', false, String(error?.message || error))
} finally {
  browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${'='.repeat(60)}\n${results.length - failed.length}/${results.length} 通过`)
process.exit(failed.length ? 1 : 0)
