<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  ArrowRight,
  ChatDotRound,
  CircleCheck,
  Coin,
  Connection,
  DataAnalysis,
  Document,
  DocumentChecked,
  Expand,
  Film,
  Files,
  Lock,
  Moon,
  OfficeBuilding,
  Position,
  Reading,
  Search,
  Sunny,
  Timer,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'

import SiteFooter from '@/components/landing/SiteFooter.vue'
import PolicyDialog from '@/components/auth/PolicyDialog.vue'
import { useReveal } from '@/composables/useReveal'
import { useTheme } from '@/composables/useTheme'
import { useUserStore } from '@/stores/user'
import { APP_TITLE, isMockMode } from '@/config'

const router = useRouter()
const userStore = useUserStore()
const { isDark, toggleTheme } = useTheme()

const pageRef = ref(null)
useReveal(pageRef)

/* ------------------------------------------------------------------ *
 * 导航
 * ------------------------------------------------------------------ */
const navLinks = [
  { label: '产品能力', href: '#features' },
  { label: '使用流程', href: '#workflow' },
  { label: '技术架构', href: '#tech' },
  { label: '常见问题', href: '#faq' },
]

const scrolled = ref(false)
const menuOpen = ref(false)

function onScroll() {
  scrolled.value = window.scrollY > 10
}

onMounted(() => {
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
})

const workspaceTarget = computed(() => ({ name: 'chat-new' }))

function goWorkspace() {
  menuOpen.value = false
  router.push(workspaceTarget.value)
}

/* ------------------------------------------------------------------ *
 * 首屏关键数字
 * ------------------------------------------------------------------ */
const stats = [
  { value: '10+', label: '文档格式解析', desc: 'PDF / Word / 表格 / 网页' },
  { value: 'Top-K', label: '可调召回范围', desc: '按知识库精确圈定检索域' },
  { value: 'SSE', label: '流式回答', desc: '首字节即开始输出' },
  { value: '100%', label: '答案带出处', desc: '每条结论可点开原文核对' },
]

/* ------------------------------------------------------------------ *
 * 产品能力
 * ------------------------------------------------------------------ */
const features = [
  {
    icon: Files,
    title: '全格式文档接入',
    desc: 'PDF、Word、Markdown、Excel、PPT 与网页一键上传，自动解析、分块并向量化。',
    tag: '上传即用',
  },
  {
    icon: Search,
    title: '语义检索召回',
    desc: '向量检索锁定与问题最相关的片段，避免大模型在整篇文档里「凭印象作答」。',
    tag: '语义匹配',
  },
  {
    icon: DocumentChecked,
    title: '引用可溯源',
    desc: '回答中的关键结论附带原文出处、页码与相关度，点开即可逐条核对。',
    tag: '有据可依',
  },
  {
    icon: Lock,
    title: '数据不出内网',
    desc: '支持私有化部署，文档与向量库全部落在你指定的环境中。',
    tag: '私有化',
  },
  {
    icon: OfficeBuilding,
    title: '面向团队协作',
    desc: '知识库分级管理、会话留痕、检索范围与召回参数随问随调。',
    tag: '多知识库',
  },
  {
    icon: Connection,
    title: '开放接口',
    desc: '标准 REST + SSE 流式接口，方便接入企业现有门户与业务系统。',
    tag: '易集成',
  },
]

/* ------------------------------------------------------------------ *
 * 使用流程
 * ------------------------------------------------------------------ */
const workflow = [
  {
    step: '01',
    title: '创建知识库',
    desc: '按业务线或部门划分知识库，作为检索时的最小范围单位。',
    icon: Files,
  },
  {
    step: '02',
    title: '上传并解析文档',
    desc: '上传后自动完成解析、清洗、分块与向量化，进度实时可见。',
    icon: Document,
  },
  {
    step: '03',
    title: '提问并获得引用',
    desc: '选定检索范围后提问，回答逐字流式输出，并附上来源片段。',
    icon: ChatDotRound,
  },
  {
    step: '04',
    title: '核对与沉淀',
    desc: '点开引用回溯原文，把高频问题沉淀为团队标准答案。',
    icon: CircleCheck,
  },
]

