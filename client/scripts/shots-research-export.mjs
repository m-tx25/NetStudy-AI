/** 截研究助手页，确认三个导出按钮。 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = 'E:/传智杯web/docs/screenshots/research'

const login = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
}).then((r) => r.json())
const token = login.accessToken || login.access_token || login.token

const { cdp, close } = await launchBrowser({ debugPort: 9343, windowSize: '1600,1000' })
try {
  await cdp.goto(`${APP}/login`)
  await delay(700)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )
  await cdp.goto(`${APP}/app/research?t=${Date.now()}`)
  await delay(5000)
  await cdp.screenshot(`${OUT}/01-研究助手-方向.png`)
  console.log('已保存 01-研究助手-方向.png')

  const buttons = await cdp.evaluate(`(() => {
    const btns = [...document.querySelectorAll('header button')].map(b => (b.textContent||'').trim());
    return btns.filter(Boolean).join(' | ');
  })()`)
  console.log('顶部按钮:', buttons)
} finally {
  close()
}
