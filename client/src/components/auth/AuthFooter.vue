<script setup>
import { usePolicyDialog } from '@/composables/usePolicyDialog'
import { COMPANY_NAME, ICP_LICENSE, SUPPORT_EMAIL } from '@/config'

const { openPolicy } = usePolicyDialog()

const year = new Date().getFullYear()
</script>

<template>
  <footer
    class="shrink-0 border-t border-black/[0.06] bg-white/70 px-5 py-3.5 backdrop-blur dark:border-white/10 dark:bg-white/[0.03]"
  >
    <div
      class="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 text-[11px] text-[#8c8c8c] sm:flex-row sm:text-xs dark:text-[#8c8c8c]"
    >
      <p>© {{ year }} {{ COMPANY_NAME }} · 保留所有权利</p>

      <nav class="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
        <button class="transition hover:text-brand" @click="openPolicy('terms')">服务协议</button>
        <span class="text-black/10 dark:text-white/15">·</span>
        <button class="transition hover:text-brand" @click="openPolicy('privacy')">隐私政策</button>
        <span class="text-black/10 dark:text-white/15">·</span>
        <a class="transition hover:text-brand" :href="`mailto:${SUPPORT_EMAIL}`">联系我们</a>
        <template v-if="ICP_LICENSE">
          <span class="text-black/10 dark:text-white/15">·</span>
          <a
            class="transition hover:text-brand"
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
