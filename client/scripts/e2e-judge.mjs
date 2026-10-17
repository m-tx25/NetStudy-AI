/**
 * 评委视角的端到端验收（真实浏览器 + 真实后端）。
 *
 * 前置：后端 3000、前端 5173 都在运行，且后端使用**默认 .env**（无 API Key 也能跑）。
 * 用法：node scripts/e2e-judge.mjs
 *
 * 覆盖：注册 → 建知识库 → 上传文档 → 向量化 → 浏览器登录 →
 *       问答页渲染 → 选择知识库 → 提问 → 看到答案与引用
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const API = process.env.API_URL || 'http://localhost:3000/api'
const APP = process.env.APP_URL || 'http://localhost:5173'

const results = []
function step(name, ok, note = '') {
  results.push({ name, ok, note })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${note ? `  ${note}` : ''}`)
}

async function apiRegister(username) {
  const res = await fetch(`${API}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email: `${username}@j.com`, password: 'test123456' }),
  })
  const data = await res.json()
  return data.accessToken || data.access_token || data.token
}

async function api(token, path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  })
  return res.json()
}

async function main() {
  const stamp = Date.now().toString(36)
  const username = `judge_${stamp}`
  const token = await apiRegister(username)
  step('后端可用（注册账号）', Boolean(token), username)

  // 通过 API 准备带文档的知识库（浏览器驱动文件选择器较脆弱）
  const kb = await api(token, '/knowledge-bases', {
    method: 'POST',
    body: JSON.stringify({ name: `评委验收库${stamp}` }),
  })
  step('创建知识库', Boolean(kb.id), kb.id)

  const form = new FormData()
  const content =
    '验收文档：本项目的部署端口是 8080，默认管理员账号为 admin。\n技术栈是 Vue 3 与 FastAPI。\n'
  form.append('file', new Blob([content], { type: 'text/plain' }), 'judge.txt')
  form.append('knowledgeBaseId', kb.id)
  const uploadRes = await fetch(`${API}/documents/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  const doc = await uploadRes.json()
  step('上传文档', uploadRes.ok, `status=${doc.status}`)

  let ready = null
  for (let i = 0; i < 30; i += 1) {
    await delay(2000)
    const docs = await api(token, `/documents?knowledgeBaseId=${kb.id}`)
    ready = (docs || []).find((d) => d.id === doc.id)
    if (ready && ['ready', 'failed'].includes(ready.status)) break
  }
  step('文档向量化完成', ready?.status === 'ready',
    `status=${ready?.status} chunks=${ready?.chunks}`)

  const { cdp, close } = await launchBrowser({ windowSize: '1440,900' })
  try {
    await cdp.goto(`${APP}/login`)
    await delay(1200)
    await cdp.evalStmt(`
      localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
      localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username }))});
      return true;
    `)

    await cdp.goto(`${APP}/app/chat`)
    await delay(4500)

    const text = await cdp.evalStmt(
      'return (document.body && document.body.innerText) || ""',
    )
    step('问答页渲染正常', text.includes('有什么可以帮你的'), `${text.length} 字符`)
    const hasInput = await cdp.evalStmt(
      'return Boolean(document.querySelector("textarea"))',
    )
    step('有输入框', hasInput)

    // 填入问题（用原生 setter 触发 Vue 的 v-model）
    const filled = await cdp.evalStmt(`
      const ta = document.querySelector('textarea');
      if (!ta) return false;
      ta.focus();
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, '本项目的部署端口是多少？');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      return ta.value.includes('8080') || ta.value.length > 0;
    `)
    step('填入问题', filled)

    // 提交：优先点发送按钮，其次回车
    const submitted = await cdp.evalStmt(`
      const ta = document.querySelector('textarea');
      const buttons = [...document.querySelectorAll('button')];
      const sendBtn = buttons.find((b) => {
        const t = (b.innerText || '').trim();
        return t === '发送' || t === '发 送' || b.getAttribute('aria-label') === '发送';
      });
      if (sendBtn && !sendBtn.disabled) { sendBtn.click(); return 'button'; }
      if (ta) {
        ta.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
        return 'enter';
      }
      return 'none';
    `)
    step('提交问题', submitted !== 'none', `方式=${submitted}`)

    // 等待流式回答结束
    await delay(12000)
    const after = await cdp.evalStmt(
      'return (document.body && document.body.innerText) || ""',
    )
    const gotPort = after.includes('8080')
    const gotExcerpt = after.includes('摘录') || after.includes('离线演示')
    const gotSource = after.includes('judge.txt') || after.includes('引用')
    step('回答包含知识库事实', gotPort, gotPort ? '命中 8080' : '未命中')
    step('展示了引用来源', gotSource, gotSource ? '有引用区' : '未看到')
    // 「离线演示」标注只在**没配大模型 Key** 时才会出现；
    // 配了 Key 走的是正常生成模式，这里只做信息性提示，不作为失败条件。
    console.log(
      gotExcerpt
        ? 'INFO  当前为离线摘录模式（未配 LLM Key）'
        : 'INFO  当前为模型生成模式（已配 LLM Key）',
    )
    if (!gotPort) {
      console.log('     页面尾部：', JSON.stringify(after.slice(-300)))
    }
  } finally {
    close()
  }

  const passed = results.filter((r) => r.ok).length
  console.log(`\n===== 通过 ${passed}/${results.length} =====`)
  results.filter((r) => !r.ok).forEach((r) => console.log(`  FAIL: ${r.name}  ${r.note}`))
  process.exit(passed === results.length ? 0 : 1)
}

main().catch((e) => {
  console.error('E2E 失败：', e)
  process.exit(1)
})
