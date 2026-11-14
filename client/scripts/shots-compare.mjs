/**
 * 给「论文对比」页面截图。
 * 前置：后端 3000 + 前端 5173 已运行，且已有一份 ready 的对比（demo 账号）。
 * 用法：node scripts/shots-compare.mjs
 */
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = resolve(process.cwd(), '..', 'docs', 'screenshots', 'compare')
mkdirSync(OUT, { recursive: true })

const loginRes = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
})
const loginData = await loginRes.json()
const token = loginData.accessToken || loginData.access_token || loginData.token
if (!token) throw new Error(`登录失败: ${JSON.stringify(loginData).slice(0, 200)}`)
console.log('已获取 token')

const { cdp, close } = await launchBrowser({ debugPort: 9335, windowSize: '1600,1100' })

try {
  await cdp.goto(`${APP}/login`)
  await delay(900)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )

  await cdp.goto(`${APP}/app/compare`)
  await delay(6000)

  await cdp.screenshot(`${OUT}/01-论文对比-结果.png`)
  console.log('已保存 01-论文对比-结果.png')

  // 滚到矩阵位置再拍一张，确保矩阵表格完整可见
  const scrolled = await cdp.evaluate(`(() => {
    const h = [...document.querySelectorAll('h2')].find(x => (x.textContent||'').includes('对比矩阵'));
    if (!h) return 'no-matrix';
    h.scrollIntoView({ block: 'start' });
    return 'ok';
  })()`)
  console.log('滚动到矩阵:', scrolled)
  await delay(1200)
  await cdp.screenshot(`${OUT}/02-对比矩阵.png`)
  console.log('已保存 02-对比矩阵.png')

  const text = await cdp.evaluate(`document.body.innerText.replace(/\\n{2,}/g,'\\n').slice(0, 1200)`)
  console.log('--- 页面文本 ---')
  console.log(text)
} finally {
  close()
}
