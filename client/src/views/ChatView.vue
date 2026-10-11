<script setup>
import { onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

import ChatHeader from '@/components/chat/ChatHeader.vue'
import MessageInput from '@/components/chat/MessageInput.vue'
import MessageList from '@/components/chat/MessageList.vue'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'

const route = useRoute()
const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()

onMounted(() => {
  knowledgeStore.loadBases()
  chatStore.openConversation(route.params.id || null)
})

// /chat <-> /chat/:id 复用同一个组件，靠路由参数驱动会话切换
watch(
  () => route.params.id,
  (id) => {
    chatStore.openConversation(id || null)
  },
)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col app-canvas">
    <ChatHeader />
    <div class="min-h-0 flex-1">
      <MessageList />
    </div>
    <MessageInput />
  </div>
</template>
