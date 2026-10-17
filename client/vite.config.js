import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  // PostCSS 直接内联，避免不同 Vite 版本对 postcss.config.js 的查找差异
  css: {
    postcss: {
      plugins: [
        // 显式指定 config 路径，避免因 cwd 不同导致 Tailwind 找不到配置而产出空样式
        tailwindcss({ config: fileURLToPath(new URL('./tailwind.config.js', import.meta.url)) }),
        autoprefixer(),
      ],
    },
  },
  server: {
    port: 5173,
    open: false,
    // 前端统一用相对路径请求 /api/**，由 Vite 转发到 Express，避免开发期跨域
    proxy: {
      '/api': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        // SSE 不能被缓冲，否则「打字机效果」会变成一次性吐完
        configure(proxy) {
          if (typeof proxy?.on !== 'function') return
          proxy.on('proxyRes', (proxyRes) => {
            const contentType = String(proxyRes.headers?.['content-type'] || '')
            if (contentType.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform'
              proxyRes.headers['x-accel-buffering'] = 'no'
            }
          })
        },
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1600,
  },
})
