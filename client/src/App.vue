<script setup>
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1>传智杯 Web 项目</h1>
      <nav class="app-nav">
        <RouterLink to="/">首页</RouterLink>
        <RouterLink to="/about">关于</RouterLink>
      </nav>
    </header>

    <main class="app-main">
      <RouterView />
    </main>

    <footer class="app-footer">脚手架已就绪，开始写业务代码吧。</footer>
  </div>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.app-header h1 {
  font-size: 18px;
  margin: 0;
}

.app-nav {
  display: flex;
  gap: 16px;
}

.app-nav a {
  color: #374151;
  text-decoration: none;
}

.app-nav a.router-link-active {
  color: #2563eb;
  font-weight: 600;
}

.app-main {
  padding: 24px;
  min-height: 60vh;
}

.app-footer {
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
  color: #6b7280;
  font-size: 13px;
}
</style>
