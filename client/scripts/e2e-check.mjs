/**
 * 端到端冒烟测试（无需人工介入、无需额外依赖）。
 *
 * 覆盖：登录页渲染 → 真实登录 → 流式问答 → 引用来源 → 账号设置改用户名 →
 *      改密码（先试错再成功）→ 强制重新登录 → 用新凭据登录 → 知识库页 → 主题切换。
 *
 * 前置：先启动 dev server（VITE_USE_MOCK=true）
 *   npm run dev:client
 * 运行：
 *   npm run check:e2e
 */
import { delay, launchBrowser } from './lib/cdp.mjs'

const APP_ORIGIN = process.env.APP_ORIGIN || 'http://[::1]:5173'

const results = []
let failures = 0

function check(name, ok, detail = '') {
  results.push({ name, ok })
  if (!ok) failures += 1
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  -> ${detail}` : ''}`)
}

/**
 * 轮询等待页面进入期望状态（Mock 的 sleep 与真实渲染都有随机性，固定 delay 容易假失败）。
 * @param {import('./lib/cdp.mjs').Cdp} cdp
 * @param {string} expression 返回布尔值的表达式
 * @param {{ timeout?: number, interval?: number }} options
 */
async function waitFor(cdp, expression, { timeout = 9000, interval = 250 } = {}) {
  const deadline = Date.now() + timeout
  for (;;) {
    try {
      if (await cdp.evaluate(expression)) return true
    } catch {
      /* 页面正在跳转，忽略后重试 */
    }
    if (Date.now() >= deadline) return false
    await delay(interval)
  }
}

/** 注入到页面里的通用工具：绕过框架的受控输入，直接触发 input 事件 */
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
    const el = [...document.querySelectorAll('button, a, li, span')]
      .find((node) => node.innerText && node.innerText.trim() === text)
      || [...document.querySelectorAll('button')]
        .find((node) => (node.innerText || '').includes(text))
    if (el) el.click()
    return !!el
  }
