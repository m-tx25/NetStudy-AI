<script setup>
import { usePolicyDialog } from '@/composables/usePolicyDialog'
import { COMPANY_NAME, ICP_LICENSE, SUPPORT_EMAIL } from '@/config'

const { openPolicy } = usePolicyDialog()

const year = new Date().getFullYear()
</script>

<template>
  <footer
    class="shrink-0 border-t app-border px-5 py-3.5"
    style="background-color: color-mix(in srgb, var(--app-panel) 70%, transparent)"
  >
    <div
      class="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 text-[11px] app-muted sm:flex-row sm:text-xs"
    >
      <p>© {{ year }} {{ COMPANY_NAME }} · 保留所有权利</p>

      <nav class="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
        <button class="transition hover-app-accent" @click="openPolicy('terms')">服务协议</button>
        <span class="app-faint">·</span>
        <button class="transition hover-app-accent" @click="openPolicy('privacy')">隐私政策</button>
        <span class="app-faint">·</span>
        <a class="transition hover-app-accent" :href="`mailto:${SUPPORT_EMAIL}`">联系我们</a>
        <template v-if="ICP_LICENSE">
          <span class="app-faint">·</span>
          <a
            class="transition hover-app-accent"
            href="https://beian.miit.gov.cn/"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ ICP_LICENSE }}
          </a>
        </template>
      </nav>
    </div>
  </footer>
</template>
