<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Collection,
  Document,
  Grid,
  Picture,
  Refresh,
  Tickets,
} from '@element-plus/icons-vue'

import { fetchPaperStructure, reindexPaper } from '@/api/papers'
import { reportReading } from '@/api/library'
import AnalysisPanel from '@/components/paper/AnalysisPanel.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const refreshing = ref(false)
const data = ref(null)
const error = ref('')
const scroller = ref(null)

// 自动阅读状态：打开即「阅读中」，滚动到接近底部记「已读」
let lastReported = -1
let finishReported = false

function reportScroll() {
  const element = scroller.value
  if (!element || !element.scrollHeight) return
  const percent = Math.min(
    100,
    Math.round(((element.scrollTop + element.clientHeight) / element.scrollHeight) * 100),
  )
  const atBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - 24

  if (atBottom && !finishReported) {
    finishReported = true
    reportReading({ documentId: route.params.id, progress: 100, finished: true }).catch(() => {})
    return
  }
  if (!finishReported && (lastReported < 0 || percent - lastReported >= 10)) {
    lastReported = percent
    reportReading({ documentId: route.params.id, progress: percent, finished: false }).catch(() => {})
  }
}

function markOpened() {
  if (finishReported) return
  lastReported = 0
  reportReading({ documentId: route.params.id, progress: 0, finished: false }).catch(() => {})
}

const sectionLabel = (section) => section.label || section.type
const qualityItems = computed(() => {
  const quality = data.value?.quality
  if (!quality) return []
  return [
    { icon: Document, label: '字符数', value: quality.charCount },
    { icon: Tickets, label: '页数', value: quality.pageCount },
    { icon: Collection, label: '章节', value: quality.sectionCount },
    { icon: Tickets, label: '参考文献', value: quality.referenceCount },
    { icon: Grid, label: '表格', value: quality.tableCount },
    { icon: Picture, label: '图注', value: quality.figureCount },
  ]
})

const tables = computed(() => (data.value?.assets || []).filter((item) => item.kind === 'table'))
const figures = computed(() => (data.value?.assets || []).filter((item) => item.kind === 'figure'))

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchPaperStructure(route.params.id)
  } catch (err) {
    error.value = err?.message || '加载解析结果失败'
  } finally {
    loading.value = false
  }
}

async function refresh() {
  refreshing.value = true
  try {
    await reindexPaper(route.params.id)
    ElMessage.success('已触发重新解析，几秒后自动刷新')
    setTimeout(load, 4000)
  } catch (err) {
    ElMessage.error(err?.message || '重新解析失败')
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  load()
  markOpened()
})
</script>

