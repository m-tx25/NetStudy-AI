import { ElMessage } from 'element-plus'

/**
 * 全局错误兜底。
 *
 * 背景（真实事故）：论文对比页的时间轴里有一条「2020 年」的节点没有 documentId，
 * 模板里无条件调用 `paperLabel(undefined)` → 抛 TypeError →
 * **整个主区域白屏**，用户只看到一片黑，完全不知道发生了什么。
 *
 * 三层防护：
 *   1. router.onError：动态分包加载失败（发版后旧页面还开着）→ 自动重载一次
 *   2. app.config.errorHandler：组件渲染/生命周期里的异常 → 控制台 + 顶部提示
 *   3. AppLayout 的 onErrorCaptured：把错误挡在子组件里，主区域显示可点的兜底面板
 */

const RELOAD_FLAG = 'app.chunk-reload-at'

/** 判断是不是「分包加载失败」（发版后 chunk 名字变了，旧页面拿不到） */
function isChunkLoadError(error) {
  const text = String(error?.message || error || '')
  return (
    /Failed to fetch dynamically imported module/i.test(text) ||
    /Importing a module script failed/i.test(text) ||
    /Loading chunk [\d]+ failed/i.test(text) ||
    /error loading dynamically imported module/i.test(text)
  )
}

export function installErrorHandling(app, router) {
  // ---- 1. 分包加载失败：自动重载一次（避免死循环，10 分钟内只重载一次）
  if (router) {
    router.onError((error) => {
      if (!isChunkLoadError(error)) {
        console.error('[router] 路由错误', error)
        return
      }
      const last = Number(sessionStorage.getItem(RELOAD_FLAG) || 0)
      if (Date.now() - last < 60_000) {
        console.error('[router] 分包加载失败，且刚刚重载过，不再自动重试', error)
        ElMessage.error('页面资源已更新，请手动刷新（Ctrl+F5）')
        return
      }
      sessionStorage.setItem(RELOAD_FLAG, String(Date.now()))
      console.warn('[router] 分包加载失败，自动重载以获取新版本', error)
      window.location.reload()
    })
  }

  // ---- 2. 组件内未捕获异常：控制台 + 顶部提示（页面不一定白屏，但要让人知道）
  app.config.errorHandler = (error, instance, info) => {
    console.error('[vue] 未捕获异常', info, error)
    const name = instance?.$options?.name || instance?.$?.type?.name || ''
    ElMessage({
      type: 'error',
      duration: 6000,
      showClose: true,
      message: `页面渲染出错${name ? `（${name}）` : ''}：${String(error?.message || error).slice(0, 80)}`,
    })
  }

  app.config.warnHandler = (message, instance, trace) => {
    if (import.meta.env.DEV) console.warn('[vue:warn]', message, trace)
  }
}
