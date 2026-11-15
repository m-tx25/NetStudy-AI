/**
 * 注册 Service Worker：仅在**生产构建**里注册。
 *
 * 开发环境不注册的原因：SW 会缓存 HTML 与 assets，
 * 改代码后页面反复拿到旧版本，热更新看起来「失效」，排查起来非常费时。
 */
export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return
  if (import.meta.env.DEV) return

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch((error) => {
      // 注册失败不影响主流程（例如 http 访问且非 localhost 时浏览器会拒绝）
      console.warn('[PWA] Service Worker 注册失败', error)
    })
  })
}
