/**
 * 截登录页（队友改了 auth 文案）。
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const OUT = 'E:/传智杯web/docs/screenshots'

const { cdp, close } = await launchBrowser({ debugPort: 9341, windowSize: '1600,1000' })
try {
  await cdp.goto(`${APP}/login?t=${Date.now()}`)
  await delay(2500)
  await cdp.screenshot(`${OUT}/01-login.png`)
  console.log('已保存 01-login.png')

  const text = await cdp.evaluate(`document.body.innerText.replace(/\\n{2,}/g,'\\n').slice(0, 500)`)
  console.log('--- 登录页文本 ---')
  console.log(text)
} finally {
  close()
}
