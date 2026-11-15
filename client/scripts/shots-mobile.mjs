/** 手机尺寸截图：看现有响应式到什么程度。 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = 'E:/传智杯web/docs/screenshots/mobile'

const login = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
}).then((r) => r.json())
const token = login.accessToken || login.access_token || login.token

// iPhone 12/13 逻辑分辨率
const { cdp, close } = await launchBrowser({ debugPort: 9360, windowSize: '390,844' })
try {
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 844,
    deviceScaleFactor: 2,
    mobile: true,
  })
  await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 })

  for (const [name, path] of [
    ['01-home', '/'],
    ['02-chat', '/app/chat'],
    ['03-compare', '/app/compare'],
  ]) {
    if (name === '02-chat') {
      await cdp.goto(`${APP}/login`)
      await delay(600)
      await cdp.evaluate(
        `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
         localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
         true`,
      )
    }
    await cdp.goto(`${APP}${path}?t=${Date.now()}`)
    await delay(3000)
    await cdp.screenshot(`${OUT}/${name}.png`)
    const info = await cdp.evaluate(`(() => ({
      w: innerWidth,
      h: innerHeight,
      scrollW: document.documentElement.scrollWidth,
      overflow: document.documentElement.scrollWidth > innerWidth + 2,
      sidebarVisible: !!document.querySelector('aside') &&
        getComputedStyle(document.querySelector('aside')).display !== 'none',
    }))()`)
    console.log(name, JSON.stringify(info))
  }
} finally {
  close()
}
