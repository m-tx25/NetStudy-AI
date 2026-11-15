/* eslint-disable no-restricted-globals */
/**
 * Service Worker：让「添加到主屏」后能像 App 一样启动。
 *
 * 策略：
 *   - 静态资源（/assets/* 带内容哈希）→ 缓存优先，命中即返回，永不失效
 *   - 导航请求（HTML）→ 网络优先，失败时回落缓存的首页（离线也能看到壳）
 *   - /api/* 一律直连，**绝不缓存**（问答结果是动态的，缓存会读到过期引用）
 */
const VERSION = 'v1'
const SHELL_CACHE = `matrix-shell-${VERSION}`
const ASSET_CACHE = `matrix-assets-${VERSION}`

// 首次安装时缓存应用外壳
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('matrix-') && key !== SHELL_CACHE && key !== ASSET_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  // 接口：直连，不缓存（引用/流式结果必须是实时的）
  if (url.pathname.startsWith('/api/')) return

  // 带哈希的静态资源：缓存优先
  if (url.pathname.startsWith('/assets/') || /\.(png|svg|woff2?|ttf|ico)$/.test(url.pathname)) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            const copy = response.clone()
            caches.open(ASSET_CACHE).then((cache) => cache.put(request, copy))
            return response
          }),
      ),
    )
    return
  }

  // 导航请求：网络优先，离线回落首页
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match('/index.html').then((hit) => hit || caches.match('/')),
      ),
    )
  }
})
