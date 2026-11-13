<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'

import AuthFooter from '@/components/auth/AuthFooter.vue'
import AuthPanel from '@/components/auth/AuthPanel.vue'
import PolicyDialog from '@/components/auth/PolicyDialog.vue'
import { APP_TITLE } from '@/config'

const props = defineProps({
  /** 'login' | 'register' —— 决定标题下方的切换入口 */
  mode: { type: String, default: 'login' },
})

const isLogin = computed(() => props.mode !== 'register')
</script>

<template>
  <div class="auth-shell flex min-h-screen flex-col lg:flex-row">
    <!-- 左侧：品牌 + 表单（白底，参考图左边那一栏） -->
    <section
      class="relative flex min-h-screen flex-col px-6 py-7 sm:px-12 lg:w-1/2 lg:px-14 xl:px-20"
    >
      <header class="flex items-start justify-between gap-6">
        <RouterLink :to="{ name: 'home' }" class="flex items-center gap-3">
          <span class="auth-logo">R</span>
          <span class="leading-tight">
            <span
              class="block text-[15px] font-semibold tracking-tight"
              :style="{ color: 'var(--auth-title)' }"
            >
              {{ APP_TITLE }}
            </span>
            <span
              class="mt-1 block font-mono text-[10px] tracking-wide"
              :style="{ color: 'var(--auth-faint)' }"
            >
              Enterprise Knowledge Assistant
            </span>
          </span>
        </RouterLink>

        <RouterLink :to="{ name: 'home' }" class="auth-back shrink-0 pt-1">
          返回首页
          <el-icon :size="12"><ArrowRight /></el-icon>
        </RouterLink>
      </header>

      <div class="mx-auto flex w-full max-w-[430px] flex-1 flex-col justify-center py-10">
        <h1 class="auth-h1">
          欢迎来到
          <span class="auth-h1-brand">{{ APP_TITLE }}</span>
        </h1>

        <slot name="lead" />

        <div class="auth-tabs">
          <span class="auth-tab auth-tab--active">
            {{ isLogin ? '使用账号密码登录' : '创建账号' }}
          </span>
          <RouterLink
            :to="isLogin ? { name: 'register' } : { name: 'login' }"
            class="auth-tab auth-tab--link"
          >
            {{ isLogin ? '免费注册' : '去登录' }}
          </RouterLink>
        </div>

        <slot />

        <div v-if="$slots.below" class="mt-4">
          <slot name="below" />
        </div>
      </div>

      <AuthFooter />
    </section>

    <!-- 右侧：宣传面板（青绿渐变 + S 形分界 + 插画） -->
    <AuthPanel />
  </div>

  <PolicyDialog />
</template>
