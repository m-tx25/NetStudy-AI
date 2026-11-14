/**
 * 给「研究助手」页面截图。
 * 前置：后端 3000 + 前端 5173 已运行，且 demo 账号已有一份 ready 的研究报告。
 * 用法：node scripts/shots-research.mjs
 */
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = resolve(process.cwd(), '..', 'docs', 'screenshots', 'research')
mkdirSync(OUT, { recursive: true })

const loginRes = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
})
const loginData = await loginRes.json()
const token = loginData.accessToken || loginData.access_token || loginData.token
if (!token) throw new Error(`登录失败: ${JSON.stringify(loginData).slice(0, 200)}`)

const { cdp, close } = await launchBrowser({ debugPort: 9336, windowSize: '1600,1100' })

try {
  await cdp.goto(`${APP}/login`)
  await delay(900)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )

  await cdp.goto(`${APP}/app/research`)
  await delay(6000)
  await cdp.screenshot(`${OUT}/01-研究助手-方向.png`)
  console.log('已保存 01-研究助手-方向.png')

  for (const [label, index] of [['02-研究问题', 1], ['03-创新空间与计划', 2]]) {
    const result = await cdp.evaluate(`(() => {
      const heads = [...document.querySelectorAll('h2')];
      const target = heads[${index}];
      if (!target) return 'not-found:' + heads.length;
      target.scrollIntoView({ block: 'start' });
      return 'ok';
    })()`)
    console.log(`${label}: ${result}`)
    await delay(1200)
    await cdp.screenshot(`${OUT}/${label}.png`)
    console.log(`已保存 ${label}.png`)
  }

  const scrollCheck = await cdp.evaluate(`(() => {
    const el = document.querySelector('.overflow-y-auto');
    if (!el) return { ok: false, reason: '找不到滚动容器' };
    const before = el.scrollTop;
    el.scrollTop = el.scrollHeight;
    const after = el.scrollTop;
    el.scrollTop = before;
    return { ok: after > before, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
  })()`)
  console.log('滚动检测:', JSON.stringify(scrollCheck))

  const text = await cdp.evaluate(`document.body.innerText.replace(/\\n{2,}/g,'\\n').slice(0, 600)`)
  console.log('--- 页面文本 ---')
  console.log(text)
} finally {
  close()
}
