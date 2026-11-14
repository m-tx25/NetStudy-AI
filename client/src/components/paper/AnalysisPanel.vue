<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Loading, Refresh, Search } from '@element-plus/icons-vue'

import { apiUrl, authHeaders } from '@/api/request'
import { fetchAnalyses, fetchAnalysisKinds } from '@/api/papers'
import { fetchEventStream } from '@/utils/sse'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({
  documentId: { type: String, required: true },
  sections: { type: Array, default: () => [] },
})

const kinds = ref([])
const generated = ref({})
const activeKind = ref('summary')
const content = ref('')
const evidence = ref([])
const citations = ref([])
const warning = ref('')
const streaming = ref(false)
const error = ref('')

const question = ref('')
const askSection = ref('')
const asking = ref(false)
const askContent = ref('')
const askCitations = ref([])
const askWarning = ref('')

let controller = null

const rendered = computed(() => renderMarkdown(content.value || ''))
const renderedAsk = computed(() => renderMarkdown(askContent.value || ''))
const activeLabel = computed(
  () => kinds.value.find((item) => item.kind === activeKind.value)?.label || '智能分析',
)

/**
 * 章节下拉的选项：按「章节类型」去重。
 * 同一类型会出现多个小节（例如十几个 other），逐个列出会满屏重复；
 * 而且问答接口是按类型过滤的，重复项本身也没有区分意义。
 */
const sectionOptions = computed(() => {
  const map = new Map()
  for (const section of props.sections || []) {
    if (!section.type || section.type === 'front' || map.has(section.type)) continue
    const label =
      section.label || (section.type === 'other' ? '其他小节' : section.heading || section.type)
    map.set(section.type, label)
  }
  return [...map.entries()].map(([value, label]) => ({ value, label }))
})

// 章节数据变化或历史选择失效（如选过 front）时，回退到「全部章节」
watch(sectionOptions, (options) => {
  if (askSection.value && !options.some((item) => item.value === askSection.value)) {
    askSection.value = ''
  }
})

onMounted(async () => {
  try {
    kinds.value = await fetchAnalysisKinds()
  } catch {
    kinds.value = []
  }
  try {
    const rows = await fetchAnalyses(props.documentId)
    generated.value = Object.fromEntries(rows.map((row) => [row.kind, row]))
  } catch {
    generated.value = {}
  }
  if (kinds.value.length) start(kinds.value[0].kind)
})

async function start(kind, force = false) {
  if (controller) controller.abort()
  controller = new AbortController()
  activeKind.value = kind
  content.value = ''
  evidence.value = []
  citations.value = []
  warning.value = ''
  error.value = ''
  streaming.value = true

  try {
    await fetchEventStream(apiUrl(`/papers/${props.documentId}/analysis/${kind}/stream`), {
      method: 'POST',
      headers: authHeaders(),
      body: { force },
      signal: controller.signal,
      onEvent: ({ data }) => {
        if (!data) return
        if (data.type === 'meta') {
          evidence.value = data.evidence || []
          if (data.cached) citations.value = data.citations || []
        } else if (data.type === 'delta') {
          content.value += data.content || ''
        } else if (data.type === 'done') {
          citations.value = data.citations || []
          warning.value = data.citationWarning || ''
          streaming.value = false
          generated.value = {
            ...generated.value,
            [kind]: { kind, contentMd: content.value, citations: citations.value },
          }
        } else if (data.type === 'error') {
          error.value = data.message || '生成失败'
          streaming.value = false
        }
      },
    })
  } catch (err) {
    if (err?.name !== 'AbortError') {
      error.value = err?.message || '生成失败'
    }
    streaming.value = false
  }
}

async function regenerate() {
  if (!activeKind.value) return
  await start(activeKind.value, true)
}

async function ask() {
  if (!question.value.trim()) {
    ElMessage.warning('请输入问题')
    return
  }
  if (controller) controller.abort()
  controller = new AbortController()
  asking.value = true
  askContent.value = ''
  askCitations.value = []
  askWarning.value = ''

  try {
    await fetchEventStream(apiUrl(`/papers/${props.documentId}/ask/stream`), {
      method: 'POST',
      headers: authHeaders(),
      body: { content: question.value.trim(), section: askSection.value || '' },
      signal: controller.signal,
      onEvent: ({ data }) => {
        if (!data) return
        if (data.type === 'delta') askContent.value += data.content || ''
        else if (data.type === 'done') {
          askCitations.value = data.citations || []
          askWarning.value = data.citationWarning || ''
          asking.value = false
        } else if (data.type === 'error') {
          ElMessage.error(data.message || '回答失败')
          asking.value = false
        }
      },
    })
  } catch (err) {
    if (err?.name !== 'AbortError') ElMessage.error(err?.message || '回答失败')
    asking.value = false
  }
}

function citationLabel(item) {
  const section = item.sectionHeading || item.sectionLabel || ''
  return `[${item.index}] p${item.page || '?'}${section ? ` · ${section}` : ''}`
}
</script>

