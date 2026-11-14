<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  ArrowRight,
  Filter,
  Link,
  Loading,
  Refresh,
  Search,
} from '@element-plus/icons-vue'

import { fetchRelated, fetchSources, searchLiterature } from '@/api/literature'
import { addLibraryItem } from '@/api/library'
import PaperCard from '@/components/search/PaperCard.vue'

const form = reactive({
  q: '',
  author: '',
  doi: '',
  yearFrom: undefined,
  yearTo: undefined,
  venue: '',
  source: '',
  sort: 'relevance',
})

const advanced = ref(false)
const loading = ref(false)
const searched = ref(false)
const error = ref('')
const items = ref([])
const sourceStates = ref([])
const page = ref(1)
const pageSize = 10
const total = ref(0)
const sources = ref([])

const drawer = reactive({
  open: false,
  paper: null,
  related: [],
  loading: false,
})

const hasQuery = computed(
  () => Boolean(form.q.trim() || form.author.trim() || form.doi.trim()),
)

const activeSources = computed(() => sourceStates.value.filter((item) => item.ok))
const failedSources = computed(() => sourceStates.value.filter((item) => !item.ok))

onMounted(async () => {
  try {
    const data = await fetchSources({ silent: true })
    sources.value = data.sources || []
  } catch {
    sources.value = []
  }
})

