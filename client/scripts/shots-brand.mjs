/**
 * 截首页 + 侧边栏，确认更名生效。
 * 用法：node scripts/shots-brand.mjs
 */
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = resolve(process.cwd(), '..', 'docs', 'screenshots')
mkdirSync(OUT, { recursive: true })

const loginRes = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
})
const loginData = await loginRes.json()
const token = loginData.accessToken || loginData.access_token || loginData.token

const { cdp, close } = await launchBrowser({ debugPort: 9338, windowSize: '1600,1000' })

try {
  await cdp.goto(`${APP}/`)
  await delay(2500)
  await cdp.screenshot(`${OUT}/00-home.png`)
  console.log('已保存 00-home.png')

  await cdp.goto(`${APP}/login`)
  await delay(800)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )
  await cdp.goto(`${APP}/app/chat`)
  await delay(3500)
  await cdp.screenshot(`${OUT}/05-chat-answer.png`)
  console.log('已保存 05-chat-answer.png')

  const brand = await cdp.evaluate(`(() => {
    const el = document.querySelector('aside');
    return el ? el.innerText.split('\\n').slice(0, 3).join(' | ') : 'no-aside';
  })()`)
  console.log('侧边栏品牌:', brand)
} finally {
  close()
}