/* ------------------------------------------------------------------ *
 * 技术架构
 * ------------------------------------------------------------------ */
const pipeline = ['文档上传', '解析清洗', '语义分块', '向量化', '检索召回', '生成回答']

const architecture = [
  {
    title: '数据接入层',
    icon: DataAnalysis,
    items: ['多格式解析器', '增量索引更新', '文档版本管理', '失败任务重试'],
  },
  {
    title: '向量检索层',
    icon: Position,
    items: ['文本分块与 Embedding', '相似度阈值过滤', 'Top-K 召回可调', '多知识库联合检索'],
  },
  {
    title: '生成与引用层',
    icon: Reading,
    items: ['上下文拼装与提示词控制', 'SSE 流式输出', '引用片段与相关度', '回答可重新生成'],
  },
]

const guards = ['传输加密', '权限分级', '操作审计', '私有化部署']

/* ------------------------------------------------------------------ *
 * 适用场景
 * ------------------------------------------------------------------ */
const scenarios = [
  {
    key: 'edu',
    label: '教育培训',
    icon: Reading,
    title: '课程资料变成随时可问的助教',
    desc: '把课件、习题解析、培养方案接入知识库，学生提问直接命中讲义原文，老师不必重复答疑。',
    points: ['课件与讲义统一检索', '答案标注章节出处', '按班级划分知识库'],
  },
  {
    key: 'law',
    label: '法务合规',
    icon: OfficeBuilding,
    title: '合同与制度条款逐条可核',
    desc: '合同模板、内部制度、监管文件入库后，条款级检索让每一次引用都有原文支撑。',
    points: ['条款级精确召回', '引用带页码定位', '历史版本可追溯'],
  },
  {
    key: 'tech',
    label: '研发支持',
    icon: Connection,
    title: '技术文档与接口手册即问即答',
    desc: '把接口文档、部署手册、故障复盘沉淀进知识库，新同学不必再翻十几个仓库找答案。',
    points: ['多仓库文档聚合', '代码片段高亮展示', '会话记录可回溯'],
  },
  {
    key: 'service',
    label: '客户服务',
    icon: ChatDotRound,
    title: '客服话术与工单经验复用',
    desc: '标准话术、常见故障处理流程入库，坐席提问即得带出处的处置建议。',
    points: ['标准话术一键检索', '处理流程分步输出', '高频问题沉淀复用'],
  },
]

const activeScenario = ref('edu')
const currentScenario = computed(
  () => scenarios.find((item) => item.key === activeScenario.value) || scenarios[0],
)

/* ------------------------------------------------------------------ *
 * 常见问题
 * ------------------------------------------------------------------ */
const faqs = [
  {
    q: '和直接把文档丢给大模型有什么区别？',
    a: '直接投喂受限于上下文长度，且模型容易「编」。本系统先用向量检索在你的知识库里定位最相关的片段，再让模型基于这些片段作答，因此答案更准、更短，并且每条结论都能指出原文出处。',
  },
  {
    q: '支持哪些文档格式？',
    a: 'PDF、Word（doc/docx）、Markdown、纯文本、CSV、Excel、PPT、HTML 与 JSON 都可以上传，系统会按格式选择解析器，自动分块并写入向量库。',
  },
  {
    q: '文档数据会上传到第三方吗？',
    a: '不会。向量库与文件存储都部署在你指定的环境里，支持完全离线的私有化部署；界面上也提供传输加密、权限分级与操作审计能力。',
  },
  {
    q: '回答不准时可以怎么调整？',
    a: '提问前可以勾选参与检索的知识库，并调整召回数量 Top-K 与相似度阈值：范围收窄、阈值提高会让答案更保守但更精准。也可以直接点开引用片段核对原文。',
  },
  {
    q: '多人协作如何管理？',
    a: '知识库与文档按账号维度隔离，会话自动留痕并按日期归档；管理员可以统一维护知识库与文档生命周期。',
  },
  {
    q: '如何接入我们自己的系统？',
    a: '后端提供标准 REST 接口与 SSE 流式问答接口，前端也内置了会话、知识库、检索参数的完整实现，可直接对接企业门户或工单系统。',
  },
]
</script>

