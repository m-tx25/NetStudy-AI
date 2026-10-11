/**
 * 用无头浏览器给主要页面截图，产出到 docs/screenshots/。
 *
 * 前置：先启动 dev server（Mock 模式）
 *   npm run dev:client
 * 运行：
 *   npm run screenshots
 */
import { join } from 'node:path'

import { delay, launchBrowser } from './lib/cdp.mjs'

const ORIGIN = process.env.APP_ORIGIN || 'http://[::1]:5173'
const OUT = join(import.meta.dirname, '..', '..', 'docs', 'screenshots')

const HELPERS = `
  const setValue = (el, value) => {
    if (!el) return false
    const proto = el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  }
  const clickByText = (text) => {
    const el = [...document.querySelectorAll('button')]
      .find((node) => (node.innerText || '').includes(text))
    if (el) el.click()
    return !!el
  }
`

async function main() {
  const { cdp, close } = await launchBrowser({ debugPort: 9344 })
  const shot = async (name) => {
    await cdp.screenshot(join(OUT, name))
    console.log(`saved ${name}`)
  }

  try {
    await cdp.send('Storage.clearDataForOrigin', { origin: ORIGIN, storageTypes: 'all' }).catch(() => {})

    /* 1. 首页落地页（默认深色科技风，整屏 + 可滚动） */
    await cdp.goto(`${ORIGIN}/`)
    await delay(1800)
    await shot('00-home.png')
    await cdp.evaluate(`window.scrollTo({ top: Math.round(window.innerHeight * 1.15), behavior: 'instant' })`)
    await delay(1400)
    await shot('00b-home-scroll.png')

    /* 2. 登录页 */
    await cdp.goto(`${ORIGIN}/login`)
    await delay(1600)
    await shot('01-login.png')

    /* 3. 注册页 */
    await cdp.goto(`${ORIGIN}/register`)
    await delay(1300)
    await shot('02-register.png')

    /* 4. 回到登录页，通过界面真实登录，让 Mock 侧建立登录态 */
    await cdp.goto(`${ORIGIN}/login`)
    await delay(1400)
    const loggedIn = await cdp.evaluate(`(() => {
      ${HELPERS}
      const okUser = setValue(document.querySelector('input[autocomplete="username"]'), 'demo')
      const okPwd = setValue(document.querySelector('input[autocomplete="current-password"]'), '123456')
      return okUser && okPwd && clickByText('登 录')
    })()`)
    if (!loggedIn) throw new Error('截图前置的登录动作失败')
    await delay(2500)

    /* 5. 问答欢迎页 */
    await shot('03-chat-welcome.png')

    /* 6. 流式生成中 */
    await cdp.evaluate(`(() => { ${HELPERS} return clickByText('总结文档要点') })()`)
    await delay(2600)
    await shot('04-chat-streaming.png')

    /* 7. 回答完成（含引用来源展开） */
    await delay(14000)
    await cdp.evaluate(`(() => {
      const chip = document.querySelector('button[title$=".md"], button[title$=".pdf"], button[title$=".docx"]')
      chip?.click()
      return !!chip
    })()`)
    await delay(700)
    await shot('05-chat-answer.png')

    /* 8. 知识库管理 */
    await cdp.goto(`${ORIGIN}/app/knowledge`)
    await delay(2400)
    await shot('06-knowledge.png')

    /* 9. 上传弹窗 */
    await cdp.evaluate(`(() => { ${HELPERS} return clickByText('上传文档') })()`)
    await delay(1200)
    await shot('07-upload-dialog.png')
    await cdp.evaluate(`document.querySelector('.el-dialog__headerbtn')?.click()`)
    await delay(600)

    /* 10. 账号设置：资料卡片（含「登录账号将变更」提示） */
    await cdp.goto(`${ORIGIN}/app/settings`)
    await delay(2200)
    await cdp.evaluate(`(() => {
      ${HELPERS}
      setValue(document.querySelector('input[placeholder^="用于界面展示"]'), '张工')
      setValue(document.querySelector('input[autocomplete="username"]'), 'zhanggong')
      return true
    })()`)
    await delay(600)
    await shot('08-settings-profile.png')

    /* 10. 账号设置：修改密码卡片（含密码强度） */
    await cdp.evaluate(`(() => {
      ${HELPERS}
      setValue(document.querySelector('input[autocomplete="current-password"]'), '123456')
      setValue(document.querySelector('input[placeholder^="至少 6 位，建议 8 位以上"]'), 'NewPass@2025')
      setValue(document.querySelector('input[placeholder="再次输入新密码"]'), 'NewPass@2025')
      const section = [...document.querySelectorAll('section')]
        .find((node) => node.innerText.includes('修改密码'))
      section?.scrollIntoView({ block: 'start' })
      return !!section
    })()`)
    await delay(900)
    await shot('09-settings-password.png')

    /* 11. 浅色主题下的问答（深色是默认主题，这里验证浅色仍可用） */
    await cdp.evaluate(`(() => {
      localStorage.setItem('rag.theme', 'light')
      document.documentElement.classList.remove('dark')
      return true
    })()`)
    await cdp.goto(`${ORIGIN}/app/chat`)
    await delay(2600)
    await shot('10-chat-light.png')
  } finally {
    close()
  }
}

main().catch((error) => {
  console.error('截图失败：', error.message)
  process.exit(1)
})
