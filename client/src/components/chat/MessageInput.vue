<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Promotion, VideoPause, Delete } from '@element-plus/icons-vue'

import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()

const draft = ref('')
const inputRef = ref(null)

const streaming = computed(() => chatStore.streaming)
const canSend = computed(() => draft.value.trim().length > 0 && !streaming.value)

const selectedBases = computed(() =>
  knowledgeStore.bases.filter((base) => chatStore.selectedKnowledgeBaseIds.includes(base.id)),
)

const placeholder = computed(() =>
  selectedBases.value.length
    ? `向「${selectedBases.value.map((b) => b.name).join('、')}」提问…`
    : '输入你的问题，可先在右上角选择知识库…',
)

function focus() {
  nextTick(() => inputRef.value?.focus?.())
}

function submit() {
  const text = draft.value.trim()
  if (!text || streaming.value) return
  draft.value = ''
  chatStore.sendMessage(text)
  focus()
}

function onKeydown(event) {
  if (event.key !== 'Enter') return
  // 中文输入法组词过程中不触发发送
  if (event.isComposing || event.keyCode === 229) return
  if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return
  event.preventDefault()
  submit()
}

function stop() {
  chatStore.stopStreaming()
}

function removeBase(id) {
  chatStore.toggleKnowledgeBase(id)
}

function goKnowledge() {
  router.push({ name: 'knowledge' })
}

// 会话切换后重新聚焦输入框
watch(
  () => route.params.id,
  () => focus(),
)
</script>

<template>
  <div class="shrink-0 border-t app-border app-canvas px-3 pb-3 pt-2 md:px-6">
    <div class="mx-auto w-full max-w-3xl">
      <!-- 已选知识库 -->
      <div v-if="selectedBases.length" class="mb-2 flex flex-wrap items-center gap-1.5">
        <span class="text-xs app-muted">检索范围：</span>
        <el-tag
          v-for="base in selectedBases"
          :key="base.id"
          size="small"
          closable
          type="success"
          effect="light"
          @close="removeBase(base.id)"
        >
          {{ base.name }}
        </el-tag>
        <button
          class="text-xs app-accent underline-offset-2 hover:underline"
          @click="goKnowledge"
        >
          管理
        </button>
      </div>
      <div v-else class="mb-2 flex items-center gap-2 text-xs app-muted">
        <span>未选择知识库，将基于全部已就绪文档回答</span>
        <button class="app-accent underline-offset-2 hover:underline" @click="goKnowledge">
          去上传文档
        </button>
      </div>

      <!-- 输入区 -->
      <div
        class="flex items-end gap-2 rounded-3xl border app-border app-elevated px-3 py-2 shadow-sm transition focus-within:border-brand-light/60 focus-within:shadow-lg"
      >
        <el-input
          ref="inputRef"
          v-model="draft"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 8 }"
          resize="none"
          :placeholder="placeholder"
          class="rag-chat-input min-w-0 flex-1"
          @keydown="onKeydown"
        />

        <button
          v-if="streaming"
          class="tech-button grid h-9 w-9 shrink-0 place-items-center rounded-full"
          title="停止生成"
          @click="stop"
        >
          <el-icon><VideoPause /></el-icon>
        </button>
        <button
          v-else
          class="grid h-9 w-9 shrink-0 place-items-center rounded-full transition disabled:cursor-not-allowed"
          :class="
            canSend
              ? 'bg-gradient-to-br from-brand-light to-brand text-white shadow-lg shadow-brand/25 hover:brightness-110'
              : 'app-active app-faint'
          "
          :disabled="!canSend"
          title="发送（Enter）"
          @click="submit"
        >
          <el-icon><Promotion /></el-icon>
        </button>
      </div>

      <div class="mt-2 flex items-center justify-between gap-3 px-1 text-[11px] app-faint">
        <span>
          Enter 发送 · Shift + Enter 换行
          <span v-if="chatStore.topK"> · Top-K {{ chatStore.topK }}</span>
        </span>
        <button
          v-if="draft"
          class="inline-flex items-center gap-1 hover:text-red-500"
          @click="draft = ''"
        >
          <el-icon :size="12"><Delete /></el-icon>
          清空
        </button>
        <span v-else>回答内容由知识库检索结果生成，请核对原始文档</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.rag-chat-input .el-textarea__inner) {
  border: none;
  box-shadow: none;
  padding: 6px 0;
  background: transparent;
  font-size: 15px;
  line-height: 1.6;
  color: inherit;
}

:deep(.rag-chat-input .el-textarea__inner:focus) {
  box-shadow: none;
}
</style>
