/** 诊断线上页面：控制台错误、失败请求、渲染结果。 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const SITE = process.env.SITE_URL || 'http://8.163.132.51'
const { cdp, close } = await launchBrowser({ debugPort: 9352, windowSize: '1600,1000' })

const logs = []
const failed = []
const badResponses = []

// cdp.on 只接受单个回调，自己按 method 分发
cdp.on((msg) => {
  if (msg.method === 'Runtime.exceptionThrown') {
    const d = msg.params.exceptionDetails || {}
    logs.push(`[exception] ${d.exception?.description || d.text}`)
  } else if (msg.method === 'Runtime.consoleAPICalled') {
    const args = (msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ')
    logs.push(`[console.${msg.params.type}] ${args}`)
  } else if (msg.method === 'Network.loadingFailed') {
    failed.push(`${msg.params.errorText} (${msg.params.type})`)
  } else if (msg.method === 'Network.responseReceived') {
    const r = msg.params.response
    if (r.status >= 400) badResponses.push(`${r.status} ${r.url}`)
  }
})

try {
  await cdp.send('Runtime.enable')
  await cdp.send('Network.enable')
  await cdp.goto(`${SITE}/?t=${Date.now()}`)
  await delay(4000)

  const state = await cdp.evaluate(`(() => ({
    url: location.href,
    htmlLength: document.documentElement.outerHTML.length,
    bodyText: (document.body.innerText || '').slice(0, 200),
    appEl: !!document.querySelector('#app'),
    appChildren: (document.querySelector('#app') || {}).childElementCount,
    bodyBg: getComputedStyle(document.body).backgroundColor,
    scripts: [...document.scripts].map(s => s.src).filter(Boolean),
  }))()`)
  console.log('页面状态:', JSON.stringify(state, null, 2))
  console.log('失败请求:', failed.length ? failed : '无')
  console.log('4xx/5xx:', badResponses.length ? badResponses : '无')
  console.log('日志:')
  for (const line of logs.slice(0, 15)) console.log('  ' + line)
  if (!logs.length) console.log('  （无）')
} finally {
  close()
}
