/**
 * 端到端验证「用户在前端自己添加模型」：
 *   打开选择器 → 添加模型 → 用本地预设一键填入 → 保存 → 连接测试通过 → 出现在列表并被选中。
 * 前置：后端(3000) + 前端(5173) + 本地 mock LLM(11500) 已启动。
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.argv[2] || 'http://localhost:5173'
const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  -> ${detail}` : ''}`)
}

const browser = await launchBrowser({ debugPort: 9452, windowSize: '1440,1000' })
const { cdp } = browser

const HELPERS = `
  const setValue = (el, v) => {
    if (!el) return false
    const proto = el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
    return true
  }
  // 注意：不要用 offsetParent 判可见性 —— 在无头浏览器里它会把真实可见的元素判成不可见，
  // 导致点击不到按钮（这个坑踩过一次）。改为按文本精确匹配，再退化为包含匹配。
  const clickByText = (text, scope) => {
    const root = scope || document
    const all = [...root.querySelectorAll('button, a, li, [role="button"]')]
    const norm = (s) => (s || '').replace(/\\s/g, '')
    const exact = all.find((n) => norm(n.innerText) === norm(text))
    if (exact) { exact.click(); return true }
    const loose = all.find((n) => norm(n.innerText).includes(norm(text)))
    if (loose) { loose.click(); return true }
    return false
  }
`

try {
  // 登录
  await cdp.goto(`${APP}/login`)
  await delay(1200)
  await cdp.evaluate(`localStorage.clear()`)
  await cdp.goto(`${APP}/login`)
  await delay(1500)
  await cdp.evaluate(`(() => {
    ${HELPERS}
    setValue(document.querySelector('input[autocomplete="username"]'), 'demo')
    setValue(document.querySelector('input[autocomplete="current-password"]'), '123456')
    clickByText('登录')
    return true
  })()`)
  await delay(3500)

  // 打开模型选择器
  const opened = await cdp.evaluate(`(() => {
    ${HELPERS}
    const btn = [...document.querySelectorAll('button')]
      .find((b) => (b.getAttribute('title') || '').includes('当前生成模型'))
    if (!btn) return false
    btn.click()
    return true
  })()`)
  check('打开模型选择器', opened === true)
  await delay(1000)

  const panel = await cdp.evaluate(`(() => {
    const text = document.body.innerText
    return {
      hasAddButton: text.includes('添加模型'),
      hasPresetsHint: text.includes('尚未配置可用的模型') || text.includes('本地部署'),
    }
  })()`)
  check('面板有「添加模型」入口', panel.hasAddButton === true)
  check('未配置时给出指引', panel.hasPresetsHint === true)

  // 打开添加模型对话框
  const dialogOpened = await cdp.evaluate(`(() => {
    ${HELPERS}
    return clickByText('添加模型')
  })()`)
  check('打开发添加对话框', dialogOpened === true)
  await delay(1200)

  const dialogState = await cdp.evaluate(`(() => {
    const text = document.body.innerText
    return {
      hasTitle: text.includes('添加模型'),
      hasLocalPresets: text.includes('Ollama') || text.includes('vLLM') || text.includes('LM Studio'),
      hasBaseUrlField: Boolean([...document.querySelectorAll('input')].find((i) => (i.placeholder||'').includes('11434') || (i.placeholder||'').includes('api.deepseek'))),
      hasKeyField: Boolean(document.querySelector('input[type="password"]')),
      hasTestButton: text.includes('测试连接'),
    }
  })()`)
  check('对话框含本地预设按钮', dialogState.hasLocalPresets === true)
  check('对话框含接口地址输入框', dialogState.hasBaseUrlField === true)
  check('对话框含 API Key 输入框（密码型）', dialogState.hasKeyField === true)
  check('对话框含「测试连接」按钮', dialogState.hasTestButton === true)

  // 一键填入本地预设
  const presetApplied = await cdp.evaluate(`(() => {
    ${HELPERS}
    const presetBtn = [...document.querySelectorAll('button')]
      .find((b) => /Ollama|vLLM|LM Studio/.test(b.innerText || ''))
    if (!presetBtn) return { ok: false, reason: '未找到预设按钮' }
    const label = presetBtn.innerText.trim()
    presetBtn.click()
    return { ok: true, label }
  })()`)
  check('点击本地预设可一键填入', presetApplied.ok === true, presetApplied.label || presetApplied.reason)

  await delay(600)
  // 把地址改成 mock LLM 所在的 11500，并填名称与模型名，使其真正可用
  const filled = await cdp.evaluate(`(() => {
    ${HELPERS}
    const inputs = [...document.querySelectorAll('input')]
    const byPlaceholder = (kw) => inputs.find((i) => (i.placeholder || '').includes(kw))
    const nameInput = byPlaceholder('本地 Qwen') || byPlaceholder('例如')
    if (nameInput) setValue(nameInput, '前端添加的本地模型')
    // 接口地址：找当前值以 http 开头的输入框（预设已填入一个地址）
    const urlInput = inputs.find((i) => /^https?:\\/\\//.test(i.value || ''))
    if (urlInput) setValue(urlInput, 'http://127.0.0.1:11500/v1')
    const modelInput = inputs.find(
      (i) => (i.placeholder || '').includes('qwen2.5:7b') || (i.placeholder || '').includes('deepseek-chat'),
    )
    if (modelInput) setValue(modelInput, 'ui-added-model')
    return {
      name: nameInput ? nameInput.value : null,
      url: urlInput ? urlInput.value : null,
      model: modelInput ? modelInput.value : null,
    }
  })()`)
  check('表单已填入可用的本地模型信息', filled.url === 'http://127.0.0.1:11500/v1' && filled.model === 'ui-added-model',
    JSON.stringify(filled))

  // 保存（会顺带做连通性测试）
  const saved = await cdp.evaluate(`(() => {
    ${HELPERS}
    return clickByText('添加')
  })()`)
  check('提交保存', saved === true)

  // 等待保存 + 探测完成
  let probeText = ''
  for (let i = 0; i < 25; i += 1) {
    await delay(1000)
    const state = await cdp.evaluate(`(() => {
      const text = document.body.innerText
      return {
        passed: text.includes('连接测试通过'),
        failed: text.includes('连接测试未通过'),
        hint: text.includes('正在测试连接'),
      }
    })()`)
    if (state.passed || state.failed) {
      probeText = state.passed ? '连接测试通过' : '连接测试未通过'
      break
    }
  }
  check('保存后自动做连通性测试并通过', probeText === '连接测试通过', probeText || '未观察到测试结果')

  await delay(1500)
  // 关闭对话框，确认新模型出现在下拉且已被选中
  await cdp.evaluate(`(() => {
    ${HELPERS}
    clickByText('取消')
    return true
  })()`)
  await delay(1000)

  const headerState = await cdp.evaluate(`(() => {
    const btn = [...document.querySelectorAll('button')]
      .find((b) => (b.getAttribute('title') || '').includes('当前生成模型'))
    return { title: btn ? btn.getAttribute('title') : '', text: btn ? btn.innerText.trim() : '' }
  })()`)
  check('新模型被自动选中（头部显示）', headerState.text.includes('前端添加的本地模型'),
    `header="${headerState.text}"`)

  // 打开面板确认有「自带」标记与编辑/删除入口
  await cdp.evaluate(`(() => {
    const btn = [...document.querySelectorAll('button')]
      .find((b) => (b.getAttribute('title') || '').includes('当前生成模型'))
    if (btn) btn.click()
    return true
  })()`)
  await delay(1000)
  const listState = await cdp.evaluate(`(() => {
    const text = document.body.innerText
    return {
      hasMine: text.includes('前端添加的本地模型'),
      hasOwnTag: text.includes('自带'),
      hasEdit: Boolean(document.querySelector('button[title="编辑"]')),
      hasDelete: Boolean(document.querySelector('button[title="删除"]')),
    }
  })()`)
  check('下拉中出现自带的模型', listState.hasMine === true)
  check('标注为「自带」', listState.hasOwnTag === true)
  check('自带模型有编辑按钮', listState.hasEdit === true)
  check('自带模型有删除按钮', listState.hasDelete === true)

  await cdp.screenshot('D:/chuangzhibei/docs/screenshots/byom-add-model.png')
  console.log('\n截图：docs/screenshots/byom-add-model.png')
} catch (error) {
  check('测试执行未抛异常', false, String(error?.message || error))
} finally {
  browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${'='.repeat(66)}\n${results.length - failed.length}/${results.length} 通过`)
process.exit(failed.length ? 1 : 0)
