/**
 * 团队功能截图（生成到 docs/screenshots/teams/）。
 *
 * 前置：后端 3000 + 前端 5173 已运行。
 * 用法：node scripts/shots-teams.mjs
 */
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const API = process.env.API_URL || 'http://localhost:3000/api'

const OUT = resolve(process.cwd(), '..', 'docs', 'screenshots', 'teams')
mkdirSync(OUT, { recursive: true })

async function apiRegister(username) {
  const res = await fetch(`${API}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email: `${username}@shot.com`, password: 'test123456' }),
  })
  const data = await res.json()
  return data.accessToken || data.access_token || data.token
}

async function apiTeam(token, payload) {
  const res = await fetch(`${API}/teams`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
  return res.json()
}

async function apiAddMember(token, teamId, username, role) {
  await fetch(`${API}/teams/${teamId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ username, role }),
  })
}

async function main() {
  const stamp = Date.now().toString(36)
  const owner = `shot_${stamp}`
  const token = await apiRegister(owner)

  // 造点数据，让截图有内容
  const teamA = await apiTeam(token, {
    name: '网络工程组',
    description: '负责综合布线、子网划分与设备配置文档的整理与维护',
    visibility: 'public',
    joinPolicy: 'approval',
  })
  await apiTeam(token, {
    name: '算法竞赛队',
    description: '流水线、指令系统与体系结构相关资料的共享知识库',
    visibility: 'public',
    joinPolicy: 'open',
  })
  const teamB = await apiTeam(token, {
    name: '私有项目组',
    description: '仅凭邀请码加入的内部项目团队',
    visibility: 'private',
    joinPolicy: 'closed',
  })

  // 拉两个成员 + 造一个待审批申请
  const m1 = `shot_m1_${stamp}`
  const m2 = `shot_m2_${stamp}`
  const applicant = `shot_ap_${stamp}`
  await apiRegister(m1)
  await apiRegister(m2)
  const applicantToken = await apiRegister(applicant)
  await apiAddMember(token, teamA.id, m1, 'admin')
  await apiAddMember(token, teamA.id, m2, 'member')
  await fetch(`${API}/teams/${teamA.id}/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${applicantToken}` },
    body: JSON.stringify({ message: '我是同专业的同学，想加入一起整理资料' }),
  })

  // 给团队配一个密钥（截图展示掩码）
  await fetch(`${API}/teams/${teamA.id}/keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ provider: 'zhipu', secret: 'demo0000000000.fakekey1234', label: '团队智谱 Key', model: 'embedding-3' }),
  })

  const { cdp, close } = await launchBrowser({ windowSize: '1440,960' })
  try {
    await cdp.goto(`${APP}/login`)
    await delay(1000)
    await cdp.evaluate(
      `localStorage.setItem('rag.access_token', ${JSON.stringify(token)});
       localStorage.setItem('rag.user', ${JSON.stringify(JSON.stringify({ username: owner }))});
       true`,
    )

    // 1) 我的团队列表
    await cdp.goto(`${APP}/app/teams`)
    await delay(2600)
    await cdp.screenshot(`${OUT}/01-我的团队.png`)
    console.log('已生成 01-我的团队.png')

    // 2) 发现团队
    await cdp.evaluate(
      `(() => {
         const tabs = [...document.querySelectorAll('.el-tabs__item')];
         const tab = tabs.find((t) => (t.innerText || '').includes('发现团队'));
         if (tab) tab.click();
         return true;
       })()`,
    )
    await delay(1800)
    await cdp.screenshot(`${OUT}/02-发现团队.png`)
    console.log('已生成 02-发现团队.png')

    // 3) 创建团队弹窗
    await cdp.evaluate(
      `(() => {
         const btns = [...document.querySelectorAll('button')];
         const btn = btns.find((b) => (b.innerText || '').includes('创建团队'));
         if (btn) btn.click();
         return true;
       })()`,
    )
    await delay(1200)
    await cdp.screenshot(`${OUT}/03-创建团队.png`)
    console.log('已生成 03-创建团队.png')
    await cdp.evaluate(
      `(() => {
         const btns = [...document.querySelectorAll('.el-dialog__footer button')];
         const btn = btns.find((b) => (b.innerText || '').includes('取消'));
         if (btn) btn.click();
         return true;
       })()`,
    )
    await delay(800)

    // 4) 团队详情（成员）
    await cdp.evaluate(
      `(() => {
         const tabs = [...document.querySelectorAll('.el-tabs__item')];
         const tab = tabs.find((t) => (t.innerText || '').includes('我的团队'));
         if (tab) tab.click();
         return true;
       })()`,
    )
    await delay(1200)
    await cdp.evaluate(
      `(() => {
         const cards = [...document.querySelectorAll('article')];
         const card = cards.find((c) => (c.innerText || '').includes('网络工程组'));
         if (card) card.click();
         return true;
       })()`,
    )
    await delay(2200)
    await cdp.screenshot(`${OUT}/04-团队详情-成员.png`)
    console.log('已生成 04-团队详情-成员.png')

    // 5) 入队审批
    await cdp.evaluate(
      `(() => {
         const tabs = [...document.querySelectorAll('.el-tabs__item')];
         const tab = tabs.find((t) => (t.innerText || '').includes('入队审批'));
         if (tab) tab.click();
         return true;
       })()`,
    )
    await delay(1600)
    await cdp.screenshot(`${OUT}/05-入队审批.png`)
    console.log('已生成 05-入队审批.png')

    // 6) 团队设置（含密钥）
    await cdp.evaluate(
      `(() => {
         const tabs = [...document.querySelectorAll('.el-tabs__item')];
         const tab = tabs.find((t) => (t.innerText || '').includes('团队设置'));
         if (tab) tab.click();
         return true;
       })()`,
    )
    await delay(2000)
    await cdp.evaluate(
      `(() => {
         const el = document.querySelector('.el-drawer__body .el-tabs__content');
         if (el) el.scrollTop = el.scrollHeight;
         return true;
       })()`,
    )
    await delay(800)
    await cdp.screenshot(`${OUT}/06-团队设置与密钥.png`)
    console.log('已生成 06-团队设置与密钥.png')

    // 7) 个人 API 密钥设置
    await cdp.goto(`${APP}/app/settings`)
    await delay(2400)
    await cdp.evaluate('window.scrollTo(0, document.body.scrollHeight * 0.72); true')
    await delay(700)
    await cdp.screenshot(`${OUT}/07-个人API密钥.png`)
    console.log('已生成 07-个人API密钥.png')

    // 8) 知识库归属选择
    await cdp.goto(`${APP}/app/knowledge`)
    await delay(2200)
    await cdp.evaluate(
      `(() => {
         const btns = [...document.querySelectorAll('button')];
         const btn = btns.find((b) => (b.innerText || '').includes('新建知识库'));
         if (btn) btn.click();
         return true;
       })()`,
    )
    await delay(1400)
    await cdp.screenshot(`${OUT}/08-知识库归属选择.png`)
    console.log('已生成 08-知识库归属选择.png')
  } finally {
    close()
  }

  console.log(`\n截图目录：${OUT}`)
  console.log(`（含私有团队 ${teamB.name}，可用于验证私有团队不可搜索）`)
}

main().catch((error) => {
  console.error('截图失败：', error)
  process.exit(1)
})
