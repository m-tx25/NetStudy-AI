<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  ArrowRight,
  ChatDotRound,
  CircleCheck,
  Coin,
  DataAnalysis,
  Document,
  DocumentChecked,
  Expand,
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
  { label: '适用场景', href: '#scenarios' },
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

/**
 * 能力卡点击：未登录先提示登录（带 redirect 回到对应功能），已登录直接进入该功能页。
 * 首页是公开页，卡片不能是「只展示不响应」的摆设，否则用户点半天不知道要登录。
 */
async function goFeature(item) {
  if (!item?.to) return
  if (userStore.isAuthenticated) {
    router.push(item.to)
    return
  }
  try {
    await ElMessageBox.confirm(
      `登录后即可使用「${item.title}」，未登录只能浏览产品介绍。`,
      '需要登录',
      {
        confirmButtonText: '去登录',
        cancelButtonText: '再看看',
        type: 'info',
        customClass: 'home-login-prompt',
      },
    )
    router.push({ name: 'login', query: { redirect: item.to } })
  } catch {
    // 用户选择「再看看」：什么都不做
  }
}

/* ------------------------------------------------------------------ *
 * 首屏关键数字
 * ------------------------------------------------------------------ */
const stats = [
  { value: '10+', label: '文档格式解析', desc: 'PDF / Word / 表格 / 网页' },
  { value: '2~6 篇', label: '同屏论文对比', desc: '维度矩阵 · 演进 · 空白' },
  { value: '3 种', label: '成果导出格式', desc: 'Markdown / Word / PDF' },
  { value: '100%', label: '结论可溯源', desc: '论文名 · 章节 · 页码' },
]

/* ------------------------------------------------------------------ *
 * 产品能力
 * ------------------------------------------------------------------ */
const features = [
  {
    icon: Search,
    title: '多源文献检索',
    desc: '按主题、作者或 DOI 在学术源中检索，命中的论文直接收进文献库，省去手工建库。',
    tag: '检索入库',
    to: '/app/search',
  },
  {
    icon: Files,
    title: '文献库与标签',
    desc: '论文、阅读笔记与标签统一管理，按课题分组；个人库与团队库分开存放。',
    tag: '统一管理',
    to: '/app/library',
  },
  {
    icon: DocumentChecked,
    title: '论文结构化解析',
    desc: '按章节切分并保留页码，图表、指标与结论都能定位回原文位置。',
    tag: '页码对齐',
    to: '/app/library',
  },
  {
    icon: DataAnalysis,
    title: '多篇论文对比',
    desc: '选 2~6 篇自动归纳对比维度，输出带页码的矩阵、演进时间轴与研究空白。',
    tag: '2~6 篇',
    to: '/app/compare',
  },
  {
    icon: TrendCharts,
    title: '研究助手',
    desc: '基于所选论文给出研究方向、可研究问题与技术路线，逐条标注「文献依据 / AI 假设」。',
    tag: '选题辅助',
    to: '/app/research',
  },
  {
    icon: Document,
    title: '成果导出',
    desc: '阅读报告、综述初稿、对比报告一键导出 Word / PDF，参考文献按 GB/T 7714 生成。',
    tag: '不编 DOI',
    to: '/app/reports',
  },
]

/* ------------------------------------------------------------------ *
 * 使用流程
 * ------------------------------------------------------------------ */
const workflow = [
  {
    step: '01',
    title: '检索或上传',
    desc: '从学术源检索论文，或直接上传 PDF，统一收进文献库。',
    icon: Search,
  },
  {
    step: '02',
    title: '解析并建索引',
    desc: '章节切分、页码对齐、指标抽取，再写入向量索引。',
    icon: Document,
  },
  {
    step: '03',
    title: '对比与追问',
    desc: '选 2~6 篇做横向对比，或限定论文范围提问，答案精确到页码。',
    icon: ChatDotRound,
  },
  {
    step: '04',
    title: '导出成果',
    desc: '把结论整理成阅读报告、综述初稿或对比报告，直接交付。',
    icon: CircleCheck,
  },
]

/* ------------------------------------------------------------------ *
 * 技术架构
 * ------------------------------------------------------------------ */
const pipeline = ['文献检索', '解析入库', '章节切分', '向量化', '检索召回', '引用生成']