<template>
  <div
    ref="scroller"
    class="mx-auto h-full min-h-0 w-full max-w-5xl overflow-y-auto scrollbar-thin px-4 py-6 md:px-8"
    @scroll.passive="reportScroll"
  >
    <header class="mb-4 flex items-center justify-between gap-3">
      <button class="flex items-center gap-1.5 text-sm app-muted transition hover:app-text" @click="router.back()">
        <el-icon><ArrowLeft /></el-icon>
        返回
      </button>
      <el-button size="small" :icon="Refresh" :loading="refreshing" @click="refresh">重新解析</el-button>
    </header>

    <div v-if="loading" class="py-20 text-center text-sm app-muted">加载解析结果…</div>
    <div v-else-if="error" class="app-panel rounded-xl border border-red-500/30 p-6 text-sm text-red-500">
      {{ error }}
    </div>

    <template v-else-if="data">
      <section class="app-panel rounded-2xl border app-border p-5">
        <p class="text-xs app-muted">{{ data.name }} · {{ data.status }}</p>
        <h1 class="mt-1 text-xl font-semibold leading-8 app-text">
          {{ data.metadata.title || data.name }}
        </h1>
        <p v-if="data.metadata.authors?.length" class="mt-2 text-sm app-text-secondary">
          {{ data.metadata.authors.join('、') }}
        </p>
        <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs app-muted">
          <span v-if="data.metadata.venue">{{ data.metadata.venue }}</span>
          <span v-if="data.metadata.year">{{ data.metadata.year }}</span>
          <a
            v-if="data.metadata.doi"
            :href="`https://doi.org/${data.metadata.doi}`"
            target="_blank"
            class="text-brand"
          >
            DOI: {{ data.metadata.doi }}
          </a>
        </div>

        <div class="mt-4 grid grid-cols-3 gap-2 md:grid-cols-6">
          <div v-for="item in qualityItems" :key="item.label" class="rounded-lg border app-border px-3 py-2">
            <p class="text-[11px] app-muted">{{ item.label }}</p>
            <p class="mt-0.5 text-sm font-semibold app-text">{{ item.value ?? 0 }}</p>
          </div>
        </div>

        <div v-if="data.quality?.warnings?.length" class="mt-3 space-y-1">
          <p v-for="warning in data.quality.warnings" :key="warning" class="text-xs leading-5 text-amber-500">
            · {{ warning }}
          </p>
        </div>
      </section>

      <AnalysisPanel :document-id="data.documentId" :sections="data.sections" />

      <section class="mt-4">
        <h2 class="mb-2 text-sm font-semibold app-text">章节结构</h2>
        <el-collapse v-if="data.sections.length" class="paper-collapse">
          <el-collapse-item v-for="section in data.sections" :key="section.id" :name="section.id">
            <template #title>
              <span class="flex w-full items-center gap-2 pr-2 text-sm">
                <span
                  v-if="section.label && section.label !== section.heading"
                  class="rounded bg-brand/10 px-1.5 py-0.5 text-[11px] text-brand"
                >
                  {{ sectionLabel(section) }}
                </span>
                <span class="min-w-0 flex-1 truncate app-text">{{ section.heading }}</span>
                <span class="text-[11px] app-muted">
                  <template v-if="section.pageStart">p{{ section.pageStart }}<template v-if="section.pageEnd && section.pageEnd !== section.pageStart">-{{ section.pageEnd }}</template> · </template>
                  {{ section.charCount }} 字
                </span>
              </span>
            </template>
            <pre class="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-black/20 p-3 text-xs leading-6 text-slate-300">{{ section.text }}</pre>
          </el-collapse-item>
        </el-collapse>
        <p v-else class="app-panel rounded-xl border app-border p-4 text-xs app-muted">
          未识别到章节结构，已按全文处理。
        </p>
      </section>

      <section v-if="tables.length" class="mt-5">
        <h2 class="mb-2 text-sm font-semibold app-text">表格（{{ tables.length }}）</h2>
        <div class="space-y-3">
          <div v-for="table in tables" :key="table.id" class="app-panel overflow-x-auto rounded-xl border app-border p-3">
            <p class="mb-2 text-xs app-muted">
              <template v-if="table.page">第 {{ table.page }} 页 · </template>
              {{ table.caption || '未识别表题' }}
            </p>
            <table class="min-w-full text-left text-xs">
              <tbody>
                <tr v-for="(row, rowIndex) in table.rows.slice(0, 12)" :key="rowIndex" class="border-t app-border">
                  <td v-for="(cell, cellIndex) in row" :key="cellIndex" class="px-2 py-1.5 app-text-secondary">
                    {{ cell }}
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="table.rows.length > 12" class="mt-1 text-[11px] app-muted">仅展示前 12 行，共 {{ table.rows.length }} 行</p>
          </div>
        </div>
      </section>

      <section v-if="figures.length" class="mt-5">
        <h2 class="mb-2 text-sm font-semibold app-text">图注（{{ figures.length }}）</h2>
        <ul class="space-y-1.5">
          <li v-for="figure in figures" :key="figure.id" class="rounded-lg border app-border px-3 py-2 text-xs app-text-secondary">
            <span v-if="figure.page" class="mr-2 text-[11px] app-muted">p{{ figure.page }}</span>
            {{ figure.caption }}
          </li>
        </ul>
      </section>

      <section v-if="data.references.length" class="mt-5">
        <h2 class="mb-2 text-sm font-semibold app-text">参考文献（{{ data.references.length }}）</h2>
        <ol class="space-y-2">
          <li
            v-for="reference in data.references"
            :key="reference.id"
            class="rounded-lg border app-border px-3 py-2 text-xs leading-6 app-text-secondary"
          >
            {{ reference.rawText }}
            <a
              v-if="reference.doi"
              :href="`https://doi.org/${reference.doi}`"
              target="_blank"
              class="ml-2 text-brand"
            >
              DOI
            </a>
          </li>
        </ol>
      </section>
    </template>
  </div>
</template>

<style scoped>
.paper-collapse :deep(.el-collapse-item__header) {
  background: transparent;
  border-color: var(--app-border, rgba(148, 163, 184, 0.2));
  padding-left: 0.75rem;
  padding-right: 0.75rem;
}
.paper-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
  border-color: var(--app-border, rgba(148, 163, 184, 0.2));
}
</style>
