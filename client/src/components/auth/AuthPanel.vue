<script setup>
import AuthIllustration from '@/components/auth/AuthIllustration.vue'
import { isMockMode } from '@/config'

/** 四项能力：与首页「产品能力」保持一致，突出学术文献场景 */
const capabilities = [
  {
    title: '多源文献检索',
    desc: '按主题、作者或 DOI 检索，命中论文直接收进文献库',
  },
  {
    title: '多篇论文对比',
    desc: '2~6 篇自动归纳对比维度，结论带原文页码',
  },
  {
    title: '研究助手',
    desc: '基于所选论文给出研究方向与技术路线，标注文献依据与 AI 假设',
  },
  {
    title: '成果一键导出',
    desc: '阅读报告与综述初稿导出 Word / PDF，参考文献按 GB/T 7714',
  },
]

const trustItems = ['权限分级', '团队隔离', '操作审计', '私有化部署']
</script>

<template>
  <aside
    class="auth-panel relative hidden overflow-hidden lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-1/2"
  >
    <!-- S 形分界线：颜色跟左侧底色一致，形成参考图里的弧线过渡 -->
    <svg
      class="auth-curve pointer-events-none absolute inset-y-0 left-0 h-full w-[44%]"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path d="M0 0H36C28 12 24 22 28 32C34 44 50 48 50 58C50 69 30 71 32 82C34 92 40 96 40 100H0Z" />
    </svg>

    <div class="relative z-10 flex h-full w-full flex-col py-10 pl-[30%] pr-[5%] xl:pl-[34%]">
      <!-- 徽标 -->
      <div class="flex items-center justify-center gap-2">
        <span class="auth-badge">
          <span
            class="inline-block h-1.5 w-1.5 rounded-full"
            :style="{ backgroundColor: 'var(--auth-blue)' }"
          />
          学术文献 · RAG 研究平台
        </span>
        <span class="auth-badge auth-badge--strong">学术版</span>
      </div>

      <!-- 主标题 -->
      <h2 class="auth-promo-title">
        把海量论文，<br />
        读成一页<span class="auth-promo-mark">可核对的结论</span>
      </h2>

      <!-- 副标题（参考图里的强调行，数值用品牌深色） -->
      <p class="auth-promo-sub">
        <span class="auth-promo-line" />
        注册即免费体验 · <b class="auth-promo-num">4</b> 大核心能力
        <span class="auth-promo-line auth-promo-line--right" />
      </p>

      <!-- 能力点：两列「【能力】说明」 -->
      <ul class="mt-6 grid gap-x-5 gap-y-3 xl:grid-cols-2">
        <li v-for="item in capabilities" :key="item.title" class="auth-cap">
          <span class="auth-cap-dot" />
          <span>
            <b class="auth-cap-title">【{{ item.title }}】</b>{{ item.desc }}
          </span>
        </li>
      </ul>

      <!-- 插画 -->
      <div class="mt-5 flex min-h-0 flex-1 items-center justify-center">
        <AuthIllustration class="max-h-[320px] w-full" />
      </div>

      <!-- 说明 + 信任条 -->
      <p class="auth-promo-note">
        把文献交给大模型之前，先用检索锁定最相关的章节。答案有据可依、结论可核可查——这是把
        AI 用于科研的底线。
      </p>

      <div class="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5">
        <span v-for="item in trustItems" :key="item" class="auth-trust">
          <svg viewBox="0 0 16 16" class="h-3 w-3" aria-hidden="true">
            <circle cx="8" cy="8" r="7" fill="none" stroke="var(--auth-blue)" stroke-width="1.4" />
            <path
              d="M4.8 8.2l2.1 2.1 4.3-4.6"
              fill="none"
              stroke="var(--auth-blue)"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          {{ item }}
        </span>
      </div>

      <p v-if="isMockMode" class="mt-2 text-center text-[11px]" :style="{ color: 'var(--auth-faint)' }">
        当前为 Mock 演示模式，未连接真实后端
      </p>
    </div>
  </aside>
</template>
