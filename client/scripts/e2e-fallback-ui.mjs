/**
 * 验证「无依据回退」在界面上的呈现：提问一个知识库里没有的问题，
 * 应看到橙色的「知识库中未检索到相关依据」标注 + 引导上传文档。
 * 前置：后端(3000，已配 LLM) + 前端(5173) 已启动。
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.argv[2] || 'http://localhost:5173'
const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  -> ${detail}` : ''}`)
}

const browser = await launchBrowser({ debugPort: 9449, windowSize: '1440,1000' })
const { cdp } = browser

try {
  await cdp.goto(`${APP}/login`)
  await delay(1500)
  await cdp.evaluate(`(() => {
    const setValue = (el, v) => {
      if (!el) return false
      const proto = window.HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
      return true
    }
    setValue(document.querySelector('input[autocomplete="username"]'), 'demo')
    setValue(document.querySelector('input[autocomplete="current-password"]'), '123456')
    const btn = [...document.querySelectorAll('button')].find((b) => (b.innerText || '').includes('登'))
    if (btn) btn.click()
    return true
  })()`)
  await delay(3500)

  /** 在输入框提问并等待回答完成 */
  async function ask(question) {
    await cdp.evaluate(`(() => {
      const area = document.querySelector('textarea')
      if (!area) return false
      const proto = window.HTMLTextAreaElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(area, ${JSON.stringify(question)})
      area.dispatchEvent(new Event('input', { bubbles: true }))
      return true
    })()`)
    await delay(400)
    await cdp.evaluate(`(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => {
        const t = (b.innerText || '').trim()
        return t === '发送' || t.includes('发送')
      })
      if (btn) { btn.click(); return true }
      // 兜底：直接派发 Enter
      const area = document.querySelector('textarea')
      if (area) {
        area.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
        return true
      }
      return false
    })()`)
    // 等待回答结束（出现「重新生成」按钮或标注）
    for (let i = 0; i < 40; i += 1) {
      await delay(1000)
      const done = await cdp.evaluate(`(() => {
        const text = document.body.innerText
        return text.includes('非知识库依据') || text.includes('引用来源') || text.includes('重新生成')
      })()`)
      if (done) break
    }
    await delay(1500)
  }

  /* ---------- 场景 1：知识库里没有的问题 ---------- */
  await ask('请用一句话解释量子纠缠，并给出一个生活化类比。')

  const missState = await cdp.evaluate(`(() => {
    const text = document.body.innerText
    return {
      hasBanner: text.includes('知识库中未检索到相关依据'),
      hasDisclaimer: text.includes('并非来自你上传的文档'),
      hasGuide: text.includes('知识库管理'),
      hasSourceChip: text.includes('引用来源'),
    }
  })()`)
  check('界面出现「未检索到相关依据」标注', missState.hasBanner === true)
  check('标注说明「并非来自你上传的文档」', missState.hasDisclaimer === true)
  check('标注引导用户去知识库管理上传', missState.hasGuide === true)
  check('无依据时不显示「引用来源」', missState.hasSourceChip === false, `hasSourceChip=${missState.hasSourceChip}`)

  await cdp.screenshot('D:/chuangzhibei/docs/screenshots/fallback-banner.png')
  console.log('截图：docs/screenshots/fallback-banner.png')

  /* ---------- 场景 2：知识库里有的问题 ---------- */
  await ask('报销流程分几步？单张发票超过多少金额需要附加采购申请单编号？')

  const hitState = await cdp.evaluate(`(() => {
    const text = document.body.innerText
    // 只检查最后一条回答对应的区域：取最后一个助手气泡
    const bubbles = [...document.querySelectorAll('.markdown-body')]
    const last = bubbles[bubbles.length - 1]
    const lastWrap = last ? last.closest('div') : null
    return {
      hasSourceChip: text.includes('引用来源'),
      // 只要页面上还有标注，就说明本轮可能也走了回退
      anyBanner: text.includes('知识库中未检索到相关依据'),
      lastSnippet: last ? (last.innerText || '').slice(0, 60) : '',
    }
  })()`)
  check('有依据的问题显示了「引用来源」', hitState.hasSourceChip === true, hitState.lastSnippet.replace(/\n/g, ' '))
} catch (error) {
  check('测试执行未抛异常', false, String(error?.message || error))
} finally {
  browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${'='.repeat(60)}\n${results.length - failed.length}/${results.length} 通过`)
process.exit(failed.length ? 1 : 0)
