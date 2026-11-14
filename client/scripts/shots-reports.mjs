/**
 * 给「成果导出」页面截图。
 * 前置：后端 3000 + 前端 5173 已运行，demo 账号已有 ready 的报告。
 * 用法：node scripts/shots-reports.mjs
 */
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = resolve(process.cwd(), '..', 'docs', 'screenshots', 'reports')
mkdirSync(OUT, { recursive: true })

const loginRes = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
})
const loginData = await loginRes.json()
const token = loginData.accessToken || loginData.access_token || loginData.token
if (!token) throw new Error(`登录失败: ${JSON.stringify(loginData).slice(0, 200)}`)

const { cdp, close } = await launchBrowser({ debugPort: 9337, windowSize: '1600,1100' })

try {
  await cdp.goto(`${APP}/login`)
  await delay(900)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )

  await cdp.goto(`${APP}/app/reports`)
  await delay(6000)
  await cdp.screenshot(`${OUT}/01-成果导出-报告预览.png`)
  console.log('已保存 01-成果导出-报告预览.png')

  const scrolled = await cdp.evaluate(`(() => {
    const head = [...document.querySelectorAll('h2')].find(x => (x.textContent||'').includes('参考文献'));
    if (!head) return 'no-refs';
    head.scrollIntoView({ block: 'center' });
    return 'ok';
  })()`)
  console.log('滚动到参考文献:', scrolled)
  await delay(1200)
  await cdp.screenshot(`${OUT}/02-参考文献格式.png`)
  console.log('已保存 02-参考文献格式.png')

  const scrollCheck = await cdp.evaluate(`(() => {
    const el = document.querySelector('.overflow-y-auto');
    if (!el) return { ok: false };
    const before = el.scrollTop;
    el.scrollTop = el.scrollHeight;
    const after = el.scrollTop;
    el.scrollTop = before;
    return { ok: after > before, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
  })()`)
  console.log('滚动检测:', JSON.stringify(scrollCheck))
} finally {
  close()
}
