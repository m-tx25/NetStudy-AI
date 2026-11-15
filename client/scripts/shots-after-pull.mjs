/**
 * 拉取队友改动后核对：首页 + 上传弹窗（存储限制）。
 * 用法：node scripts/shots-after-pull.mjs
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

const { cdp, close } = await launchBrowser({ debugPort: 9339, windowSize: '1600,1000' })

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
  await cdp.goto(`${APP}/app/knowledge`)
  await delay(3500)

  // 打开上传弹窗
  const opened = await cdp.evaluate(`(() => {
    const btns = [...document.querySelectorAll('button')];
    const target = btns.find(b => /上传/.test(b.textContent || ''));
    if (!target) return 'no-button:' + btns.map(b => (b.textContent||'').trim()).slice(0, 12).join('/');
    target.click();
    return 'ok';
  })()`)
  console.log('打开上传弹窗:', opened)
  await delay(2000)
  await cdp.screenshot(`${OUT}/06-knowledge-upload.png`)
  console.log('已保存 06-knowledge-upload.png')

  const text = await cdp.evaluate(`document.body.innerText.replace(/\\n{2,}/g,'\\n').slice(0, 700)`)
  console.log('--- 页面文本 ---')
  console.log(text)
} finally {
  close()
}
