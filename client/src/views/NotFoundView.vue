<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="relative flex h-screen flex-col items-center justify-center gap-4 overflow-hidden px-6 text-center app-bg">
    <div class="pointer-events-none absolute inset-0 tech-grid tech-grid-fade opacity-60" />
    <div class="tech-glow left-1/2 top-1/3 h-72 w-72 -translate-x-1/2 animate-pulse-glow" />

    <div class="relative">
      <p class="font-mono text-6xl font-bold tech-gradient-text">404</p>
      <h1 class="mt-4 text-lg font-semibold app-text">页面不存在</h1>
      <p class="mt-2 max-w-sm text-sm app-muted">
        你访问的地址没有对应的页面，可能是链接已失效或输入有误。
      </p>
      <div class="mt-6 flex flex-wrap items-center justify-center gap-2">
        <el-button @click="router.back()">返回上一页</el-button>
        <el-button type="primary" @click="router.replace({ name: 'home' })">回到首页</el-button>
      </div>
    </div>
  </div>
</template>
