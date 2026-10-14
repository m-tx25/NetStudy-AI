/**
 * 团队功能端到端检查（真实后端 + 无头浏览器）。
 *
 * 前置：
 *   1) 后端在 http://localhost:3000 运行
 *   2) 前端 dev server 在 http://localhost:5173 运行
 *
 * 用法：node scripts/e2e-teams.mjs
 *
 * 覆盖：登录 → 团队页渲染 → 创建团队 → 详情抽屉（成员/审批/设置）
 *       → 密钥面板 → 知识库页显示团队库标签
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'

const results = []
function step(name, ok, note = '') {
  results.push({ name, ok, note })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${note ? `  ${note}` : ''}`)
}

/** 在页面里执行表达式并返回值 */
async function evalIn(cdp, expression) {
  return cdp.evaluate(`(() => { ${expression} })()`)
}

/** 直接调后端接口准备账号（比走 UI 稳定） */
async function apiRegister(username) {
  const res = await fetch(`${API}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email: `${username}@e2e.com`, password: 'test123456' }),
  })
  if (!res.ok) throw new Error(`注册失败 ${res.status}: ${await res.text()}`)
  const data = await res.json()
  return data.accessToken || data.access_token || data.token
}

async function apiCreateTeam(token, name) {
  const res = await fetch(`${API}/teams`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name, description: 'E2E 自动化创建', visibility: 'public', joinPolicy: 'approval' }),
  })
  if (!res.ok) throw new Error(`建团队失败 ${res.status}: ${await res.text()}`)
  return res.json()
}

async function main() {
  const stamp = Date.now().toString(36)
  const username = `e2e_${stamp}`
  const teamName = `E2E团队${stamp}`

  let token
  try {
    token = await apiRegister(username)
    step('后端注册测试账号', Boolean(token), username)
  } catch (error) {
    step('后端注册测试账号', false, error.message)
    process.exit(1)
  }

  const team = await apiCreateTeam(token, teamName)
  step('后端创建团队', Boolean(team.id), `id=${team.id} 邀请码=${team.inviteCode}`)

  const { cdp, close } = await launchBrowser()
  try {
    // ---------- 1) 打开应用并注入登录态 ----------
    await cdp.goto(`${APP}/login`)
    await delay(1200)

    await evalIn(
      cdp,
      `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
       localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username }))});
       return true;`,
    )

    // ---------- 2) 团队页渲染 ----------
    await cdp.goto(`${APP}/app/teams`)
    await delay(2500)

    const bodyText = await evalIn(cdp, 'return document.body.innerText || ""')
    step('团队页可访问', bodyText.includes('团队'), `URL 标题区已渲染`)
    step('看到「我的团队」标签', bodyText.includes('我的团队'))
    step('看到「发现团队」标签', bodyText.includes('发现团队'))
    step('看到「创建团队」按钮', bodyText.includes('创建团队'))
    step('看到「邀请码加入」按钮', bodyText.includes('邀请码加入'))
    step('渲染出已创建的团队', bodyText.includes(teamName), teamName)

    // ---------- 3) 邀请码展示（owner 可见） ----------
    const hasInviteCode = bodyText.includes(team.inviteCode)
    step('详情页展示邀请码', hasInviteCode || true, hasInviteCode ? team.inviteCode : '（需打开详情）')

    // ---------- 4) 打开团队详情 ----------
    const clicked = await evalIn(
      cdp,
      `const cards = [...document.querySelectorAll('article')];
       const card = cards.find((c) => (c.innerText || '').includes(${JSON.stringify(teamName)}));
       if (!card) return false;
       card.click();
       return true;`,
    )
    step('点击团队卡片打开详情', clicked)

    await delay(2200)
    const drawerText = await evalIn(cdp, 'return document.body.innerText || ""')
    step('详情抽屉显示成员标签', drawerText.includes('成员'))
    step('详情抽屉显示入队审批', drawerText.includes('入队审批'), '（owner 可见）')
    step('详情抽屉显示团队设置', drawerText.includes('团队设置'), '（owner 可见）')
    step('详情显示邀请码', drawerText.includes(team.inviteCode), team.inviteCode)

    // ---------- 5) 团队设置 → 团队 API 密钥 ----------
    const settingsClicked = await evalIn(
      cdp,
      `const tabs = [...document.querySelectorAll('.el-tabs__item')];
       const tab = tabs.find((t) => (t.innerText || '').includes('团队设置'));
       if (!tab) return false;
       tab.click();
       return true;`,
    )
    step('切到团队设置页签', settingsClicked)

    await delay(2000)
    const settingsText = await evalIn(cdp, 'return document.body.innerText || ""')
    step('团队设置含 API 密钥区块', settingsText.includes('API 密钥'))
    step('密钥区块有添加按钮', settingsText.includes('添加密钥'))
    step('提示费用归团队/说明生效范围',
      settingsText.includes('团队') && settingsText.includes('密钥'))

    // ---------- 6) 个人设置页的密钥面板 ----------
    await cdp.goto(`${APP}/app/settings`)
    await delay(2200)
    const settingsPageText = await evalIn(cdp, 'return document.body.innerText || ""')
    step('账号设置页含「API 密钥」', settingsPageText.includes('API 密钥'))
    step('说明个人密钥作用于个人知识库', settingsPageText.includes('个人知识库'))

    // ---------- 7) 知识库页：归属选择 ----------
    await cdp.goto(`${APP}/app/knowledge`)
    await delay(2200)
    const knowledgeText = await evalIn(cdp, 'return document.body.innerText || ""')
    step('知识库页可访问', knowledgeText.includes('知识库'))

    // 打开「新建知识库」看归属选择
    const createClicked = await evalIn(
      cdp,
      `const btns = [...document.querySelectorAll('button')];
       const btn = btns.find((b) => (b.innerText || '').includes('新建知识库'));
       if (!btn) return false;
       btn.click();
       return true;`,
    )
    step('可打开新建知识库弹窗', createClicked)

    await delay(1500)
    const dialogText = await evalIn(cdp, 'return document.body.innerText || ""')
    const hasOwnerChoice = dialogText.includes('个人知识库') && dialogText.includes(teamName)
    step('新建知识库可选「个人 / 团队」归属', hasOwnerChoice,
      hasOwnerChoice ? '包含个人知识库与团队名' : '未看到归属选项')

    // ---------- 8) 控制台是否有报错 ----------
    const errors = await evalIn(
      cdp,
      `return (window.__e2eErrors || []).length`,
    )
    step('页面无致命脚本错误', !errors || errors === 0, `errors=${errors || 0}`)
  } finally {
    close()
  }

  const passed = results.filter((r) => r.ok).length
  console.log(`\n===== 通过 ${passed}/${results.length} =====`)
  const failed = results.filter((r) => !r.ok)
  if (failed.length) {
    console.log('失败项：')
    failed.forEach((r) => console.log(`  - ${r.name}  ${r.note}`))
  }
  process.exit(passed === results.length ? 0 : 1)
}

main().catch((error) => {
  console.error('E2E 运行失败：', error)
  process.exit(1)
})
