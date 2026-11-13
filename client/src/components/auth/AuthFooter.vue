<script setup>
import { usePolicyDialog } from '@/composables/usePolicyDialog'
import { COMPANY_NAME, ICP_LICENSE, SUPPORT_EMAIL } from '@/config'

const { openPolicy } = usePolicyDialog()

const year = new Date().getFullYear()
</script>

<template>
  <footer class="auth-footer">
    <p>© {{ year }} {{ COMPANY_NAME }} · 保留所有权利</p>

    <nav class="flex flex-wrap items-center gap-x-2.5 gap-y-1">
      <button class="transition" @click="openPolicy('terms')">服务协议</button>
      <span>·</span>
      <button class="transition" @click="openPolicy('privacy')">隐私政策</button>
      <span>·</span>
      <a class="transition" :href="`mailto:${SUPPORT_EMAIL}`">联系我们</a>
      <template v-if="ICP_LICENSE">
        <span>·</span>
        <a
          class="transition"
          href="https://beian.miit.gov.cn/"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ ICP_LICENSE }}
        </a>
      </template>
    </nav>
  </footer>
</template>
