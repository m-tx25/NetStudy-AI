/**
 * 截图：聊天页「知识库」选择器里团队库的标记。
 * 前置：后端 3000 + 前端 5173 已运行。
 * 用法：node scripts/shots-kb-selector.mjs
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
const data = await loginRes.json()
const token = data.accessToken || data.access_token || data.token
if (!token) throw new Error('登录失败')

const { cdp, close } = await launchBrowser({ debugPort: 9335, windowSize: '1440,960' })

try {
  await cdp.goto(`${APP}/login`)
  await delay(800)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )

  await cdp.goto(`${APP}/app/chat`)
  await delay(3000)

  // 点开输入框上方那颗「知识库」按钮（侧边栏是「知识库管理」，要精确匹配）
  const opened = await cdp.evaluate(`(() => {
    const btn = [...document.querySelectorAll('button')]
      .find(b => (b.textContent || '').trim().replace(/\\s+/g, '').replace(/^知识库\\d+$/, '知识库') === '知识库');
    if (!btn) {
      return 'no-button:' + [...document.querySelectorAll('button')]
        .map(b => (b.textContent || '').trim()).filter(Boolean).slice(0, 12).join('|');
    }
    btn.click();
    return 'ok';
  })()`)
  console.log('打开选择器:', opened)
  await delay(2200)

  await cdp.screenshot(`${OUT}/10-知识库选择器.png`)
  console.log('已保存 10-知识库选择器.png')

  const text = await cdp.evaluate(`(() => {
    const p = document.querySelector('.rag-kb-popover');
    return p ? p.innerText.replace(/\\n{2,}/g,'\\n') : document.body.innerText.slice(0,500);
  })()`)
  console.log('--- 弹层文本 ---')
  console.log(text)
} finally {
  close()
}
