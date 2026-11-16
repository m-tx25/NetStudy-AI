<script setup>
import { onErrorCaptured, onMounted, ref, watch } from 'vue'
import { RouterView } from 'vue-router'

import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useSidebar } from '@/composables/useSidebar'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const chatStore = useChatStore()
const { mobileSidebarOpen, closeMobileSidebar } = useSidebar()

/**
 * 子页面渲染出错时把错误挡在 <main> 里，显示可点的兜底面板，
 * 而不是让整个主区域变成一片黑。
 *
 * 线上真实事故：论文对比页的「研究方向演进」里有一条 2020 年的节点没有 documentId，
 * 模板无条件调 paperLabel(undefined) → TypeError → 主区域全黑，
 * 用户完全不知道发生了什么，只能来问「这里怎么黑了」。
 */
const pageError = ref(null)
onErrorCaptured((error) => {
  console.error('[layout] 页面渲染失败', error)
  pageError.value = error
  return false
})

function reloadPage() {
  pageError.value = null
  window.location.reload()
}

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
      <div
        v-if="pageError"
        class="flex h-full flex-col items-center justify-center gap-4 p-8 text-center"
      >
        <p class="text-sm font-medium app-text">这个页面渲染出错了</p>
        <p class="max-w-md break-words text-xs leading-6 app-muted">
          {{ String(pageError?.message || pageError).slice(0, 200) }}
        </p>
        <div class="flex gap-2">
          <el-button type="primary" @click="reloadPage">重新加载</el-button>
          <el-button @click="pageError = null">返回</el-button>
        </div>
      </div>
      <RouterView v-else />
    </main>
  </div>
</template>

<style>
.rag-sidebar-drawer .el-drawer__body {
  padding: 0;
  overflow: hidden;
}
</style>
