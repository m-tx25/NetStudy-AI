<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Expand, Moon, Plus, Sunny } from '@element-plus/icons-vue'

import KnowledgeSelector from '@/components/chat/KnowledgeSelector.vue'
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
  <header
    class="flex h-14 shrink-0 items-center gap-2 border-b app-border app-canvas px-3 md:px-5"
  >
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

    <KnowledgeSelector />

    <button
      class="grid h-9 w-9 place-items-center rounded-lg app-muted transition app-hover hover-app-text"
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
  </header>
</template>
