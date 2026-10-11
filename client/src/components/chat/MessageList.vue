<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowDown, Loading } from '@element-plus/icons-vue'

import MessageItem from '@/components/chat/MessageItem.vue'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'

const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()

const scroller = ref(null)
const atBottom = ref(true)

const messages = computed(() => chatStore.messages)

const lastAssistantId = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    if (messages.value[i].role === 'assistant') return messages.value[i].id
  }
  return null
})

/** 监听最后一条消息的长度变化，实现「流式输出时自动贴底」 */
const tailLength = computed(() => {
  const last = messages.value[messages.value.length - 1]
  return last ? `${last.id}:${(last.content || '').length}` : ''
})

const examples = computed(() => {
  const base = knowledgeStore.bases[0]?.name || '知识库'
  return [
    { icon: '📄', title: '总结文档要点', text: `请总结「${base}」中的核心内容` },
    { icon: '🔍', title: '精准检索', text: '系统支持哪些文档格式？上传后多久可以检索？' },
    { icon: '🧩', title: '对比分析', text: '对比不同文档中对同一问题的描述，指出差异' },
    { icon: '💻', title: '带代码示例', text: '给出调用流式问答接口的代码示例' },
  ]
})

function onScroll() {
  const el = scroller.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 120
}

function scrollToBottom(smooth = false) {
  const el = scroller.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

watch(tailLength, () => {
  if (!atBottom.value) return
  nextTick(() => scrollToBottom())
})

watch(
  () => messages.value.length,
  () => {
    atBottom.value = true
    nextTick(() => scrollToBottom())
  },
)

onMounted(() => {
  nextTick(() => scrollToBottom())
})

function ask(text) {
  chatStore.sendMessage(text)
}

function regenerate() {
  chatStore.regenerate()
}
</script>

<template>
  <div class="relative h-full min-h-0">
    <div ref="scroller" class="scrollbar-thin h-full overflow-y-auto" @scroll.passive="onScroll">
      <!-- 加载历史消息 -->
      <div
        v-if="chatStore.messagesLoading"
        class="flex h-full items-center justify-center gap-2 text-sm text-[#8e8e8e]"
      >
        <el-icon class="animate-spin"><Loading /></el-icon>
        正在加载对话记录…
      </div>

      <!-- 空态欢迎页 -->
      <div
        v-else-if="!messages.length"
        class="mx-auto flex min-h-full w-full max-w-3xl flex-col items-center justify-center px-4 py-10"
      >
        <div class="grid h-12 w-12 place-items-center rounded-2xl bg-brand text-xl font-bold text-white">
          R
        </div>
        <h1 class="mt-4 text-center text-xl font-semibold text-[#0d0d0d] md:text-2xl dark:text-[#ececec]">
          有什么可以帮你的？
        </h1>
        <p class="mt-2 text-center text-sm text-[#8e8e8e]">
          回答基于你上传的知识库文档检索生成
          <template v-if="chatStore.selectedKnowledgeBaseIds.length">
            · 当前检索 {{ chatStore.selectedKnowledgeBaseIds.length }} 个知识库
          </template>
          <template v-else> · 尚未选择知识库，将检索全部已就绪文档 </template>
        </p>

        <div class="mt-8 grid w-full gap-3 sm:grid-cols-2">
          <button
            v-for="example in examples"
            :key="example.title"
            class="group rounded-2xl border border-[#e5e5e5] bg-white p-4 text-left transition hover:border-brand/50 hover:shadow-md dark:border-[#3a3a3a] dark:bg-[#2a2a2a]"
            @click="ask(example.text)"
          >
            <p class="flex items-center gap-2 text-sm font-medium text-[#0d0d0d] dark:text-[#ececec]">
              <span>{{ example.icon }}</span>
              {{ example.title }}
            </p>
            <p class="mt-1 line-clamp-2 text-xs leading-5 text-[#8e8e8e]">
              {{ example.text }}
            </p>
          </button>
        </div>

        <p
          v-if="!knowledgeStore.bases.length"
          class="mt-8 rounded-xl bg-amber-50 px-4 py-3 text-center text-xs text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
        >
          还没有知识库。请先到「知识库管理」创建知识库并上传文档，问答效果会更好。
        </p>
      </div>

      <!-- 消息列表 -->
      <div v-else class="pb-6">
        <MessageItem
          v-for="message in messages"
          :key="message.id"
          :message="message"
          :streaming="chatStore.streaming"
          :is-last-assistant="message.id === lastAssistantId"
          @regenerate="regenerate"
        />
      </div>
    </div>

    <!-- 回到底部 -->
    <transition
      enter-active-class="transition duration-150"
      enter-from-class="opacity-0 translate-y-2"
      leave-active-class="transition duration-100"
      leave-to-class="opacity-0"
    >
      <button
        v-if="!atBottom"
        class="absolute bottom-4 left-1/2 grid h-9 w-9 -translate-x-1/2 place-items-center rounded-full border border-[#e5e5e5] bg-white text-[#5d5d5d] shadow-md transition hover:bg-[#f5f5f5] dark:border-[#3a3a3a] dark:bg-[#2f2f2f] dark:text-[#b4b4b4]"
        title="回到底部"
        @click="scrollToBottom(true)"
      >
        <el-icon><ArrowDown /></el-icon>
      </button>
    </transition>
  </div>
</template>