<template>
  <div ref="pageRef" class="min-h-screen app-bg">
    <!-- ============================ 顶部导航 ============================ -->
    <header
      class="fixed inset-x-0 top-0 z-50 transition-colors duration-300"
      :class="scrolled ? 'border-b app-border backdrop-blur-xl' : 'border-b border-transparent'"
      :style="scrolled ? 'background-color: color-mix(in srgb, var(--app-bg) 82%, transparent)' : ''"
    >
      <div class="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-5 sm:px-8">
        <RouterLink :to="{ name: 'home' }" class="flex shrink-0 items-center gap-2.5">
          <span
            class="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-light to-brand text-sm font-bold text-white shadow-lg shadow-brand/25"
          >
            R
          </span>
          <span class="hidden text-[15px] font-semibold tracking-tight app-text sm:block">
            {{ APP_TITLE }}
          </span>
        </RouterLink>

        <!-- 桌面端锚点导航 -->
        <nav class="ml-6 hidden items-center gap-1 lg:flex">
          <a
            v-for="link in navLinks"
            :key="link.href"
            :href="link.href"
            class="rounded-lg px-3 py-2 text-[13px] app-muted transition hover-app-text"
          >
            {{ link.label }}
          </a>
        </nav>

        <div class="ml-auto flex items-center gap-2">
          <span
            v-if="isMockMode"
            class="hidden rounded-full border app-border px-2.5 py-1 text-[11px] app-muted sm:inline-block"
          >
            演示模式
          </span>

          <button
            class="grid h-9 w-9 place-items-center rounded-lg app-muted transition app-hover hover-app-text"
            :title="isDark ? '切换为浅色' : '切换为深色'"
            @click="toggleTheme"
          >
            <el-icon><Sunny v-if="isDark" /><Moon v-else /></el-icon>
          </button>

          <!-- 未登录：登录 / 注册按钮 -->
          <template v-if="!userStore.isAuthenticated">
            <RouterLink
              :to="{ name: 'login' }"
              class="hidden rounded-xl px-4 py-2 text-[13px] font-medium app-text transition app-hover sm:block"
            >
              登录
            </RouterLink>
            <RouterLink
              :to="{ name: 'register' }"
              class="tech-button-solid rounded-xl px-4 py-2 text-[13px] font-medium"
            >
              免费注册
            </RouterLink>
          </template>

          <!-- 已登录：进入工作台 -->
          <template v-else>
            <button
              class="tech-button-solid flex items-center gap-1.5 rounded-xl px-4 py-2 text-[13px] font-medium"
              @click="goWorkspace"
            >
              进入工作台
              <el-icon><ArrowRight /></el-icon>
            </button>
            <span
              class="hidden h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-light to-brand text-xs font-semibold text-white md:grid"
              :title="userStore.displayName"
            >
              {{ userStore.avatarText }}
            </span>
          </template>

          <!-- 移动端菜单 -->
          <button
            class="grid h-9 w-9 place-items-center rounded-lg app-muted transition app-hover hover-app-text lg:hidden"
            title="菜单"
            @click="menuOpen = !menuOpen"
          >
            <el-icon><Expand /></el-icon>
          </button>
        </div>
      </div>

      <!-- 移动端展开面板 -->
      <div
        v-if="menuOpen"
        class="border-t app-border px-5 pb-4 pt-2 lg:hidden"
        style="background-color: var(--app-canvas)"
      >
        <a
          v-for="link in navLinks"
          :key="link.href"
          :href="link.href"
          class="block rounded-lg px-3 py-2.5 text-sm app-muted transition app-hover hover-app-text"
          @click="menuOpen = false"
        >
          {{ link.label }}
        </a>
        <RouterLink
          v-if="!userStore.isAuthenticated"
          :to="{ name: 'login' }"
          class="mt-1 block rounded-lg px-3 py-2.5 text-sm app-text transition app-hover"
          @click="menuOpen = false"
        >
          登录
        </RouterLink>
      </div>
    </header>

    <main class="pt-16">
      <!-- ============================ 首屏 ============================ -->
      <section class="relative overflow-hidden">
        <div class="pointer-events-none absolute inset-0 tech-grid tech-grid-fade opacity-70" />
        <div class="tech-glow -left-24 -top-24 h-[26rem] w-[26rem] animate-pulse-glow" />
        <div
          class="tech-glow -right-20 top-24 h-[22rem] w-[22rem] animate-pulse-glow"
          style="background: #38bdf8; opacity: 0.1"
        />
        <div
          class="pointer-events-none absolute inset-x-0 bottom-0 h-32"
          style="background: linear-gradient(to top, var(--app-bg), transparent)"
        />

        <div
          class="relative mx-auto grid w-full max-w-6xl items-center gap-10 px-5 py-16 sm:px-8 lg:min-h-[calc(100vh-4rem)] lg:grid-cols-[1.05fr_0.95fr] lg:gap-12 lg:py-14"
        >
          <!-- 左：文案 -->
          <div class="reveal">
            <span
              class="inline-flex items-center gap-2 rounded-full border app-border px-3 py-1.5 text-[11px] app-muted tech-glass"
            >
              <span class="relative flex h-1.5 w-1.5">
                <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-light opacity-75" />
                <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand-light" />
              </span>
              检索增强生成 · RAG 架构
            </span>

            <h1 class="mt-6 text-balance text-[34px] font-semibold leading-[1.25] tracking-tight app-text sm:text-[44px] lg:text-[50px]">
              让每一个答案<br />
              都能追溯到<span class="tech-gradient-text">原文出处</span>
            </h1>

            <p class="mt-6 max-w-xl text-[15px] leading-8 app-muted">
              把团队的文档交给大模型之前，先用向量检索锁定最相关的片段。
              回答有据可依、结论可核可查——这是企业场景使用 AI 的底线。
            </p>

            <div class="mt-9 flex flex-wrap items-center gap-3">
              <RouterLink
                v-if="!userStore.isAuthenticated"
                :to="{ name: 'login' }"
                class="tech-button-solid inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-medium"
              >
                立即登录使用
                <el-icon><ArrowRight /></el-icon>
              </RouterLink>
              <button
                v-else
                class="tech-button-solid inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-medium"
                @click="goWorkspace"
              >
                进入工作台
                <el-icon><ArrowRight /></el-icon>
              </button>

              <a
                href="#features"
                class="tech-button inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-medium"
              >
                了解产品能力
              </a>
            </div>

            <dl class="mt-10 grid max-w-xl grid-cols-2 gap-x-6 gap-y-5 sm:mt-12 sm:grid-cols-4">
              <div v-for="item in stats" :key="item.label">
                <dt class="font-mono text-xl font-semibold app-accent">{{ item.value }}</dt>
                <dd class="mt-1 text-[13px] app-text-secondary">{{ item.label }}</dd>
                <dd class="mt-0.5 text-[11px] app-faint">{{ item.desc }}</dd>
              </div>
            </dl>
          </div>

          <!-- 右：产品预览 -->
          <div class="reveal relative" style="transition-delay: 120ms">
            <div
              class="pointer-events-none absolute -inset-6 rounded-[32px] opacity-40"
              style="background: radial-gradient(circle at 70% 20%, var(--app-accent-glow), transparent 60%)"
            />

            <div class="group relative overflow-hidden rounded-3xl tech-glass shadow-2xl">
              <!-- 窗口栏 -->
              <div class="flex items-center gap-2 border-b app-border px-4 py-3">
                <span class="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
                <span class="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
                <span class="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
                <span class="ml-3 font-mono text-[11px] app-faint">rag-workspace / chat</span>
                <span class="ml-auto inline-flex items-center gap-1.5 text-[11px] app-muted">
                  <span class="h-1.5 w-1.5 rounded-full bg-brand-light" />
                  已连接知识库
                </span>
              </div>

              <div class="relative space-y-4 px-4 py-5 sm:px-5">
                <!-- 提问 -->
                <div class="flex justify-end">
                  <p
                    class="max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-[13px] leading-6 text-white"
                    style="background-image: linear-gradient(135deg, #25c39c, #0f9b7a)"
                  >
                    员工入职当天需要提交哪些材料？
                  </p>
                </div>

                <!-- 回答 -->
                <div class="flex gap-2.5">
                  <span
                    class="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-light to-brand text-[11px] font-bold text-white"
                  >
                    R
                  </span>
                  <div class="min-w-0 flex-1">
                    <div class="rounded-2xl rounded-tl-md border app-border app-panel px-4 py-3">
                      <p class="text-[13px] leading-6 app-text-secondary">
                        根据《员工入职手册（2024 修订版）》，入职当天需提交：身份证复印件 2 份、
                        学历证书复印件、体检报告、一寸照片 3 张，并现场签署保密协议。<span
                          class="ml-0.5 inline-block h-3.5 w-[7px] translate-y-0.5 animate-pulse rounded-sm bg-brand-light align-middle"
                        />
                      </p>

                      <div class="mt-3 space-y-1.5">
                        <div
                          class="flex items-center gap-2 rounded-lg border app-border app-canvas px-2.5 py-2"
                        >
                          <span class="accent-bar h-6 w-[3px] shrink-0 rounded-full bg-brand-light" />
                          <el-icon class="shrink-0 text-[13px] app-accent"><Document /></el-icon>
                          <span class="min-w-0 flex-1 truncate font-mono text-[11px] app-muted">
                            员工入职手册.pdf · 第 6 页
                          </span>
                          <span class="shrink-0 font-mono text-[10px] app-accent">0.87</span>
                        </div>
                        <div
                          class="flex items-center gap-2 rounded-lg border app-border app-canvas px-2.5 py-2"
                        >
                          <span class="h-6 w-[3px] shrink-0 rounded-full" style="background: #38bdf8" />
                          <el-icon class="shrink-0 text-[13px]" style="color: #38bdf8"><Document /></el-icon>
                          <span class="min-w-0 flex-1 truncate font-mono text-[11px] app-muted">
                            HR 流程说明.md · 入职材料清单
                          </span>
                          <span class="shrink-0 font-mono text-[10px] app-accent">0.79</span>
                        </div>
                      </div>
                    </div>

                    <div class="mt-2 flex items-center gap-3 text-[11px] app-faint">
                      <span class="inline-flex items-center gap-1">
                        <el-icon><CircleCheck /></el-icon>
                        已完成，用时 1.4s
                      </span>
                      <span>引用 2 条</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 输入条 -->
              <div class="border-t app-border px-4 py-3">
                <div
                  class="flex items-center gap-2 rounded-2xl border app-border app-panel px-3 py-2.5"
                >
                  <el-icon class="text-sm app-faint"><Search /></el-icon>
                  <span class="flex-1 truncate text-[12px] app-faint">
                    继续追问，例如「体检报告有什么有效期要求？」
                  </span>
                  <span
                    class="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-light to-brand text-white"
                  >
                    <el-icon class="text-xs"><Position /></el-icon>
                  </span>
                </div>
                <div class="mt-2.5 flex items-center gap-2 text-[10px] app-faint">
                  <span class="rounded-md border app-border px-1.5 py-0.5">知识库：人力资源</span>
                  <span class="rounded-md border app-border px-1.5 py-0.5">Top-K：5</span>
                  <span class="rounded-md border app-border px-1.5 py-0.5">阈值：0.20</span>
                  <span class="ml-auto animate-float">流式输出中…</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============================ 产品能力 ============================ -->
      <section id="features" class="scroll-mt-24 border-t app-border">
        <div class="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8">
          <div class="reveal max-w-2xl">
            <p class="font-mono text-xs tracking-[0.2em] app-accent">CAPABILITIES</p>
            <h2 class="mt-3 text-[28px] font-semibold tracking-tight app-text sm:text-[34px]">
              把文档变成可检索、可核对的知识
            </h2>
            <p class="mt-4 text-[15px] leading-8 app-muted">
              从上传解析到流式回答，每一步都为「可核查」服务：检索范围能收窄，召回参数能调整，
              引用片段能点开。
            </p>
          </div>

          <div class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <article
              v-for="(item, index) in features"
              :key="item.title"
              class="reveal tech-lift group rounded-2xl tech-glass p-6"
              :style="`transition-delay: ${(index % 3) * 90}ms`"
            >
              <div class="flex items-start justify-between">
                <span
                  class="grid h-11 w-11 place-items-center rounded-xl border app-border app-panel text-base app-accent transition group-hover:border-brand-light/60"
                >
                  <el-icon class="app-accent"><component :is="item.icon" /></el-icon>
                </span>
                <span class="rounded-full border app-border px-2.5 py-1 text-[10px] app-muted">
                  {{ item.tag }}
                </span>
              </div>
              <h3 class="mt-5 text-[15px] font-semibold app-text">{{ item.title }}</h3>
              <p class="mt-2 text-[13px] leading-6 app-muted">{{ item.desc }}</p>
            </article>
          </div>

          <!-- 数据条 -->
          <div
            class="reveal mt-6 flex flex-wrap items-center gap-x-8 gap-y-4 rounded-2xl border app-border app-panel px-6 py-5"
          >
            <span class="inline-flex items-center gap-2 text-[13px] app-muted">
              <el-icon class="app-accent"><Timer /></el-icon>
              首字节即输出，长回答无需等待
            </span>
            <span class="inline-flex items-center gap-2 text-[13px] app-muted">
              <el-icon class="app-accent"><DataAnalysis /></el-icon>
              分块与召回参数可在界面调整
            </span>
            <span class="inline-flex items-center gap-2 text-[13px] app-muted">
              <el-icon class="app-accent"><TrendCharts /></el-icon>
              会话与文档操作全程留痕
            </span>
          </div>
        </div>
      </section>

      <!-- ============================ 使用流程 ============================ -->
      <section id="workflow" class="scroll-mt-24 border-t app-border app-panel">
        <div class="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8">
          <div class="reveal max-w-2xl">
            <p class="font-mono text-xs tracking-[0.2em] app-accent">WORKFLOW</p>
            <h2 class="mt-3 text-[28px] font-semibold tracking-tight app-text sm:text-[34px]">
              四步完成一次可信问答
            </h2>
          </div>

          <ol class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <li
              v-for="(item, index) in workflow"
              :key="item.step"
              class="reveal relative rounded-2xl border app-border app-canvas p-6 tech-lift"
              :style="`transition-delay: ${index * 90}ms`"
            >
              <span class="font-mono text-[26px] font-semibold app-faint">{{ item.step }}</span>
              <span
                class="absolute right-5 top-6 grid h-9 w-9 place-items-center rounded-xl border app-border app-panel app-accent"
              >
                <el-icon class="app-accent"><component :is="item.icon" /></el-icon>
              </span>
              <h3 class="mt-4 text-[15px] font-semibold app-text">{{ item.title }}</h3>
              <p class="mt-2 text-[13px] leading-6 app-muted">{{ item.desc }}</p>
            </li>
          </ol>
        </div>
      </section>

      <!-- ============================ 技术架构 ============================ -->
      <section id="tech" class="scroll-mt-24 relative overflow-hidden border-t app-border">
        <div class="pointer-events-none absolute inset-0 tech-grid opacity-40" />
        <div class="relative mx-auto w-full max-w-6xl px-5 py-20 sm:px-8">
          <div class="reveal max-w-2xl">
            <p class="font-mono text-xs tracking-[0.2em] app-accent">ARCHITECTURE</p>
            <h2 class="mt-3 text-[28px] font-semibold tracking-tight app-text sm:text-[34px]">
              一条从文档到回答的可控链路
            </h2>
            <p class="mt-4 text-[15px] leading-8 app-muted">
              检索与生成解耦：检索层负责「找到什么」，生成层负责「怎么说」，两层都能单独观测和调参。
            </p>
          </div>

          <!-- 管道 -->
          <div class="reveal mt-12 overflow-x-auto scrollbar-thin">
            <div class="flex min-w-[720px] items-center gap-2">
              <template v-for="(node, index) in pipeline" :key="node">
                <span
                  class="whitespace-nowrap rounded-xl border app-border app-canvas px-3.5 py-2.5 font-mono text-[12px] app-text-secondary"
                >
                  {{ node }}
                </span>
                <span
                  v-if="index < pipeline.length - 1"
                  class="h-px w-6 shrink-0"
                  style="background: linear-gradient(90deg, var(--app-border-strong), var(--app-accent))"
                />
              </template>
            </div>
          </div>

          <div class="mt-10 grid gap-5 lg:grid-cols-3">
            <div
              v-for="(layer, index) in architecture"
              :key="layer.title"
              class="reveal rounded-2xl tech-glass p-6"
              :style="`transition-delay: ${index * 100}ms`"
            >
              <div class="flex items-center gap-2.5">
                <span class="grid h-9 w-9 place-items-center rounded-lg app-accent-soft">
                  <el-icon><component :is="layer.icon" /></el-icon>
                </span>
                <h3 class="text-[15px] font-semibold app-text">{{ layer.title }}</h3>
              </div>
              <ul class="mt-5 space-y-3">
                <li
                  v-for="entry in layer.items"
                  :key="entry"
                  class="flex items-start gap-2 text-[13px] leading-6 app-muted"
                >
                  <el-icon class="mt-1 shrink-0 text-[12px] app-accent"><CircleCheck /></el-icon>
                  {{ entry }}
                </li>
              </ul>
            </div>
          </div>

          <!-- 安全平面 -->
          <div
            class="reveal mt-6 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-2xl border app-border app-panel px-6 py-5"
          >
            <span class="inline-flex items-center gap-2 text-[13px] font-medium app-text">
              <el-icon class="app-accent"><Lock /></el-icon>
              安全与合规
            </span>
            <span
              v-for="item in guards"
              :key="item"
              class="inline-flex items-center gap-1.5 text-[12px] app-muted"
            >
              <span class="h-1 w-1 rounded-full bg-brand-light" />
              {{ item }}
            </span>
          </div>
        </div>
      </section>

      <!-- ============================ 适用场景 ============================ -->
      <section id="scenarios" class="scroll-mt-24 border-t app-border app-panel">
        <div class="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8">
          <div class="reveal max-w-2xl">
            <p class="font-mono text-xs tracking-[0.2em] app-accent">SCENARIOS</p>
            <h2 class="mt-3 text-[28px] font-semibold tracking-tight app-text sm:text-[34px]">
              已经沉淀了文档的团队，都能直接用
            </h2>
          </div>

          <div class="reveal mt-10 flex flex-wrap gap-2">
            <button
              v-for="item in scenarios"
              :key="item.key"
              class="inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-[13px] font-medium transition"
              :class="
                activeScenario === item.key
                  ? 'app-accent-soft border border-brand-light/40'
                  : 'tech-button'
              "
              @click="activeScenario = item.key"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              {{ item.label }}
            </button>
          </div>

          <div class="reveal mt-6 grid gap-6 rounded-3xl tech-glass p-6 sm:p-9 lg:grid-cols-[1.15fr_1fr]">
            <div>
              <h3 class="text-xl font-semibold tracking-tight app-text sm:text-2xl">
                {{ currentScenario.title }}
              </h3>
              <p class="mt-4 max-w-xl text-[14px] leading-7 app-muted">
                {{ currentScenario.desc }}
              </p>
              <ul class="mt-6 space-y-3">
                <li
                  v-for="point in currentScenario.points"
                  :key="point"
                  class="flex items-center gap-2.5 text-[13px] app-text-secondary"
                >
                  <span class="grid h-5 w-5 place-items-center rounded-full app-accent-soft">
                    <el-icon class="text-[11px]"><CircleCheck /></el-icon>
                  </span>
                  {{ point }}
                </li>
              </ul>
            </div>

            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
              <div
                v-for="card in [
                  { icon: Film, title: '多模态文件', desc: '图文混排的 PDF 也能解析出结构化文本' },
                  { icon: Coin, title: '成本可控', desc: '只把命中的片段送进模型，避免整篇投喂' },
                  { icon: User, title: '权限隔离', desc: '按账号划分知识库与文档可见范围' },
                ]"
                :key="card.title"
                class="flex items-start gap-3 rounded-2xl border app-border app-canvas p-4"
              >
                <el-icon class="mt-0.5 shrink-0 app-accent"><component :is="card.icon" /></el-icon>
                <div>
                  <p class="text-[13px] font-medium app-text">{{ card.title }}</p>
                  <p class="mt-1 text-[12px] leading-5 app-muted">{{ card.desc }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ============================ 常见问题 ============================ -->
      <section id="faq" class="scroll-mt-24 border-t app-border">
        <div class="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8">
          <div class="reveal max-w-2xl">
            <p class="font-mono text-xs tracking-[0.2em] app-accent">FAQ</p>
            <h2 class="mt-3 text-[28px] font-semibold tracking-tight app-text sm:text-[34px]">
              常见问题
            </h2>
          </div>

          <div class="reveal mt-10 max-w-3xl overflow-hidden rounded-2xl border app-border">
            <details
              v-for="(item, index) in faqs"
              :key="item.q"
              class="group border-b app-border last:border-b-0 app-canvas"
            >
              <summary
                class="flex cursor-pointer items-center gap-4 px-5 py-4 text-[14px] font-medium app-text transition app-hover sm:px-6"
              >
                <span class="font-mono text-[12px] app-faint">
                  {{ String(index + 1).padStart(2, '0') }}
                </span>
                <span class="flex-1">{{ item.q }}</span>
                <span
                  class="grid h-6 w-6 shrink-0 place-items-center rounded-md border app-border text-sm app-muted transition group-open:rotate-45"
                >
                  +
                </span>
              </summary>
              <p class="px-5 pb-5 pl-[3.1rem] text-[13px] leading-7 app-muted sm:px-6 sm:pl-[3.6rem]">
                {{ item.a }}
              </p>
            </details>
          </div>
        </div>
      </section>

      <!-- ============================ 收尾 CTA ============================ -->
      <section class="border-t app-border">
        <div class="mx-auto w-full max-w-6xl px-5 py-20 sm:px-8">
          <div
            class="reveal relative overflow-hidden rounded-3xl border app-border app-panel px-6 py-14 text-center sm:px-12"
          >
            <div class="pointer-events-none absolute inset-0 tech-grid opacity-50" />
            <div class="tech-glow left-1/2 top-0 h-64 w-64 -translate-x-1/2 animate-pulse-glow" />

            <div class="relative">
              <h2 class="mx-auto max-w-2xl text-balance text-[26px] font-semibold tracking-tight app-text sm:text-[32px]">
                现在就把团队的文档，变成能答问题的知识库
              </h2>
              <p class="mx-auto mt-4 max-w-xl text-[14px] leading-7 app-muted">
                登录后即可上传文档、发起提问，并逐条核对回答的引用出处。
              </p>
              <div class="mt-8 flex flex-wrap items-center justify-center gap-3">
                <RouterLink
                  v-if="!userStore.isAuthenticated"
                  :to="{ name: 'register' }"
                  class="tech-button-solid inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-medium"
                >
                  免费创建账号
                  <el-icon><ArrowRight /></el-icon>
                </RouterLink>
                <button
                  v-else
                  class="tech-button-solid inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-medium"
                  @click="goWorkspace"
                >
                  进入工作台
                  <el-icon><ArrowRight /></el-icon>
                </button>
                <RouterLink
                  v-if="!userStore.isAuthenticated"
                  :to="{ name: 'login' }"
                  class="tech-button inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-medium"
                >
                  已有账号，去登录
                </RouterLink>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>

    <SiteFooter />

    <!-- 首页也能直接打开服务协议 / 隐私政策（页脚按钮共用同一个单例状态） -->
    <PolicyDialog />
  </div>
</template>

<style scoped>
/* 引用片段左侧小竖条：hover 时向左滑动一点，作为科技感的微交互 */
.accent-bar {
  transition: transform 0.2s ease;
}

.group:hover .accent-bar {
  transform: translateX(-2px);
}

/* 折叠面板去掉浏览器默认三角标记 */
summary {
  list-style: none;
}

summary::-webkit-details-marker {
  display: none;
}

summary::marker {
  content: '';
}
</style>
