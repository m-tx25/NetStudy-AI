<script setup>
import { onMounted, ref } from 'vue'

const status = ref('检查中…')
const detail = ref('')

onMounted(async () => {
  try {
    // 开发环境经 vite 代理转发到后端 http://localhost:3000
    const res = await fetch('/api/health')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    status.value = '后端连接正常'
    detail.value = JSON.stringify(data)
  } catch (err) {
    status.value = '后端未连接'
    detail.value = String(err.message || err)
  }
})
</script>

<template>
  <section>
    <h2>项目骨架已就绪</h2>
    <p>Vue 3 + Vite 前端 / Express 后端，前后端连通性：</p>
    <p><strong>{{ status }}</strong></p>
    <p v-if="detail" class="detail">{{ detail }}</p>
  </section>
</template>

<style scoped>
.detail {
  color: #6b7280;
  font-size: 13px;
  word-break: break-all;
}
</style>
