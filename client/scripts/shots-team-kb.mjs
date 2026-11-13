/**
 * 给「团队 → 知识库」新面板截图。
 * 前置：后端 3000 + 前端 5173 已运行。
 * 用法：node scripts/shots-team-kb.mjs
 *
 * 登录方式：先调 API 拿 token，再写 localStorage（比填表单稳，与 shots-teams.mjs 一致）
 */
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = resolve(process.cwd(), '..', 'docs', 'screenshots', 'teams')
mkdirSync(OUT, { recursive: true })

// 1) 用 demo 账号登录拿 token
const loginRes = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
})
const loginData = await loginRes.json()
const token = loginData.accessToken || loginData.access_token || loginData.token
if (!token) throw new Error(`登录失败: ${JSON.stringify(loginData).slice(0, 200)}`)
console.log('已获取 token')

const { cdp, close } = await launchBrowser({ debugPort: 9334, windowSize: '1440,960' })

try {
  await cdp.goto(`${APP}/login`)
  await delay(900)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )

  // 2) 团队页
  await cdp.goto(`${APP}/app/teams`)
  await delay(2800)

  // 3) 进入第一个团队详情
  const openResult = await cdp.evaluate(`(() => {
    const cards = [...document.querySelectorAll('article')];
    if (!cards.length) return 'no-article';
    cards[0].click();
    return 'clicked:' + cards.length;
  })()`)
  console.log('进入团队详情:', openResult)
  await delay(2600)

  // 4) 切到「知识库」Tab
  const tabResult = await cdp.evaluate(`(() => {
    const tabs = [...document.querySelectorAll('.el-tabs__item')];
    const labels = tabs.map(t => (t.textContent || '').trim());
    const tab = tabs.find(t => (t.textContent || '').trim() === '知识库');
    if (!tab) return 'not-found:' + JSON.stringify(labels);
    tab.click();
    return 'ok';
  })()`)
  console.log('切换知识库 Tab:', tabResult)
  await delay(6000)

  await cdp.screenshot(`${OUT}/09-团队知识库.png`)
  console.log('已保存 09-团队知识库.png')

  const text = await cdp.evaluate(`document.body.innerText.replace(/\\n{2,}/g,'\\n').slice(-700)`)
  console.log('--- 页面文本 ---')
  console.log(text)
} finally {
  close()
}
