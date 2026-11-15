/**
 * 截首页功能区块（队友 e1423c8 改的部分）。
 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const OUT = 'E:/传智杯web/docs/screenshots'

const { cdp, close } = await launchBrowser({ debugPort: 9340, windowSize: '1600,1000' })
try {
  await cdp.goto(`${APP}/?t=${Date.now()}`)
  await delay(2500)

  const scrolled = await cdp.evaluate(`(() => {
    const heads = [...document.querySelectorAll('h2,h3')].map(h => (h.textContent || '').trim());
    const target = [...document.querySelectorAll('h2')].find(h => /能力|功能/.test(h.textContent || ''));
    if (target) target.scrollIntoView({ block: 'start' });
    else window.scrollTo(0, 900);
    return heads.slice(0, 10).join(' | ');
  })()`)
  console.log('标题:', scrolled)

  await delay(1200)
  await cdp.screenshot(`${OUT}/02-home-features.png`)
  console.log('已保存 02-home-features.png')
} finally {
  close()
}
