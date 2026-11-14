<script setup>
import { computed } from 'vue'
import { Document, Link, Reading } from '@element-plus/icons-vue'

const props = defineProps({
  paper: { type: Object, required: true },
})

const emit = defineEmits(['open', 'collect'])

const authorsText = computed(() => {
  const list = props.paper.authors || []
  if (!list.length) return '作者信息缺失'
  const names = list.slice(0, 3).map((item) => item.name).filter(Boolean)
  const suffix = list.length > 3 ? ` 等 ${list.length} 人` : ''
  return names.join('、') + suffix
})

const abstractText = computed(() => {
  const text = (props.paper.abstract || '').trim()
  if (!text) return '暂无摘要（部分数据源仅提供元数据）'
  return text.length > 260 ? `${text.slice(0, 260)}…` : text
})

const doiUrl = computed(() =>
  props.paper.doi ? `https://doi.org/${props.paper.doi}` : '',
)

const sourceLabel = computed(() => {
  const map = {
    openalex: 'OpenAlex',
    crossref: 'Crossref',
    arxiv: 'arXiv',
    semantic_scholar: 'Semantic Scholar',
  }
  return map[props.paper.source] || props.paper.source
})
</script>

<template>
  <article
    class="app-card group rounded-xl border app-border p-4 transition hover:border-brand/40"
  >
    <div class="flex items-start gap-3">
      <span
        class="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand"
      >
        <el-icon><Document /></el-icon>
      </span>

      <div class="min-w-0 flex-1">
        <button
          class="block w-full text-left text-[15px] font-semibold leading-6 app-text transition hover:text-brand"
          :title="paper.title"
          @click="emit('open', paper)"
        >
          {{ paper.title || '（无标题）' }}
        </button>

        <p class="mt-1 truncate text-xs app-muted">{{ authorsText }}</p>

        <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs app-muted">
          <span v-if="paper.venue" class="truncate">{{ paper.venue }}</span>
          <span v-if="paper.year">{{ paper.year }}</span>
          <span v-if="paper.citedBy">被引 {{ paper.citedBy }}</span>
          <span
            v-if="paper.openAccess?.isOa"
            class="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[11px] font-medium text-emerald-500"
          >
            开放获取
          </span>
          <span class="rounded bg-white/5 px-1.5 py-0.5 text-[11px]">{{ sourceLabel }}</span>
        </div>

        <p class="mt-2 line-clamp-2 text-[13px] leading-6 app-text-secondary">
          {{ abstractText }}
        </p>

        <div class="mt-3 flex flex-wrap items-center gap-3 text-xs">
          <button class="font-medium text-brand transition hover:opacity-80" @click="emit('open', paper)">
            <el-icon class="mr-1 align-[-2px]"><Reading /></el-icon>
            查看详情
          </button>
          <button class="font-medium app-muted transition hover:text-brand" @click="emit('collect', paper)">
            + 收藏到文献库
          </button>
          <a
            v-if="doiUrl"
            :href="doiUrl"
            target="_blank"
            rel="noopener"
            class="app-muted transition hover:text-brand"
          >
            <el-icon class="mr-1 align-[-2px]"><Link /></el-icon>
            DOI
          </a>
          <a
            v-if="paper.openAccess?.pdfUrl"
            :href="paper.openAccess.pdfUrl"
            target="_blank"
            rel="noopener"
            class="app-muted transition hover:text-brand"
          >
            <el-icon class="mr-1 align-[-2px]"><Link /></el-icon>
            原文 PDF
          </a>
        </div>
      </div>
    </div>
  </article>
</template>