const architecture = [
  {
    title: '数据接入层',
    icon: DataAnalysis,
    items: ['多源检索与去重', 'PDF 结构化解析', '章节与页码对齐', '文献库与标签'],
  },
  {
    title: '检索与分析层',
    icon: Position,
    items: ['BM25 与向量混合检索', '按篇配额召回', '重排与证据判定', '对比维度自动归纳'],
  },
  {
    title: '生成与成果层',
    icon: Reading,
    items: ['引用对齐到章节页码', '研究方向与假设标注', 'Word / PDF / Markdown 导出', 'GB/T 7714 参考文献'],
  },
]

const guards = ['权限分级', '团队隔离', '操作审计', '私有化部署']

/* ------------------------------------------------------------------ *
 * 适用场景
 * ------------------------------------------------------------------ */
const scenarios = [
  {
    key: 'research',
    label: '开题调研',
    icon: Search,
    title: '一个主题，先把领域摸清',
    desc: '按关键词与 DOI 聚合检索候选论文，收进文献库逐篇解析，再决定精读哪几篇。',
    points: ['多源检索与去重', '按课题建文献库', '章节级摘要'],
  },
  {
    key: 'review',
    label: '文献综述',
    icon: Reading,
    title: '把十篇论文压成一页对照表',
    desc: '选 2~6 篇做横向对比，自动归纳对比维度，输出带页码的矩阵与演进脉络。',
    points: ['对比维度自动归纳', '结论带原文页码', '研究空白提示'],
  },
  {
    key: 'writing',
    label: '论文写作',
    icon: Document,
    title: '从读到写，成果直接导出',
    desc: '阅读报告、综述初稿、研究现状整理，一键导出 Word 与 PDF，参考文献格式合规。',
    points: ['GB/T 7714 参考文献', '只从真实文献生成', 'Word / PDF 双格式'],
  },
  {
    key: 'team',
    label: '团队协作',
    icon: OfficeBuilding,
    title: '一个课题组共用一套文献底稿',
    desc: '团队文献库、角色权限与入队审批，成员看到的是同一份解析结果与结论。',
    points: ['团队文献库共享', '负责人 / 管理员 / 成员', '操作全程留痕'],
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
    q: '和直接把论文丢给 ChatGPT 有什么区别？',
    a: '直接贴论文受限于上下文长度，模型也容易「编」结论。本系统先在你选定的论文范围内检索最相关的章节，再让模型基于这些片段作答；引用会落到具体论文、章节与页码，没找到依据时会明确列出，而不是硬编。',
  },
  {
    q: '支持哪些文献来源和格式？',
    a: '可以从学术源按主题、作者或 DOI 检索并收进文献库，也可以直接上传 PDF、Word、Markdown 等文件；系统按格式选择解析器，切分章节、对齐页码后写入向量库。',
  },
  {
    q: '对比结论会不会是编的？',
    a: '对比矩阵要求每个单元格标注原文页码，抽取不到就显示「未提及」；卡片抽取失败的论文不会进入对比，并会把每篇的失败原因列出来，而不是笼统说「全部失败」。',
  },
  {
    q: '导出的参考文献能直接用吗？',
    a: '支持 GB/T 7714、APA、IEEE 三种格式，只从文献库里真实存在的论文生成，不补 DOI、不编作者；导出前可以先在成果页预览。',
  },
  {
    q: '团队怎么协作？',
    a: '团队分负责人 / 管理员 / 成员三种角色，文献库与知识库按团队共享；通过邀请码或搜索申请入队，由管理员审批，操作全程留痕。',
  },
  {
    q: '能不能私有化部署？',
    a: '可以。文件、向量库与数据库都部署在指定环境，生成模型走 OpenAI 兼容协议，可接本地 Ollama 或内网网关，文档不出内网。',
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
            M
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
          class="relative mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-10 px-5 py-16 sm:px-8 lg:min-h-[calc(100vh-4rem)] lg:grid-cols-[1.05fr_0.95fr] lg:gap-12 lg:py-14"
        >
          <!-- 左：文案 -->
          <div class="reveal min-w-0">
            <span
              class="inline-flex items-center gap-2 rounded-full border app-border px-3 py-1.5 text-[11px] app-muted tech-glass"
            >
              <span class="relative flex h-1.5 w-1.5">
                <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-light opacity-75" />
                <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand-light" />
              </span>
              学术文献 · RAG 研究平台
            </span>

            <h1 class="mt-6 text-balance text-[34px] font-semibold leading-[1.25] tracking-tight app-text sm:text-[44px] lg:text-[50px]">
              把海量论文<br />
              读成<span class="tech-gradient-text">一页可核对的结论</span>
            </h1>

            <p class="mt-6 max-w-xl text-[15px] leading-8 app-muted">
              从检索、解析到对比和成稿：每条结论都能回到论文的具体章节与页码，
              参考文献只从真实文献生成——这是把 AI 用于科研的底线。
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
                <span class="ml-3 font-mono text-[11px] app-faint">matrix-scholar / compare</span>
                <span class="ml-auto inline-flex items-center gap-1.5 text-[11px] app-muted">
                  <span class="h-1.5 w-1.5 rounded-full bg-brand-light" />
                  已连接文献库
                </span>
              </div>

              <div class="relative space-y-4 px-4 py-5 sm:px-5">
                <!-- 提问 -->
                <div class="flex justify-end">
                  <p
                    class="max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 text-[13px] leading-6 text-white"
                    style="background-image: linear-gradient(135deg, #25c39c, #0f9b7a)"
                  >
                    这两篇文献分别在讲什么？
                  </p>
                </div>

                <!-- 回答 -->
                <div class="flex gap-2.5">
                  <span
                    class="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-light to-brand text-[11px] font-bold text-white"
                  >
                    M
                  </span>
                  <div class="min-w-0 flex-1">
                    <div class="rounded-2xl rounded-tl-md border app-border app-panel px-4 py-3">
                      <p class="text-[13px] leading-6 app-text-secondary">
                        Gupta 等按时间线梳理 RAG 从朴素到模块化的演进，并归纳评测与挑战；
                        Corso 等从消息传递机制出发，讨论 GNN 的表达能力与过平滑问题。<span
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
                            A Comprehensive Survey of RAG · 第 3 页
                          </span>
                          <span class="shrink-0 font-mono text-[10px] app-accent">0.91</span>
                        </div>
                        <div
                          class="flex items-center gap-2 rounded-lg border app-border app-canvas px-2.5 py-2"
                        >
                          <span class="h-6 w-[3px] shrink-0 rounded-full" style="background: #38bdf8" />
                          <el-icon class="shrink-0 text-[13px]" style="color: #38bdf8"><Document /></el-icon>
                          <span class="min-w-0 flex-1 truncate font-mono text-[11px] app-muted">
                            Graph neural networks · 第 1 页
                          </span>
                          <span class="shrink-0 font-mono text-[10px] app-accent">0.86</span>
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
                    继续追问，例如「第二篇怎么处理过平滑？」
                  </span>
                  <span
                    class="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-light to-brand text-white"
                  >
                    <el-icon class="text-xs"><Position /></el-icon>
                  </span>
                </div>
                <div class="mt-2.5 flex items-center gap-2 text-[10px] app-faint">
                  <span class="rounded-md border app-border px-1.5 py-0.5">范围：2 篇论文</span>
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
              从检索到成稿，一条链路走完
            </h2>
            <p class="mt-4 text-[15px] leading-8 app-muted">
              检索、解析、对比、研究助手与成果导出共享同一份文献底稿——
              每一步都保留页码，随时可以回原文核对。
            </p>
          </div>

          <div class="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <article
              v-for="(item, index) in features"
              :key="item.title"
              class="reveal tech-lift group cursor-pointer rounded-2xl tech-glass p-6"
              :style="`transition-delay: ${(index % 3) * 90}ms`"
              role="button"
              tabindex="0"
              @click="goFeature(item)"
              @keydown.enter.prevent="goFeature(item)"
              @keydown.space.prevent="goFeature(item)"
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
              对比维度与召回参数可在界面调整
            </span>
            <span class="inline-flex items-center gap-2 text-[13px] app-muted">
              <el-icon class="app-accent"><TrendCharts /></el-icon>
              引用与操作全程留痕
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
              四步，从选题到成稿
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
              从开题到投稿，都能用上
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
                  { icon: DocumentChecked, title: '页码可追溯', desc: '结论、矩阵与引用都带原文页码，随时回查' },
                  { icon: Coin, title: '成本可控', desc: '只把命中的章节送进模型，避免整篇投喂' },
                  { icon: User, title: '团队隔离', desc: '按团队划分文献库与知识库的可见范围' },
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
                现在就把读过的论文，变成能追问的文献库
              </h2>
              <p class="mx-auto mt-4 max-w-xl text-[14px] leading-7 app-muted">
                登录后即可检索并入库文献、做论文对比，每条结论都能核对到原文页码。
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
