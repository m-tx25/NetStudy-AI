<script setup>
import { onMounted, watch } from 'vue'
import { RouterView } from 'vue-router'

import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useSidebar } from '@/composables/useSidebar'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const chatStore = useChatStore()
const { mobileSidebarOpen, closeMobileSidebar } = useSidebar()

onMounted(() => {
  chatStore.loadConversations()
  // 刷新页面后若本地有 token 但已过期，这里会静默清理并跳登录
  if (userStore.isAuthenticated && !userStore.profile) userStore.loadProfile()
})

// 路由变化时自动收起移动端抽屉
watch(mobileSidebarOpen, (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
})
</script>

<template>
  <div class="flex h-screen w-full overflow-hidden app-canvas">
    <!-- 桌面端固定侧边栏 -->
    <aside
      class="hidden w-[264px] shrink-0 border-r app-border md:block"
    >
      <AppSidebar />
    </aside>

    <!-- 移动端抽屉 -->
    <el-drawer
      v-model="mobileSidebarOpen"
      direction="ltr"
      size="280px"
      :with-header="false"
      class="rag-sidebar-drawer"
    >
      <AppSidebar @navigate="closeMobileSidebar" />
    </el-drawer>

    <main class="flex min-w-0 flex-1 flex-col">
      <RouterView />
    </main>
  </div>
</template>

<style>
.rag-sidebar-drawer .el-drawer__body {
  padding: 0;
  overflow: hidden;
}
</style>
