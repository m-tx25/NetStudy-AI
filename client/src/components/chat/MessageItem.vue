<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, Files, Refresh, WarningFilled } from '@element-plus/icons-vue'

import { renderMarkdown } from '@/utils/markdown'
import { copyText } from '@/utils/clipboard'
import { formatScore } from '@/utils/format'

const props = defineProps({
  message: { type: Object, required: true },
  isLastAssistant: { type: Boolean, default: false },
  streaming: { type: Boolean, default: false },
})

const emit = defineEmits(['regenerate'])

const expandedSourceId = ref('')

const isUser = computed(() => props.message.role === 'user')

const isStreamingThis = computed(() => props.streaming && props.message.status === 'streaming')

const html = computed(() => renderMarkdown(props.message.content || ''))

const sources = computed(() =>
  Array.isArray(props.message.sources)
    ? props.message.sources.map((source, index) => ({
        key: source.id || `${index}`,
        index: index + 1,
        documentName: source.documentName || source.document_name || source.fileName || '未知文档',
        knowledgeBaseName: source.knowledgeBaseName || source.knowledge_base_name || '',
        score: source.score ?? source.similarity,
        page: source.page,
        snippet: source.snippet || source.content || source.text || '',
      }))
    : [],
)

const expandedSource = computed(
  () => sources.value.find((source) => source.key === expandedSourceId.value) || null,
)

function toggleSource(key) {
  expandedSourceId.value = expandedSourceId.value === key ? '' : key
}

async function handleCopy(text) {
  const ok = await copyText(text || props.message.content || '')
  if (ok) ElMessage.success('已复制')
  else ElMessage.error('复制失败，请手动选择文本')
}

/** 代码块「复制」按钮通过事件委托处理，避免为每个块挂监听 */
async function handleContentClick(event) {
  const button = event.target?.closest?.('[data-copy-code]')
  if (!button) return
  const encoded = button.getAttribute('data-copy-code') || ''
  let code = encoded
  try {
    code = decodeURIComponent(encoded)
  } catch {
    /* 保留原样 */
  }
  const ok = await copyText(code)
  if (ok) {
    const original = button.textContent
    button.textContent = '已复制'
    setTimeout(() => {
      button.textContent = original || '复制'
    }, 1500)
  } else {
    ElMessage.error('复制失败')
  }
}
</script>

<template>
  <div
    class="group animate-fade-up px-3 py-4 md:px-6"
    :class="isUser ? 'bg-transparent' : 'app-panel'"
  >
    <div class="mx-auto flex w-full max-w-3xl gap-3 md:gap-4" :class="isUser ? 'flex-row-reverse' : ''">
      <!-- 头像 -->
      <div class="shrink-0 pt-0.5">
        <span
          v-if="isUser"
          class="grid h-7 w-7 place-items-center rounded-full border app-border app-elevated text-xs font-semibold app-text-secondary"
        >
          我
        </span>
        <span
          v-else
          class="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-brand-light to-brand text-xs font-bold text-white"
        >
          R
        </span>
      </div>

      <!-- 内容 -->
      <div class="min-w-0 flex-1" :class="isUser ? 'flex flex-col items-end' : ''">
        <template v-if="isUser">
          <div
            class="max-w-[85%] whitespace-pre-wrap break-words rounded-3xl border app-border app-elevated px-4 py-2.5 text-[15px] leading-relaxed app-text"
          >
            {{ message.content }}
          </div>
        </template>

        <template v-else>
          <!-- 等待首字：三个跳动圆点 -->
          <div v-if="isStreamingThis && !message.content" class="flex items-center gap-1 py-2">
            <span
              v-for="i in 3"
              :key="i"
              class="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-brand-light"
              :style="{ animationDelay: `${(i - 1) * 0.16}s` }"
            />
            <span class="ml-2 text-xs app-muted">正在检索知识库并生成回答…</span>
          </div>

          <div
            v-else
            class="markdown-body"
            :class="{ 'is-streaming': isStreamingThis }"
            @click="handleContentClick"
            v-html="html"
          />

          <!-- 出错提示 -->
          <div
            v-if="message.status === 'error'"
            class="mt-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
          >
            <el-icon class="mt-0.5 shrink-0"><WarningFilled /></el-icon>
            <div class="flex-1">
              <p>{{ message.error || '生成回答时出错' }}</p>
              <button
                v-if="isLastAssistant"
                class="mt-1 font-medium underline underline-offset-2"
                @click="emit('regenerate')"
              >
                重新生成
              </button>
            </div>
          </div>

          <p
            v-else-if="message.status === 'stopped'"
            class="mt-2 text-xs app-muted"
          >
            已停止生成
          </p>

          <!-- 引用来源 -->
          <div v-if="sources.length" class="mt-3">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="inline-flex items-center gap-1 text-xs app-muted">
                <el-icon :size="13"><Files /></el-icon>
                引用来源 {{ sources.length }} 条
              </span>
              <button
                v-for="source in sources"
                :key="source.key"
                class="max-w-[180px] truncate rounded-full border px-2 py-0.5 text-[11px] transition"
                :class="
                  expandedSourceId === source.key
                    ? 'app-accent-soft border-brand-light/50'
                    : 'app-border app-muted hover-app-accent hover:border-brand-light/50'
                "
                :title="source.documentName"
                @click="toggleSource(source.key)"
              >
                [{{ source.index }}] {{ source.documentName }}
              </button>
            </div>

            <transition
              enter-active-class="transition duration-150 ease-out"
              enter-from-class="opacity-0 -translate-y-1"
              leave-active-class="transition duration-100 ease-in"
              leave-to-class="opacity-0"
            >
              <div
                v-if="expandedSource"
                :key="expandedSource.key"
                class="mt-2 rounded-xl border app-border app-canvas p-3 text-xs"
              >
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <span class="font-medium app-text">
                    [{{ expandedSource.index }}] {{ expandedSource.documentName }}
                    <span v-if="expandedSource.page" class="font-normal app-muted">
                      · 第 {{ expandedSource.page }} 页
                    </span>
                  </span>
                  <span class="flex items-center gap-2 app-muted">
                    <span v-if="expandedSource.knowledgeBaseName">
                      {{ expandedSource.knowledgeBaseName }}
                    </span>
                    <span
                      v-if="expandedSource.score !== undefined && expandedSource.score !== null"
                    >
                      相关度 {{ formatScore(expandedSource.score) }}
                    </span>
                  </span>
                </div>
                <p class="mt-1.5 leading-5 app-text-secondary">
                  {{ expandedSource.snippet }}
                </p>
              </div>
            </transition>
          </div>

          <!-- 操作区 -->
          <div
            class="mt-2 flex items-center gap-1 app-muted opacity-100 transition md:opacity-0 md:group-hover:opacity-100"
          >
            <button
              class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs transition app-hover hover-app-text"
              @click="handleCopy(message.content)"
            >
              <el-icon :size="13"><CopyDocument /></el-icon>
              复制
            </button>
            <button
              v-if="isLastAssistant && !streaming"
              class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs transition app-hover hover-app-text"
              @click="emit('regenerate')"
            >
              <el-icon :size="13"><Refresh /></el-icon>
              重新生成
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