async function runSearch(resetPage = true) {
  if (!hasQuery.value) {
    ElMessage.warning('请输入关键词、作者或 DOI')
    return
  }
  if (resetPage) page.value = 1
  loading.value = true
  error.value = ''
  try {
    const data = await searchLiterature(
      {
        q: form.q.trim(),
        author: form.author.trim(),
        doi: form.doi.trim(),
        yearFrom: form.yearFrom || undefined,
        yearTo: form.yearTo || undefined,
        venue: form.venue.trim(),
        source: form.source,
        sort: form.sort,
        page: page.value,
        pageSize,
      },
      { silent: true },
    )
    items.value = data.items || []
    sourceStates.value = data.sources || []
    total.value = data.total || 0
    searched.value = true
    if (!items.value.length) {
      const reason = failedSources.value.map((item) => `${item.label || item.name}：${item.error}`).join('；')
      ElMessage.warning(reason ? `没有检索到结果（${reason}）` : '没有检索到相关论文，换个关键词试试')
    }
  } catch (err) {
    error.value = err?.message || '检索失败'
    items.value = []
    sourceStates.value = []
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  form.author = ''
  form.doi = ''
  form.yearFrom = undefined
  form.yearTo = undefined
  form.venue = ''
  form.source = ''
  form.sort = 'relevance'
}

function prevPage() {
  if (page.value <= 1) return
  page.value -= 1
  runSearch(false)
}

function nextPage() {
  if (items.value.length < pageSize) return
  page.value += 1
  runSearch(false)
}

async function openPaper(paper) {
  drawer.open = true
  drawer.paper = paper
  drawer.related = []
  drawer.loading = true
  try {
    drawer.related = await fetchRelated(paper.source, paper.sourceId, 6, { silent: true })
  } catch {
    drawer.related = []
  } finally {
    drawer.loading = false
  }
}

const sourceName = (name) =>
  ({ openalex: 'OpenAlex', crossref: 'Crossref', arxiv: 'arXiv', semantic_scholar: 'Semantic Scholar' })[name] || name

async function collect(paper) {
  try {
    const item = await addLibraryItem(paper)
    ElMessage.success(item.duplicated ? '这篇论文已在文献库中' : '已加入文献库')
  } catch (err) {
    ElMessage.error(err?.message || '收藏失败')
  }
}
</script>

<template>
  <div class="mx-auto h-full min-h-0 w-full max-w-5xl overflow-y-auto scrollbar-thin px-4 py-6 md:px-8">
    <!-- 标题区 -->
    <header class="mb-5">
      <h1 class="text-xl font-semibold app-text">文献检索</h1>
      <p class="mt-1 text-sm app-muted">
        聚合 OpenAlex、Crossref、arXiv 等学术数据源，按关键词、作者或 DOI 查找论文。
      </p>
    </header>

    <!-- 检索栏 -->
    <section class="app-panel rounded-2xl border app-border p-4">
      <div class="flex flex-col gap-3 md:flex-row">
        <el-input
          v-model="form.q"
          size="large"
          placeholder="输入研究主题、关键词，例如：graph neural network"
          :prefix-icon="Search"
          clearable
          @keyup.enter="runSearch()"
        />
        <div class="flex gap-2">
          <el-button type="primary" size="large" :loading="loading" @click="runSearch()">
            检索
          </el-button>
          <el-button size="large" :icon="Filter" @click="advanced = !advanced">
            高级
          </el-button>
        </div>
      </div>

      <div v-if="advanced" class="mt-4 grid gap-3 border-t app-border pt-4 md:grid-cols-3">
        <label class="text-xs app-muted">
          作者
          <el-input v-model="form.author" size="default" placeholder="例如 Yann LeCun" clearable class="mt-1" />
        </label>
        <label class="text-xs app-muted">
          DOI
          <el-input v-model="form.doi" size="default" placeholder="10.1038/nature12373" clearable class="mt-1" />
        </label>
        <label class="text-xs app-muted">
          期刊 / 会议
          <el-input v-model="form.venue" size="default" placeholder="例如 Nature" clearable class="mt-1" />
        </label>
        <label class="text-xs app-muted">
          起始年份
          <el-input-number v-model="form.yearFrom" :min="1900" :max="2100" :controls="false" class="mt-1 w-full" />
        </label>
        <label class="text-xs app-muted">
          结束年份
          <el-input-number v-model="form.yearTo" :min="1900" :max="2100" :controls="false" class="mt-1 w-full" />
        </label>
        <label class="text-xs app-muted">
          数据源
          <el-select v-model="form.source" size="default" class="mt-1 w-full" placeholder="全部">
            <el-option label="全部数据源" value="" />
            <el-option v-for="item in sources" :key="item.name" :label="item.label" :value="item.name" />
          </el-select>
        </label>
        <label class="text-xs app-muted">
          排序
          <el-select v-model="form.sort" size="default" class="mt-1 w-full">
            <el-option label="相关度" value="relevance" />
            <el-option label="被引次数" value="cited" />
            <el-option label="最新发表" value="year" />
          </el-select>
        </label>
        <div class="flex items-end">
          <el-button :icon="Refresh" @click="resetFilters">重置筛选</el-button>
        </div>
      </div>
    </section>

    <!-- 数据源状态 -->
    <div v-if="searched && sourceStates.length" class="mt-3 flex flex-wrap items-center gap-2 text-xs">
      <span
        v-for="state in sourceStates"
        :key="state.name"
        class="inline-flex items-center gap-1.5 rounded-full border px-2 py-1"
        :class="
          state.ok
            ? 'border-emerald-500/30 text-emerald-500'
            : 'border-amber-500/30 text-amber-500'
        "
        :title="state.error || `耗时 ${state.latencyMs}ms`"
      >
        <i class="h-1.5 w-1.5 rounded-full" :class="state.ok ? 'bg-emerald-500' : 'bg-amber-500'" />
        {{ state.label || state.name }}
        <span v-if="state.ok" class="app-muted">{{ state.count }} 条 · {{ state.latencyMs }}ms</span>
        <span v-else class="app-muted">不可用</span>
      </span>
    </div>

    <!-- 结果 -->
    <section class="mt-4">
      <div v-if="loading" class="flex flex-col items-center justify-center gap-3 py-20 app-muted">
        <el-icon class="animate-spin" :size="22"><Loading /></el-icon>
        <span class="text-sm">正在并行检索各数据源…</span>
      </div>

      <div v-else-if="error" class="app-panel rounded-xl border border-red-500/30 p-6 text-sm text-red-500">
        {{ error }}
      </div>

      <div v-else-if="!searched" class="app-panel rounded-2xl border app-border px-6 py-16 text-center">
        <p class="text-sm font-medium app-text">从全球学术数据库开始检索</p>
        <p class="mx-auto mt-2 max-w-md text-xs leading-6 app-muted">
          试试「large language model」「single-cell RNA sequencing」，
          或直接粘贴一个 DOI。检索结果会标注来源与是否开放获取。
        </p>
      </div>

      <div v-else-if="!items.length" class="app-panel rounded-2xl border app-border px-6 py-16 text-center">
        <p class="text-sm app-text">没有找到匹配的论文</p>
        <p class="mt-2 text-xs app-muted">换个关键词，或放宽年份 / 数据源筛选。</p>
      </div>

      <div v-else class="space-y-3">
        <PaperCard v-for="paper in items" :key="paper.id" :paper="paper" @open="openPaper" @collect="collect" />
      </div>
    </section>

    <!-- 分页 -->
    <div v-if="searched && items.length" class="mt-5 flex items-center justify-center gap-3">
      <el-button size="small" :icon="ArrowLeft" :disabled="page <= 1 || loading" @click="prevPage">
        上一页
      </el-button>
      <span class="text-xs app-muted">第 {{ page }} 页</span>
      <el-button
        size="small"
        :disabled="items.length < pageSize || loading"
        @click="nextPage"
      >
        下一页
        <el-icon class="ml-1"><ArrowRight /></el-icon>
      </el-button>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawer.open" size="560px" :with-header="false" class="paper-drawer">
      <div v-if="drawer.paper" class="flex h-full flex-col">
        <div class="flex-1 overflow-y-auto scrollbar-thin p-6">
          <p class="text-xs app-muted">{{ sourceName(drawer.paper.source) }}</p>
          <h2 class="mt-2 text-lg font-semibold leading-7 app-text">
            {{ drawer.paper.title }}
          </h2>

          <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs app-muted">
            <span v-if="drawer.paper.venue">{{ drawer.paper.venue }}</span>
            <span v-if="drawer.paper.year">{{ drawer.paper.year }}</span>
            <span v-if="drawer.paper.citedBy">被引 {{ drawer.paper.citedBy }}</span>
            <span
              v-if="drawer.paper.openAccess?.isOa"
              class="rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-500"
            >
              开放获取
            </span>
          </div>

          <p class="mt-4 text-xs leading-6 app-text-secondary">
            {{ (drawer.paper.authors || []).map((a) => a.name).filter(Boolean).join('、') || '作者信息缺失' }}
          </p>

          <div class="mt-4 flex flex-wrap gap-2">
            <el-button type="primary" plain size="small" @click="collect(drawer.paper)">
              收藏到文献库
            </el-button>
            <el-button
              v-if="drawer.paper.openAccess?.pdfUrl"
              type="primary"
              size="small"
              tag="a"
              :href="drawer.paper.openAccess.pdfUrl"
              target="_blank"
            >
              打开原文 PDF
            </el-button>
            <el-button
              v-if="drawer.paper.doi"
              size="small"
              tag="a"
              :href="`https://doi.org/${drawer.paper.doi}`"
              target="_blank"
            >
              DOI 页面
            </el-button>
            <el-button
              v-if="drawer.paper.url"
              size="small"
              tag="a"
              :href="drawer.paper.url"
              target="_blank"
            >
              来源页面
            </el-button>
          </div>

          <h3 class="mt-6 text-sm font-semibold app-text">摘要</h3>
          <p class="mt-2 whitespace-pre-wrap text-[13px] leading-7 app-text-secondary">
            {{ drawer.paper.abstract || '该数据源未提供摘要。' }}
          </p>

          <template v-if="drawer.loading">
            <h3 class="mt-6 text-sm font-semibold app-text">相关论文</h3>
            <p class="mt-2 text-xs app-muted">加载中…</p>
          </template>
          <template v-else-if="drawer.related.length">
            <h3 class="mt-6 text-sm font-semibold app-text">相关论文</h3>
            <ul class="mt-2 space-y-2">
              <li v-for="item in drawer.related" :key="item.id">
                <button
                  class="w-full rounded-lg border app-border px-3 py-2 text-left text-xs leading-5 app-text transition hover:border-brand/40"
                  @click="openPaper(item)"
                >
                  {{ item.title }}
                  <span class="mt-1 block app-muted">
                    {{ item.venue || '—' }} <span v-if="item.year">· {{ item.year }}</span>
                  </span>
                </button>
              </li>
            </ul>
          </template>
        </div>

        <div class="border-t app-border p-4">
          <el-button class="w-full" @click="drawer.open = false">关闭</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>
