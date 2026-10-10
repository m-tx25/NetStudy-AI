<script setup>
import { RouterLink } from 'vue-router'

import AuthFooter from '@/components/auth/AuthFooter.vue'
import AuthPanel from '@/components/auth/AuthPanel.vue'
import PolicyDialog from '@/components/auth/PolicyDialog.vue'
import { APP_TITLE } from '@/config'

defineProps({
  /** 'login' | 'register' —— 决定右上角的互相跳转入口 */
  mode: { type: String, default: 'login' },
})
</script>

<template>
  <div class="flex min-h-screen flex-col bg-[#f5f7fa] dark:bg-[#141414]">
    <div class="flex min-h-0 flex-1">
      <!-- 左侧品牌区（lg 以上显示） -->
      <AuthPanel />

      <!-- 右侧表单区 -->
      <div class="flex flex-1 flex-col items-center justify-center px-5 py-8 sm:px-8 lg:py-12">
        <div class="w-full max-w-[420px]">
          <!-- 移动端品牌头 -->
          <div class="mb-5 flex items-center justify-between lg:hidden">
            <div class="flex items-center gap-2.5">
              <span
                class="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand to-emerald-600 text-sm font-bold text-white"
              >
                R
              </span>
              <span class="text-[15px] font-semibold text-[#0d0d0d] dark:text-[#ececec]">
                {{ APP_TITLE }}
              </span>
            </div>
            <RouterLink
              :to="mode === 'login' ? { name: 'register' } : { name: 'login' }"
              class="text-xs font-medium text-brand hover:underline"
            >
              {{ mode === 'login' ? '免费注册' : '返回登录' }}
            </RouterLink>
          </div>

          <!-- 桌面端右上角切换入口 -->
          <div class="mb-4 hidden items-center justify-end gap-2.5 text-xs text-[#8c8c8c] lg:flex">
            <span>{{ mode === 'login' ? '还没有账号？' : '已有账号？' }}</span>
            <RouterLink
              :to="mode === 'login' ? { name: 'register' } : { name: 'login' }"
              class="rounded-lg border border-black/[0.08] bg-white px-3 py-1.5 font-medium text-[#3d3d3d] transition hover:border-brand/50 hover:text-brand dark:border-white/10 dark:bg-white/5 dark:text-[#dcdcdc]"
            >
              {{ mode === 'login' ? '免费注册' : '去登录' }}
            </RouterLink>
          </div>

          <!-- 表单卡片 -->
          <div
            class="rounded-2xl border border-black/[0.06] bg-white p-7 shadow-[0_24px_70px_-34px_rgba(15,23,42,0.4)] sm:p-8 dark:border-white/10 dark:bg-[#1f1f1f]"
          >
            <slot />
          </div>

          <!-- 卡片下方附加内容 -->
          <div class="mt-4">
            <slot name="below" />
          </div>
        </div>
      </div>
    </div>

    <AuthFooter />
    <PolicyDialog />
  </div>
</template>
