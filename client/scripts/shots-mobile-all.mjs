/** 手机尺寸批量截图：一次看全 11 个页面在 390px 下的表现。 */
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

const PAGES = [
  ['01-home', '/', false],
  ['02-login', '/login', false],
  ['03-chat', '/app/chat', true],
  ['04-compare', '/app/compare', true],
  ['05-research', '/app/research', true],
  ['06-reports', '/app/reports', true],
  ['07-search', '/app/search', true],
  ['08-library', '/app/library', true],
  ['09-knowledge', '/app/knowledge', true],
  ['10-teams', '/app/teams', true],
  ['11-settings', '/app/settings', true],
]

const { cdp, close } = await launchBrowser({ debugPort: 9361, windowSize: '390,844' })
try {
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 390, height: 844, deviceScaleFactor: 2, mobile: true,
  })
  await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 })

  await cdp.goto(`${APP}/login`)
  await delay(600)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )

  for (const [name, path] of PAGES) {
    await cdp.goto(`${APP}${path}?t=${Date.now()}`)
    await delay(2800)
    await cdp.screenshot(`${OUT}/${name}.png`)

    const info = await cdp.evaluate(`(() => {
      const de = document.documentElement;
      const overflow = de.scrollWidth > innerWidth + 2;
      // 找最宽的元素，定位横向溢出的元凶
      let worst = null;
      if (overflow) {
        for (const el of document.querySelectorAll('*')) {
          const r = el.getBoundingClientRect();
          if (r.width > innerWidth + 4 && (!worst || r.width > worst.w)) {
            worst = { w: Math.round(r.width), tag: el.tagName, cls: (el.className || '').toString().slice(0, 60) };
          }
        }
      }
      // 小于 40px 的可点区域（手机上难点）
      const small = [...document.querySelectorAll('button, a')].filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.height < 36;
      }).length;
      return { overflow, scrollW: de.scrollWidth, worst, small };
    })()`)
    console.log(`${name.padEnd(12)} overflow=${info.overflow} scrollW=${info.scrollW} smallTap=${info.small} ${info.worst ? 'width=' + info.worst.w + ' <' + info.worst.tag + ' class=' + info.worst.cls + '>' : ''}`)
  }
} finally {
  close()
}
