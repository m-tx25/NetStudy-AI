<script setup>
import { RouterLink } from 'vue-router'

import { usePolicyDialog } from '@/composables/usePolicyDialog'
import { APP_TITLE, COMPANY_NAME, ICP_LICENSE, SUPPORT_EMAIL, isMockMode } from '@/config'

const { openPolicy } = usePolicyDialog()

const year = new Date().getFullYear()

const productLinks = [
  { label: '产品能力', to: '/#features' },
  { label: '使用流程', to: '/#workflow' },
  { label: '技术架构', to: '/#tech' },
  { label: '常见问题', to: '/#faq' },
]
</script>

<template>
  <footer class="relative border-t app-border app-bg">
    <div class="mx-auto w-full max-w-6xl px-5 py-12 sm:px-8">
      <div class="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr]">
        <!-- 品牌 -->
        <div>
          <div class="flex items-center gap-2.5">
            <span
              class="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-light to-brand text-sm font-bold text-white shadow-lg shadow-brand/25"
            >
              R
            </span>
            <span class="text-[15px] font-semibold app-text">{{ APP_TITLE }}</span>
          </div>
          <p class="mt-4 max-w-xs text-[13px] leading-6 app-muted">
            面向企业知识场景的检索增强问答系统：先把文档变成可检索的知识，再让大模型给出有出处的回答。
          </p>
          <p v-if="isMockMode" class="mt-4 inline-flex items-center gap-2 text-[11px] app-muted">
            <span class="h-1.5 w-1.5 rounded-full bg-amber-400" />
            当前为 Mock 演示模式，未连接真实后端
          </p>
        </div>

        <!-- 导航 -->
        <div>
          <p class="text-xs font-semibold tracking-wider app-text-secondary">产品</p>
          <ul class="mt-4 space-y-2.5">
            <li v-for="link in productLinks" :key="link.label">
              <RouterLink :to="link.to" class="text-[13px] app-muted transition hover-app-accent">
                {{ link.label }}
              </RouterLink>
            </li>
            <li>
              <RouterLink :to="{ name: 'login' }" class="text-[13px] app-muted transition hover-app-accent">
                登录 / 注册
              </RouterLink>
            </li>
          </ul>
        </div>

        <!-- 支持 -->
        <div>
          <p class="text-xs font-semibold tracking-wider app-text-secondary">支持</p>
          <ul class="mt-4 space-y-2.5">
            <li>
              <button class="text-[13px] app-muted transition hover-app-accent" @click="openPolicy('terms')">
                服务协议
              </button>
            </li>
            <li>
              <button class="text-[13px] app-muted transition hover-app-accent" @click="openPolicy('privacy')">
                隐私政策
              </button>
            </li>
            <li>
              <a
                class="text-[13px] app-muted transition hover-app-accent"
                :href="`mailto:${SUPPORT_EMAIL}`"
              >
                {{ SUPPORT_EMAIL }}
              </a>
            </li>
          </ul>
        </div>
      </div>

      <div class="tech-hairline mt-10 h-px w-full" />

      <div
        class="mt-6 flex flex-col items-center justify-between gap-3 text-[11px] app-faint sm:flex-row"
      >
        <p>© {{ year }} {{ COMPANY_NAME }} · 保留所有权利</p>
        <a
          v-if="ICP_LICENSE"
          class="transition hover-app-accent"
          href="https://beian.miit.gov.cn/"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ ICP_LICENSE }}
        </a>
      </div>
    </div>
  </footer>
</template>