`

async function main() {
  const { cdp, close } = await launchBrowser({ debugPort: 9333 })

  try {
    const consoleErrors = []
    cdp.on((msg) => {
      if (msg.method === 'Runtime.exceptionThrown') {
        consoleErrors.push(
          msg.params?.exceptionDetails?.exception?.description ||
            msg.params?.exceptionDetails?.text ||
            'unknown exception',
        )
      }
      if (msg.method === 'Runtime.consoleAPICalled' && msg.params?.type === 'error') {
        consoleErrors.push(msg.params.args.map((a) => a.value ?? a.description).join(' '))
      }
    })

    await cdp
      .send('Storage.clearDataForOrigin', { origin: APP_ORIGIN, storageTypes: 'all' })
      .catch(() => {})

    /* ============================================================ *
     * 1. 登录页（商业化版式）
     * ============================================================ */
    await cdp.goto(`${APP_ORIGIN}/login`)
    await delay(1500)

    const loginProbe = await cdp.evaluate(`(() => {
      const text = document.body.innerText
      return {
        title: document.title,
        path: location.pathname,
        innerWidth: window.innerWidth,
        heroHeadline: text.includes('让每一个答案'),
        heroHighlight: text.includes('原文出处'),
        capability: text.includes('全格式文档接入') && text.includes('数据不出内网'),
        trust: text.includes('私有化部署') && text.includes('传输加密'),
        enterpriseBadge: text.includes('企业版'),
        hasForm: text.includes('使用你的'),
        rememberLabel: text.includes('记住账号'),
        forgotEntry: text.includes('忘记密码'),
        termsLink: text.includes('服务协议'),
        privacyLink: text.includes('隐私政策'),
        demoButton: text.includes('一键体验演示账号'),
        footer: text.includes('保留所有权利') && text.includes('京ICP备'),
        prefilled: document.querySelector('input[autocomplete="username"]')?.value || '',
      }
    })()`)

    check('登录页整体渲染（品牌区 + 表单）',
      loginProbe.hasForm && loginProbe.heroHeadline, JSON.stringify({ w: loginProbe.innerWidth }))
    check('左侧品牌区：主标题 + 高亮「原文出处」',
      loginProbe.heroHeadline && loginProbe.heroHighlight)
    check('左侧品牌区：能力卡片 + 信任条',
      loginProbe.capability && loginProbe.trust)
    check('左侧品牌区：企业版标识', loginProbe.enterpriseBadge === true)
    check('表单：记住账号 / 忘记密码入口',
      loginProbe.rememberLabel && loginProbe.forgotEntry)
    check('表单：服务协议与隐私政策链接',
      loginProbe.termsLink && loginProbe.privacyLink)
    check('表单：一键体验演示账号入口', loginProbe.demoButton === true)
    check('页脚：版权与备案信息', loginProbe.footer === true)
    check('Mock 模式预填账号', loginProbe.prefilled === 'demo', `value=${loginProbe.prefilled}`)

    // 隐私政策弹窗可以正常打开
    const privacyOpened = await cdp.evaluate(`(() => {
      ${HELPERS}
      const ok = clickByText('《隐私政策》')
      return ok
    })()`)
    await delay(600)
    const privacyProbe = await cdp.evaluate(`(() => ({
      dialogVisible: !!document.querySelector('.el-dialog'),
      hasTitle: document.body.innerText.includes('隐私政策'),
      hasSection: document.body.innerText.includes('我们收集哪些信息'),
    }))()`)
    check('隐私政策弹窗可打开且有正文',
      privacyOpened && privacyProbe.dialogVisible && privacyProbe.hasSection,
      JSON.stringify(privacyProbe))
    await cdp.evaluate(`(() => {
      ${HELPERS}
      clickByText('我已阅读')
      return true
    })()`)
    await delay(400)

    // 未登录访问受保护路由会被拦回登录页
    await cdp.goto(`${APP_ORIGIN}/app/chat`)
    await delay(1200)
    check('未登录访问 /app/chat 会被重定向到登录页',
      (await cdp.evaluate('location.pathname')) === '/login')

    /* ============================================================ *
     * 2. 真实登录（走 Mock 的账号校验，而不是直接注入 Token）
     * ============================================================ */
    const loggedIn = await cdp.evaluate(`(() => {
      ${HELPERS}
      setValue(document.querySelector('input[autocomplete="username"]'), 'demo')
      setValue(document.querySelector('input[autocomplete="current-password"]'), '123456')
      return clickByText('登 录')
    })()`)
    check('提交登录表单', loggedIn === true)
    await delay(600)
    // 登录是「请求 → 写 session → 跳转」三步，等页面真正进入问答页再看断言
    await waitFor(cdp, `location.pathname === '/app/chat' && document.body.innerText.includes('有什么可以帮你的')`)

    const afterLogin = await cdp.evaluate(`(() => ({
      path: location.pathname,
      title: document.title,
      sidebarUser: document.body.innerText.includes('演示用户'),
      hasWelcome: document.body.innerText.includes('有什么可以帮你的'),
      storedUser: (() => { try { return JSON.parse(localStorage.getItem('rag.user'))?.username } catch { return '' } })(),
    }))()`)
    check('登录成功并进入问答页',
      afterLogin.path === '/app/chat' && afterLogin.hasWelcome, JSON.stringify(afterLogin))
    check('侧边栏显示登录用户', afterLogin.sidebarUser === true)
    check('登录态已落盘 localStorage', afterLogin.storedUser === 'demo', afterLogin.storedUser)

    /* ============================================================ *
     * 3. 流式问答
     * ============================================================ */
    const clicked = await cdp.evaluate(`(() => {
      ${HELPERS}
      // 欢迎页的示例卡片是 button，textContent 形如「📄总结文档要点请总结…」；
      // 用 textContent（不受 innerText 布局换行与 emoji 影响）筛出长度最短的那个，
      // 避免误点侧边栏里标题相同的会话条目
      const el = [...document.querySelectorAll('button')]
        .filter((node) => {
          const text = (node.textContent || '').replace(/\\s+/g, '')
          return text.includes('总结文档要点') && text.includes('请总结')
        })
        .sort((a, b) => a.textContent.length - b.textContent.length)[0]
      if (el) el.click()
      return !!el
    })()`)
    check('触发示例提问', clicked === true)

    // 首次提问会「创建会话 → 写 store → 路由替换」，顺序不固定：
    // 轮询等两个信号（生成中 / 路由已切换）都出现后再断言
    await waitFor(
      cdp,
      `!!document.querySelector('.markdown-body.is-streaming')
        || document.body.innerText.includes('正在检索知识库')
        || location.pathname.startsWith('/app/chat/')`,
      { timeout: 10000 },
    )
    const routed = await waitFor(cdp, `location.pathname.startsWith('/app/chat/')`, { timeout: 10000 })
    const midProbe = await cdp.evaluate(`(() => ({
      hasUserBubble: document.body.innerText.includes('请总结'),
      streamSettled: !document.querySelector('.markdown-body.is-streaming'),
      path: location.pathname,
    }))()`)
    check('首次提问自动创建会话并切换路由', routed === true && midProbe.path.startsWith('/app/chat/'),
      midProbe.path)

    // 等正文与引用来源渲染出来（收尾会有一次 markdown 重排），
    // 再等打字机把缓冲吐完（streaming 状态由打字机 drain 结束才置回 false）
    await waitFor(
      cdp,
      `document.body.innerText.includes('结论') && document.body.innerText.includes('引用来源')`,
      { timeout: 15000 },
    )
    await waitFor(cdp, `!document.querySelector('.markdown-body.is-streaming')`, { timeout: 40000 })
    await delay(300)

    const doneProbe = await cdp.evaluate(`(() => {
      const text = document.body.innerText
      return {
        hasUserBubble: text.includes('请总结'),
        hasConclusion: text.includes('结论'),
        hasSourcesLabel: text.includes('引用来源'),
        streamSettled: !document.querySelector('.markdown-body.is-streaming'),
      }
    })()`)
    check('用户提问气泡出现', doneProbe.hasUserBubble === true)
    check('助手回答正文渲染（Markdown 标题）', doneProbe.hasConclusion === true)
    check('引用来源区块出现', doneProbe.hasSourcesLabel === true)
    check('流式已结束（打字机光标消失）', doneProbe.streamSettled === true)

    const sourceExpand = await cdp.evaluate(`(() => {
      ${HELPERS}
      const chip = document.querySelector('button[title$=".md"], button[title$=".pdf"], button[title$=".docx"]')
      if (!chip) return false
      chip.click()
      return true
    })()`)
    await delay(500)
    const sourceProbe = await cdp.evaluate(`(() => document.body.innerText.includes('相关度'))()`)
    check('引用来源可展开并显示相关度', sourceExpand && sourceProbe === true)

    /* ============================================================ *
     * 4. 账号设置 —— 修改用户名 / 昵称
     * ============================================================ */
    await cdp.goto(`${APP_ORIGIN}/app/settings`)
    await delay(1800)

    const settingsProbe = await cdp.evaluate(`(() => {
      const text = document.body.innerText
      return {
        path: location.pathname,
        title: document.title,
        hasProfileCard: text.includes('账号资料'),
        hasPasswordCard: text.includes('修改密码'),
        hasOverview: text.includes('侧边栏显示'),
        infoRows: text.includes('账号 ID') && text.includes('最近登录'),
        nickname: document.querySelector('input[placeholder^="用于界面展示"]')?.value || '',
        username: document.querySelector('input[autocomplete="username"]')?.value || '',
        email: document.querySelector('input[autocomplete="email"]')?.value || '',
      }
    })()`)
    check('账号设置页渲染（资料 + 密码两张卡片）',
      settingsProbe.path === '/app/settings' && settingsProbe.hasProfileCard && settingsProbe.hasPasswordCard,
      JSON.stringify({ path: settingsProbe.path }))
    check('账号设置页有账号概览与只读信息',
      settingsProbe.hasOverview && settingsProbe.infoRows)
    check('资料表单已回填当前账号',
      settingsProbe.nickname === '演示用户' && settingsProbe.username === 'demo',
      `${settingsProbe.nickname} / ${settingsProbe.username}`)

    // 先只填值，等 Vue 把 DOM 刷新完（按钮的 disabled 由 profileDirty 驱动）
    const filled = await cdp.evaluate(`(() => {
      ${HELPERS}
      return {
        nickname: setValue(document.querySelector('input[placeholder^="用于界面展示"]'), '张工'),
        username: setValue(document.querySelector('input[autocomplete="username"]'), 'zhanggong'),
        email: setValue(document.querySelector('input[autocomplete="email"]'), 'zhanggong@example.com'),
      }
    })()`)
    check('填写账号资料表单', filled.nickname && filled.username && filled.email, JSON.stringify(filled))
    await delay(400)

    const profileSaved = await cdp.evaluate(`(() => {
      const btn = [...document.querySelectorAll('button')]
        .find((node) => node.innerText.trim() === '保存修改')
      const before = { found: !!btn, disabled: btn ? btn.disabled : null }
      if (btn) btn.click()
      return before
    })()`)
    check('提交账号资料修改（按钮已可点击）',
      profileSaved.found === true && profileSaved.disabled === false, JSON.stringify(profileSaved))
    await delay(1800)

    const profileAfter = await cdp.evaluate(`(() => {
      const text = document.body.innerText
      let stored = {}
      try { stored = JSON.parse(localStorage.getItem('rag.user')) || {} } catch {}
      const saveBtn = [...document.querySelectorAll('button')]
        .find((node) => node.innerText.trim() === '保存修改')
      return {
        sidebarName: (document.querySelector('aside')?.innerText || '').includes('张工'),
        warnBanner: text.includes('下次请使用新用户名') || text.includes('登录账号将从'),
        storedUsername: stored.username,
        storedNickname: stored.nickname,
        storedEmail: stored.email,
        formUsername: document.querySelector('input[autocomplete="username"]')?.value || '',
        saveDisabled: saveBtn ? saveBtn.disabled : null,
        toasts: [...document.querySelectorAll('.el-message')].map((n) => n.innerText.trim()),
        fieldErrors: [...document.querySelectorAll('.el-form-item__error')].map((n) => n.innerText.trim()),
      }
    })()`)
    check('用户名 / 昵称修改成功并落盘',
      profileAfter.storedUsername === 'zhanggong' &&
        profileAfter.storedNickname === '张工' &&
        profileAfter.storedEmail === 'zhanggong@example.com',
      JSON.stringify(profileAfter))
    check('资料表单同步成新用户名', profileAfter.formUsername === 'zhanggong', profileAfter.formUsername)
    check('侧边栏立即显示新昵称', profileAfter.sidebarName === true,
      `sidebar=${profileAfter.sidebarName} toasts=${JSON.stringify(profileAfter.toasts)} errors=${JSON.stringify(profileAfter.fieldErrors)} disabled=${profileAfter.saveDisabled}`)

    /* ============================================================ *
     * 5. 账号设置 —— 修改密码（先错误后正确）
     * ============================================================ */
    const wrongPassword = await cdp.evaluate(`(() => {
      ${HELPERS}
      setValue(document.querySelector('input[autocomplete="current-password"]'), 'wrongpass')
      setValue(document.querySelector('input[placeholder^="至少 6 位，建议 8 位以上"]'), 'NewPass@2025')
      setValue(document.querySelector('input[placeholder="再次输入新密码"]'), 'NewPass@2025')
      return clickByText('确认修改密码')
    })()`)
    check('提交修改密码（当前密码故意填错）', wrongPassword === true)
    await delay(1500)
    const wrongProbe = await cdp.evaluate(`(() => ({
      toast: document.body.innerText.includes('当前密码不正确'),
      boxVisible: !!document.querySelector('.el-message-box'),
    }))()`)
    check('当前密码错误被拦截且给出提示',
      wrongProbe.toast === true && wrongProbe.boxVisible === false, JSON.stringify(wrongProbe))

    const rightPassword = await cdp.evaluate(`(() => {
      ${HELPERS}
      setValue(document.querySelector('input[autocomplete="current-password"]'), '123456')
      setValue(document.querySelector('input[placeholder^="至少 6 位，建议 8 位以上"]'), 'NewPass@2025')
      setValue(document.querySelector('input[placeholder="再次输入新密码"]'), 'NewPass@2025')
      return clickByText('确认修改密码')
    })()`)
    check('提交修改密码（填写正确）', rightPassword === true)
    await delay(1800)

    const confirmProbe = await cdp.evaluate(`(() => {
      const box = document.querySelector('.el-message-box')
      let credential = {}
      try { credential = JSON.parse(localStorage.getItem('rag.mock.db.v1'))?.credentials || {} } catch {}
      return {
        boxVisible: !!box,
        boxTitle: box ? box.innerText.includes('密码修改成功') : false,
        mockPassword: credential.password,
        mockUsername: credential.username,
      }
    })()`)
    check('弹出「密码修改成功」确认框', confirmProbe.boxVisible && confirmProbe.boxTitle,
      JSON.stringify(confirmProbe))
    check('Mock 侧密码已更新，用户名同步为新登录名',
      confirmProbe.mockPassword === 'NewPass@2025' && confirmProbe.mockUsername === 'zhanggong',
      JSON.stringify(confirmProbe))

    // 选择「立即重新登录」
    const relogin = await cdp.evaluate(`(() => {
      ${HELPERS}
      return clickByText('立即重新登录')
    })()`)
    check('点击「立即重新登录」', relogin === true)
    await delay(1800)

    const afterRelogin = await cdp.evaluate(`(() => ({
      path: location.pathname,
      hint: document.body.innerText.includes('密码已更新'),
      token: localStorage.getItem('rag.access_token') || '',
      user: localStorage.getItem('rag.user'),
    }))()`)
    check('退出到登录页并提示「密码已更新」',
      afterRelogin.path === '/login' && afterRelogin.hint === true, JSON.stringify({ path: afterRelogin.path }))
    check('本地登录态已清除', afterRelogin.token === '' && afterRelogin.user === null,
      `token="${afterRelogin.token}"`)

    /* ============================================================ *
     * 6. 用「新用户名 + 新密码」重新登录，验证修改真正生效
     * ============================================================ */
    const reloginSubmit = await cdp.evaluate(`(() => {
      ${HELPERS}
      setValue(document.querySelector('input[autocomplete="username"]'), 'zhanggong')
      setValue(document.querySelector('input[autocomplete="current-password"]'), 'NewPass@2025')
      return clickByText('登 录')
    })()`)
    check('用新凭据提交登录', reloginSubmit === true)
    await delay(2200)

    const finalProbe = await cdp.evaluate(`(() => {
      const text = document.body.innerText
      let stored = {}
      try { stored = JSON.parse(localStorage.getItem('rag.user')) || {} } catch {}
      return {
        path: location.pathname,
        sidebarName: text.includes('张工'),
        storedUsername: stored.username,
        hasWelcome: text.includes('有什么可以帮你的'),
      }
    })()`)
    check('新用户名 + 新密码登录成功',
      finalProbe.path === '/app/chat' && finalProbe.storedUsername === 'zhanggong' && finalProbe.hasWelcome,
      JSON.stringify(finalProbe))
    check('登录后侧边栏仍显示昵称「张工」', finalProbe.sidebarName === true)

    /* ============================================================ *
     * 7. 知识库页 + 主题切换
     * ============================================================ */
    await cdp.goto(`${APP_ORIGIN}/app/knowledge`)
    await delay(2000)
    const kbProbe = await cdp.evaluate(`(() => {
      const text = document.body.innerText
      return {
        path: location.pathname,
        hasTitle: text.includes('知识库管理'),
        hasBase: text.includes('产品需求文档库') || text.includes('技术文档库'),
        hasUploadBtn: text.includes('上传文档'),
        hasTableHeader: text.includes('解析状态') || text.includes('向量片段'),
        docNames: (text.match(/\\.(pdf|md|docx)/g) || []).length,
      }
    })()`)
    check('知识库页渲染', kbProbe.path === '/app/knowledge' && kbProbe.hasTitle === true)
    check('知识库列表与文档表格渲染',
      kbProbe.hasBase && kbProbe.hasUploadBtn && kbProbe.hasTableHeader, JSON.stringify(kbProbe))
    check('文档行有数据', kbProbe.docNames >= 2, `matches=${kbProbe.docNames}`)

    // 主题切换在侧边栏用户菜单里（知识库页没有独立的主题按钮）
    await cdp.evaluate(`(() => {
      const trigger = [...document.querySelectorAll('button')].find((b) => (b.innerText || '').includes('@example.com'))
      if (trigger) trigger.click()
      return !!trigger
    })()`)
    await delay(500)
    const themeClicked = await cdp.evaluate(`(() => {
      const item = [...document.querySelectorAll('.el-dropdown-menu__item')]
        .find((node) => (node.innerText || '').includes('切换为'))
      if (item) item.click()
      return !!item
    })()`)
    await delay(500)
    const themeProbe = await cdp.evaluate(`(() => ({
      isDark: document.documentElement.classList.contains('dark'),
      stored: localStorage.getItem('rag.theme'),
    }))()`)
    check('主题切换写入 html.dark 与 localStorage',
      themeClicked === true && ['dark', 'light'].includes(themeProbe.stored) && themeProbe.isDark === (themeProbe.stored === 'dark'),
      JSON.stringify({ themeClicked, ...themeProbe }))

    check('运行期无未捕获异常 / console.error', consoleErrors.length === 0,
      consoleErrors.slice(0, 3).join(' | '))
  } catch (error) {
    console.log(`\nE2E 执行中断：${error.message}`)
    failures += 1
  } finally {
    close()
  }

  console.log(`\n==== ${results.length - failures}/${results.length} 项通过 ====`)
  process.exit(failures === 0 ? 0 : 1)
}

main()
