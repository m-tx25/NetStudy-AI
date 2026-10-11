<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="flex h-screen flex-col items-center justify-center gap-4 bg-white px-6 text-center dark:bg-[#212121]">
    <p class="text-6xl font-bold text-brand">404</p>
    <h1 class="text-lg font-semibold text-[#0d0d0d] dark:text-[#ececec]">页面不存在</h1>
    <p class="max-w-sm text-sm text-[#8e8e8e]">
      你访问的地址没有对应的页面，可能是链接已失效或输入有误。
    </p>
    <div class="mt-2 flex gap-2">
      <el-button @click="router.back()">返回上一页</el-button>
      <el-button type="primary" @click="router.replace({ name: 'chat-new' })">回到问答</el-button>
    </div>
  </div>
</template>
