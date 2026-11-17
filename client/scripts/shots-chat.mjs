/** 真发一个问题，等回答出来（带引用）再截图。 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = 'E:/传智杯web/docs/screenshots'
const QUESTION = process.env.QUESTION || '什么是 Naive RAG？它和 Advanced RAG 有什么区别？'

const login = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
}).then((r) => r.json())
const token = login.accessToken || login.access_token || login.token

const { cdp, close } = await launchBrowser({ debugPort: 9391, windowSize: '1600,1000' })
try {
  await cdp.goto(`${APP}/login`)
  await delay(700)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )
  await cdp.goto(`${APP}/app/chat?t=${Date.now()}`)
  await delay(3000)
  await cdp.screenshot(`${OUT}/03-chat-welcome.png`)
  console.log('已保存 03-chat-welcome.png')

  // 填问题并发送
  const sent = await cdp.evaluate(`(() => {
    const box = document.querySelector('textarea');
    if (!box) return 'no-textarea';
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(box, ${JSON.stringify(QUESTION)});
    box.dispatchEvent(new Event('input', { bubbles: true }));
    box.focus();
    // 回车发送
    box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    return 'ok';
  })()`)
  console.log('发送:', sent)

  // 等回答出现（最多 90 秒）
  let lastLen = 0
  let stable = 0
  for (let i = 0; i < 45; i += 1) {
    await delay(2000)
    const info = await cdp.evaluate(`(() => {
      const main = document.querySelector('main');
      const text = (main?.innerText || '');
      return { len: text.length, hasSource: /来源|引用|第\\s*\\d+\\s*页/.test(text) };
    })()`)
    if (info.len > 800 && info.hasSource) {
      if (info.len === lastLen) stable += 1
      else { stable = 0; lastLen = info.len }
      if (stable >= 2) break
    }
  }

  const state = await cdp.evaluate(`(() => {
    const text = (document.querySelector('main')?.innerText || '');
    return { len: text.length, hasCitation: /第\\s*\\d+\\s*页/.test(text), tail: text.slice(-160) };
  })()`)
  console.log('回答状态:', JSON.stringify(state))
  await cdp.screenshot(`${OUT}/05-chat-answer.png`)
  console.log('已保存 05-chat-answer.png')
} finally {
  close()
}
