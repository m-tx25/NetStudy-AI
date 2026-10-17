<script setup>
import { RouterLink } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'

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
  <div class="flex min-h-screen flex-col app-bg">
    <!-- 顶部条：返回首页 + 登录/注册互切 -->
    <header
      class="relative z-20 flex h-16 shrink-0 items-center gap-3 border-b app-border px-5 sm:px-8"
    >
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

      <RouterLink
        :to="{ name: 'home' }"
        class="ml-4 hidden items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] app-muted transition app-hover hover-app-text sm:inline-flex"
      >
        <el-icon><ArrowLeft /></el-icon>
        返回首页
      </RouterLink>

      <div class="ml-auto flex items-center gap-2.5 text-xs app-muted">
        <span class="hidden sm:inline">{{ mode === 'login' ? '还没有账号？' : '已有账号？' }}</span>
        <RouterLink
          :to="mode === 'login' ? { name: 'register' } : { name: 'login' }"
          class="tech-button rounded-xl px-3.5 py-2 font-medium"
        >
          {{ mode === 'login' ? '免费注册' : '去登录' }}
        </RouterLink>
      </div>
    </header>

    <div class="flex min-h-0 flex-1">
      <!-- 左侧品牌区（lg 以上显示，占据剩余整块空间） -->
      <AuthPanel />

      <!-- 右侧表单区 -->
      <div class="flex flex-1 flex-col items-center justify-center px-5 py-10 sm:px-8 lg:py-14">
        <div class="w-full max-w-[420px]">
          <RouterLink
            :to="{ name: 'home' }"
            class="mb-5 inline-flex items-center gap-1.5 text-xs app-muted transition hover-app-accent lg:hidden"
          >
            <el-icon><ArrowLeft /></el-icon>
            返回首页
          </RouterLink>

          <!-- 表单卡片 -->
          <div class="rounded-2xl tech-glass p-7 shadow-2xl sm:p-8">
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
