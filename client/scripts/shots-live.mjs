/** 截公网线上站点，确认静态资源与页面正常。 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const SITE = process.env.SITE_URL || 'http://8.163.132.51'
const OUT = 'E:/传智杯web/docs/screenshots/deploy'

const { cdp, close } = await launchBrowser({ debugPort: 9350, windowSize: '1600,1000' })
try {
  await cdp.goto(`${SITE}/`)
  await delay(3000)
  await cdp.screenshot(`${OUT}/01-live-home.png`)
  console.log('已保存 01-live-home.png')

  const info = await cdp.evaluate(`(() => {
    const imgs = [...document.images];
    const failed = imgs.filter((i) => !i.complete || i.naturalWidth === 0).length;
    return {
      title: document.title,
      h1: (document.querySelector('h1') || {}).innerText || '',
      images: imgs.length,
      failedImages: failed,
      bg: getComputedStyle(document.body).backgroundColor,
    };
  })()`)
  console.log('页面信息:', JSON.stringify(info, null, 2))
} finally {
  close()
}