<template>
  <section class="app-panel mt-4 rounded-2xl border app-border p-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-sm font-semibold app-text">智能分析</h2>
        <p class="mt-0.5 text-xs app-muted">只依据原文片段生成，结论带页码引用</p>
      </div>
      <el-button size="small" :icon="Refresh" :loading="streaming" @click="regenerate">重新生成</el-button>
    </div>

    <div class="mt-3 flex flex-wrap gap-1.5">
      <button
        v-for="item in kinds"
        :key="item.kind"
        class="rounded-lg border px-2.5 py-1.5 text-xs transition"
        :class="
          item.kind === activeKind
            ? 'border-brand bg-brand/10 text-brand'
            : 'app-border app-muted hover:app-text'
        "
        @click="start(item.kind)"
      >
        {{ item.label }}
        <span v-if="generated[item.kind]" class="ml-1 text-[10px] opacity-70">已有</span>
      </button>
    </div>

    <div v-if="error" class="mt-3 rounded-lg border border-red-500/30 p-3 text-xs text-red-500">
      {{ error }}
    </div>

    <div v-else class="mt-3">
      <p v-if="streaming && !content" class="flex items-center gap-2 text-xs app-muted">
        <el-icon class="animate-spin"><Loading /></el-icon>
        正在检索原文并生成「{{ activeLabel }}」…
      </p>

      <div
        v-if="content"
        class="markdown-body max-h-[420px] overflow-y-auto scrollbar-thin rounded-lg bg-black/10 p-3 text-[13px] leading-7"
        v-html="rendered"
      />

      <div v-if="citations.length" class="mt-2 flex flex-wrap gap-1.5">
        <span
          v-for="item in citations"
          :key="item.index"
          class="rounded-full bg-brand/10 px-2 py-0.5 text-[11px] text-brand"
          :title="item.snippet"
        >
          {{ citationLabel(item) }}
        </span>
      </div>

      <p v-if="warning" class="mt-2 text-[11px] text-amber-500">{{ warning }}</p>

      <details v-if="evidence.length" class="mt-2 text-xs app-muted">
        <summary class="cursor-pointer">查看检索到的原文片段（{{ evidence.length }}）</summary>
        <ul class="mt-1 space-y-1">
          <li v-for="item in evidence" :key="item.index" class="rounded border app-border px-2 py-1 leading-5">
            <span class="text-brand">[{{ item.index }}]</span>
            p{{ item.page || '?' }} · {{ item.sectionHeading || item.sectionLabel }}：{{ item.snippet.slice(0, 160) }}…
          </li>
        </ul>
      </details>
    </div>

    <!-- 章节问答：独立高亮区块 + 大号输入框，避免被上面的分析内容淹没 -->
    <div class="ask-panel mt-5 rounded-2xl border p-4">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <span class="grid h-7 w-7 place-items-center rounded-lg bg-brand/15 text-brand">
          <el-icon><ChatDotRound /></el-icon>
        </span>
        <span class="text-sm font-semibold app-text">章节问答</span>
        <span class="text-[11px] app-muted">只依据原文回答，结论带页码引用</span>
      </div>

      <div class="flex flex-col gap-2 md:flex-row md:items-stretch">
        <el-select
          v-model="askSection"
          size="large"
          class="ask-select w-full md:w-44"
          placeholder="全部章节"
        >
          <el-option label="全部章节" value="" />
          <el-option
            v-for="section in sectionOptions"
            :key="section.value"
            :label="section.label"
            :value="section.value"
          />
        </el-select>

        <el-input
          v-model="question"
          size="large"
          class="ask-input flex-1"
          placeholder="输入你的问题，例如：作者的创新点与基线相比如何？"
          clearable
          @keyup.enter="ask"
        >
          <template #prefix>
            <el-icon class="text-brand"><Search /></el-icon>
          </template>
        </el-input>

        <el-button
          type="primary"
          size="large"
          class="ask-btn shrink-0"
          :loading="asking"
          @click="ask"
        >
          <el-icon class="mr-1"><ChatDotRound /></el-icon>
          提问
        </el-button>
      </div>

      <div class="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] app-muted">
        <span>Enter 直接提问 · 回答会标注原文页码</span>
        <span v-if="asking" class="text-brand">正在检索原文并生成…</span>
      </div>

      <div
        v-if="askContent"
        class="markdown-body mt-3 max-h-72 overflow-y-auto scrollbar-thin rounded-lg bg-black/20 p-3 text-[13px] leading-7"
        v-html="renderedAsk"
      />
      <div v-if="askCitations.length" class="mt-2 flex flex-wrap gap-1.5">
        <span
          v-for="item in askCitations"
          :key="item.index"
          class="rounded-full bg-brand/10 px-2 py-0.5 text-[11px] text-brand"
          :title="item.snippet"
        >
          {{ citationLabel(item) }}
        </span>
      </div>
      <p v-if="askWarning" class="mt-1 text-[11px] text-amber-500">{{ askWarning }}</p>
    </div>
  </section>
</template>

<style scoped>
.ask-panel {
  border-color: rgba(45, 212, 191, 0.35);
  background:
    radial-gradient(120% 120% at 0% 0%, rgba(45, 212, 191, 0.12), transparent 55%),
    rgba(15, 23, 42, 0.35);
  box-shadow: 0 10px 30px rgba(2, 6, 23, 0.35);
}

.ask-input :deep(.el-input__wrapper) {
  min-height: 48px;
  border-radius: 12px;
  padding: 0 14px;
  background: rgba(2, 6, 23, 0.55);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.22) inset;
  transition: box-shadow 0.2s ease;
}

.ask-input :deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 2px rgba(45, 212, 191, 0.65),
    0 0 28px rgba(45, 212, 191, 0.15);
}

.ask-input :deep(.el-input__inner) {
  font-size: 14px;
}

.ask-select :deep(.el-select__wrapper) {
  min-height: 48px;
  border-radius: 12px;
}

.ask-btn {
  height: 48px;
  padding: 0 24px;
  border-radius: 12px;
  font-weight: 600;
}
</style>
