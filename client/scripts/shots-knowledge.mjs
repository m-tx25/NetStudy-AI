/** 补拍 README 引用的知识库页与上传弹窗（新品牌+干净数据）。 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'
const OUT = 'E:/传智杯web/docs/screenshots'

const login = await fetch(`${API}/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'demo', password: '123456' }),
}).then((r) => r.json())
const token = login.accessToken || login.access_token || login.token

const { cdp, close } = await launchBrowser({ debugPort: 9390, windowSize: '1600,1000' })
try {
  await cdp.goto(`${APP}/login`)
  await delay(700)
  await cdp.evaluate(
    `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
     localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: 'demo' }))});
     true`,
  )

  // 知识库管理：选中「学术文献 · RAG」（库里有 3 篇论文，截图才有内容）
  await cdp.goto(`${APP}/app/knowledge?t=${Date.now()}`)
  await delay(2500)
  const picked = await cdp.evaluate(`(() => {
    const nodes = [...document.querySelectorAll('button,div,li')];
    const target = nodes.find((el) => (el.textContent || '').trim().startsWith('学术文献'));
    if (!target) return 'not-found';
    target.click();
    return 'ok';
  })()`)
  console.log('选择知识库:', picked)
  await delay(2600)
  await cdp.screenshot(`${OUT}/06-knowledge.png`)
  console.log('已保存 06-knowledge.png')

  // 打开上传弹窗
  const clicked = await cdp.evaluate(`(() => {
    const btns = [...document.querySelectorAll('button')];
    const target = btns.find((b) => (b.textContent || '').trim().includes('上传文档'));
    if (!target) return 'no-button';
    target.click();
    return 'ok';
  })()`)
  console.log('上传按钮:', clicked)
  await delay(1800)
  await cdp.screenshot(`${OUT}/07-upload-dialog.png`)
  console.log('已保存 07-upload-dialog.png')
} finally {
  close()
}
