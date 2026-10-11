import { createApp } from 'vue'
import { createPinia } from 'pinia'

import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIcons from '@element-plus/icons-vue'

// 样式加载顺序很重要：Element Plus 先加载，Tailwind（style.css）后加载，
// 这样同为单类名选择器时 Tailwind 工具类能覆盖组件默认样式。
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './style.css'

import App from './App.vue'
import router from './router'
import { applyStoredTheme } from '@/composables/useTheme'
import { isMockMode } from '@/config'

applyStoredTheme()

const app = createApp(App)

// 图标全量注册，模板里可直接写 <el-icon><Plus /></el-icon>
for (const [name, component] of Object.entries(ElementPlusIcons)) {
  app.component(name, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

if (isMockMode) {
  // eslint-disable-next-line no-console
  console.info(
    '%c[RAG] 当前为 Mock 演示模式：不会请求真实后端。\n切换方式：把 client/.env.development 里的 VITE_USE_MOCK 改为 false 并重启 dev server。',
    'color:#10a37f;font-weight:600',
  )
}

app.mount('#app')
