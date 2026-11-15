/** 量首页英雄区各元素宽度，定位被裁原因。 */
import { launchBrowser, delay } from './lib/cdp.mjs'

const APP = process.env.APP_URL || 'http://localhost:5173'
const { cdp, close } = await launchBrowser({ debugPort: 9362, windowSize: '390,844' })
try {
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 390, height: 844, deviceScaleFactor: 2, mobile: true,
  })
  await cdp.goto(`${APP}/?t=${Date.now()}`)
  await delay(2500)
  const info = await cdp.evaluate(`(() => {
    const pick = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x),
               overflowX: cs.overflowX, whiteSpace: cs.whiteSpace, maxW: cs.maxWidth };
    };
    const p = document.querySelector('section p');
    return {
      viewport: innerWidth,
      grid: pick('section > div.relative.mx-auto'),
      leftCol: pick('section .reveal'),
      paragraph: p ? pick('section p') : null,
      pScrollW: p ? p.scrollWidth : null,
      pClientW: p ? p.clientWidth : null,
      h1: pick('section h1'),
    };
  })()`)
  console.log(JSON.stringify(info, null, 2))
} finally {
  close()
}
