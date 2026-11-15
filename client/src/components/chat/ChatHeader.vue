<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Expand, Moon, Plus, Sunny } from '@element-plus/icons-vue'

import KnowledgeSelector from '@/components/chat/KnowledgeSelector.vue'
import ModelSelector from '@/components/chat/ModelSelector.vue'
import { useChatStore } from '@/stores/chat'
import { useSidebar } from '@/composables/useSidebar'
import { useTheme } from '@/composables/useTheme'
import { formatRelativeTime } from '@/utils/format'

const route = useRoute()
const chatStore = useChatStore()
const { openMobileSidebar } = useSidebar()
const { isDark, toggleTheme } = useTheme()

const title = computed(() => chatStore.activeConversation?.title || '新的对话')

const subtitle = computed(() => {
  const conversation = chatStore.activeConversation
  if (!conversation) return '选择知识库后开始提问'
  const time = conversation.updatedAt ? formatRelativeTime(conversation.updatedAt) : ''
  const count = conversation.messageCount || chatStore.messages.length
  return [time, count ? `${count} 条消息` : ''].filter(Boolean).join(' · ')
})

function newChat() {
  chatStore.startNewConversation()
}
</script>

<template>
  <!--
    手机（<640px）：两行 —— 第一行 菜单 + 标题 + 主题，第二行 模型 / 知识库 选择器。
    桌面：一行，选择器靠右。
    之前所有元素挤在一行，390px 下标题被压成两行、选择器被截断。
  -->
  <header class="shrink-0 border-b app-border app-canvas">
    <div class="flex h-14 items-center gap-2 px-3 md:px-5">
      <button
        class="grid h-9 w-9 shrink-0 place-items-center rounded-lg app-muted transition app-hover hover-app-text md:hidden"
        title="打开侧边栏"
        @click="openMobileSidebar"
      >
        <el-icon><Expand /></el-icon>
      </button>

      <div class="min-w-0 flex-1">
        <h1 class="truncate text-sm font-semibold app-text">
          {{ title }}
        </h1>
        <p class="truncate text-[11px] app-muted">{{ subtitle }}</p>
      </div>

      <!-- 桌面：选择器在标题行右侧 -->
      <div class="hidden items-center gap-2 sm:flex">
        <ModelSelector />
        <KnowledgeSelector />
      </div>

      <button
        class="grid h-9 w-9 shrink-0 place-items-center rounded-lg app-muted transition app-hover hover-app-text"
        :title="isDark ? '切换为浅色' : '切换为深色'"
        @click="toggleTheme"
      >
        <el-icon><Moon v-if="!isDark" /><Sunny v-else /></el-icon>
      </button>

      <button
        class="tech-button hidden h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium sm:flex"
        @click="newChat"
      >
        <el-icon :size="14"><Plus /></el-icon>
        新建
      </button>
    </div>

    <!-- 手机：选择器单独一行，横向可滚动，避免挤压 -->
    <div class="flex items-center gap-2 overflow-x-auto px-3 pb-2 sm:hidden">
      <ModelSelector />
      <KnowledgeSelector />
    </div>
  </header>
</template>
