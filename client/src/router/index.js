import { createRouter, createWebHistory } from 'vue-router'

import { setUnauthorizedHandler } from '@/api/request'
import { APP_TITLE } from '@/config'
import { useUserStore } from '@/stores/user'

const AppLayout = () => import('@/layouts/AppLayout.vue')

const routes = [
  {
    // 落地首页：公开访问，占满整屏、可滚动，登录入口收成导航栏上的按钮
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '产品首页' },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', guestOnly: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { title: '注册', guestOnly: true },
  },
  {
    // 工作台：问答 / 知识库 / 设置，全部需要登录
    path: '/app',
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: { name: 'chat-new' } },
      {
        path: 'chat',
        name: 'chat-new',
        component: () => import('@/views/ChatView.vue'),
        meta: { title: '智能问答' },
      },
      {
        path: 'chat/:id',
        name: 'chat',
        component: () => import('@/views/ChatView.vue'),
        meta: { title: '智能问答' },
      },
      {
        path: 'knowledge',
        name: 'knowledge',
        component: () => import('@/views/KnowledgeView.vue'),
        meta: { title: '知识库管理' },
      },
      {
        path: 'teams',
        name: 'teams',
        component: () => import('@/views/TeamsView.vue'),
        meta: { title: '团队' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/SettingsView.vue'),
        meta: { title: '账号设置' },
      },
    ],
  },
  // 兼容历史链接：/chat、/knowledge、/settings 一律跳转到 /app 下
  { path: '/chat', redirect: '/app/chat' },
  { path: '/chat/:id', redirect: (to) => `/app/chat/${to.params.id}` },
  { path: '/knowledge', redirect: '/app/knowledge' },
  { path: '/teams', redirect: '/app/teams' },
  { path: '/settings', redirect: '/app/settings' },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  // 首页锚点（#features / #workflow ...）需要真正滚过去，其余情况回到顶部
  scrollBehavior: (to) => (to.hash ? { el: to.hash, behavior: 'smooth' } : { top: 0 }),
})

router.beforeEach(async (to) => {
  const userStore = useUserStore()

  // 进入需要登录的页面前，先确认本地 token 真的还有效。
  // 仅判断「本地有没有 token」是不够的：后端换过 SECRET_KEY、改过密码或重建过库之后，
  // 旧 token 依然存在于 localStorage，守卫会放行，页面随即并发请求全部 401，
  // 用户看到「登录状态已失效」却不知道发生了什么。
  if (to.meta.requiresAuth) {
    await userStore.ensureSessionChecked()
  }

  if (to.meta.requiresAuth && !userStore.isAuthenticated) {
    return { name: 'login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  }

  // 已登录用户访问首页时保留首页（导航栏按钮会变成「进入工作台」），
  // 但主动访问登录/注册页时直接进工作台。
  if (to.meta.guestOnly && userStore.isAuthenticated) {
    return { name: 'chat-new' }
  }

  return true
})

router.afterEach((to) => {
  const base = APP_TITLE
  document.title = to.meta.title ? `${to.meta.title} · ${base}` : base
})

// token 失效时统一跳登录页
setUnauthorizedHandler(() => {
  const current = router.currentRoute.value
  if (current.name === 'login') return
  router.replace({ name: 'login', query: current.fullPath ? { redirect: current.fullPath } : {} })
})

export default router
