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
    class="flex h-14 shrink-0 items-center gap-2 border-b border-[#e5e5e5] bg-white px-3 md:px-5 dark:border-[#2f2f2f] dark:bg-[#212121]"
  >
    <button
      class="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-[#5d5d5d] transition hover:bg-black/5 md:hidden dark:text-[#b4b4b4] dark:hover:bg-white/10"
      title="打开侧边栏"
      @click="openMobileSidebar"
    >
      <el-icon><Expand /></el-icon>
    </button>

    <div class="min-w-0 flex-1">
      <h1 class="truncate text-sm font-semibold text-[#0d0d0d] dark:text-[#ececec]">
        {{ title }}
      </h1>
      <p class="truncate text-[11px] text-[#8e8e8e]">{{ subtitle }}</p>
    </div>

    <KnowledgeSelector />

    <button
      class="grid h-9 w-9 place-items-center rounded-lg text-[#5d5d5d] transition hover:bg-black/5 dark:text-[#b4b4b4] dark:hover:bg-white/10"
      :title="isDark ? '切换为浅色' : '切换为深色'"
      @click="toggleTheme"
    >
      <el-icon><Moon v-if="!isDark" /><Sunny v-else /></el-icon>
    </button>

    <button
      class="hidden h-9 items-center gap-1.5 rounded-lg border border-[#e5e5e5] px-3 text-xs font-medium text-[#0d0d0d] transition hover:bg-black/5 sm:flex dark:border-[#3a3a3a] dark:text-[#ececec] dark:hover:bg-white/10"
      @click="newChat"
    >
      <el-icon :size="14"><Plus /></el-icon>
      新建
    </button>
  </header>
</template>
