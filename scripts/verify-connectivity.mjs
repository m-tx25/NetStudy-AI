/**
 * 前后端连通性端到端验证。
 * 依次探测：后端直连 → 前端服务 → 前端代理转发 → 前端构建产物。
 */
const results = []

async function probe(name, url, check) {
  const started = Date.now()
  try {
    const res = await fetch(url, { redirect: 'follow' })
    const body = await res.text()
    const ms = Date.now() - started
    const verdict = check(res, body)
    results.push({ name, url, ok: verdict.ok, note: verdict.note, status: res.status, ms })
  } catch (err) {
    const ms = Date.now() - started
    results.push({ name, url, ok: false, note: 'EXCEPTION: ' + (err.cause?.code || err.message), status: '-', ms })
  }
}

const isJson = (res, body) => {
  let parsed = null
  try {
    parsed = JSON.parse(body)
  } catch {
    return { ok: false, note: 'not JSON: ' + body.slice(0, 80) }
  }
  return { ok: true, note: JSON.stringify(parsed) }
}

// 1. 后端直连
await probe('后端直连 /api/health', 'http://localhost:3000/api/health', (res, body) => {
  const r = isJson(res, body)
  if (!r.ok) return r
  const d = JSON.parse(body)
  return { ok: res.status === 200 && d.ok === true, note: `ok=${d.ok} service=${d.service}` }
})

// 2. 前端首页
await probe('前端首页 /', 'http://localhost:5173/', (res, body) => ({
  ok: res.status === 200 && /<div id="app">/.test(body),
  note: /<div id="app">/.test(body) ? 'index.html 含 #app 挂载点' : '未找到 #app',
}))

// 3. 关键：经前端代理访问后端（这才是"打通"）
await probe('前端代理 /api/health → 3000', 'http://localhost:5173/api/health', (res, body) => {
  const r = isJson(res, body)
  if (!r.ok) return r
  const d = JSON.parse(body)
  return {
    ok: res.status === 200 && d.ok === true && d.service === 'chuangzhibei-server',
    note: `经 5173 代理拿到后端响应: service=${d.service}`,
  }
})

// 4. 前端 SFC 是否正常编译
await probe('SFC 编译 HomeView.vue', 'http://localhost:5173/src/views/HomeView.vue', (res, body) => ({
  ok: res.status === 200 && /createElementBlock|openBlock|_createElementVNode/.test(body),
  note: /createElementBlock|openBlock|_createElementVNode/.test(body) ? '已编译为 render 函数' : '未见 render 函数',
}))

// 5. 后端 404 统一处理是否生效
await probe('后端 404 处理', 'http://localhost:3000/api/does-not-exist', (res, body) => {
  const r = isJson(res, body)
  return { ok: res.status === 404 && r.ok, note: r.note }
})

const pad = (s, n) => String(s).padEnd(n)
console.log('\n================ 连通性验证结果 ================')
for (const r of results) {
  console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${pad(r.name, 28)} HTTP ${pad(r.status, 5)} ${pad(r.ms + 'ms', 8)} ${r.note}`)
}
const failed = results.filter((r) => !r.ok)
console.log('===============================================')
console.log(`${results.length - failed.length}/${results.length} 通过`)
process.exit(failed.length === 0 ? 0 : 1)
