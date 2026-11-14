<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Document, Download, Printer, Refresh, Right } from '@element-plus/icons-vue'

import { listDocuments } from '@/api/knowledge'
import { listComparisons } from '@/api/compare'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useReportsStore } from '@/stores/reports'
import { notifyError } from '@/utils/notify'
import { renderMarkdown } from '@/utils/markdown'

const MAX_PAPERS = 8

const reportsStore = useReportsStore()
const knowledgeStore = useKnowledgeStore()

const kind = ref('reading')
const baseId = ref('')
const documents = ref([])
const docsLoading = ref(false)
const selected = ref([])
const title = ref('')
const comparisonId = ref('')
const comparisons = ref([])

const KINDS = [
  { value: 'reading', label: '论文阅读报告', hint: '针对单篇论文', papers: 1 },
  { value: 'review', label: '文献综述初稿', hint: '2~8 篇，按主题成文', papers: 2 },
  { value: 'status', label: '研究现状整理', hint: '按主题/方法/阶段', papers: 2 },
  { value: 'comparison', label: '多论文对比报告', hint: '复用已有对比结果', papers: 0 },
]

const current = computed(() => reportsStore.current)
const running = computed(() => reportsStore.isRunning)
const ready = computed(() => current.value?.status === 'ready')
const html = computed(() => renderMarkdown(current.value?.contentMd || ''))
const needPapers = computed(() => kind.value !== 'comparison')

const stageText = {
  cards: '解析论文',
  generate: '撰写报告',
  done: '完成',
}

function kindLabel(value) {
  return KINDS.find((item) => item.value === value)?.label || value
}

async function loadDocuments() {
  if (!baseId.value) {
    documents.value = []
    return
  }
  docsLoading.value = true
  try {
    documents.value = await listDocuments(baseId.value)
  } catch (error) {
    notifyError(error, '加载文档失败')
  } finally {
    docsLoading.value = false
  }
}

function toggle(doc) {
  const index = selected.value.indexOf(doc.id)
  if (index >= 0) {
    selected.value.splice(index, 1)
    return
  }
  if (kind.value === 'reading') {
    selected.value = [doc.id]
    return
  }
  if (selected.value.length >= MAX_PAPERS) {
    ElMessage.warning(`最多选择 ${MAX_PAPERS} 篇`)
    return
  }
  selected.value.push(doc.id)
}

function isSelected(id) {
  return selected.value.includes(id)
}

async function generate() {
  const payload = { kind: kind.value, title: title.value.trim() }
  if (kind.value === 'comparison') {
    if (!comparisonId.value) {
      ElMessage.warning('请选择一条对比结果')
      return
    }
    payload.comparisonId = comparisonId.value
  } else {
    if (!selected.value.length) {
      ElMessage.warning('请选择论文')
      return
    }
    payload.documentIds = selected.value
  }
  try {
    await reportsStore.start(payload)
  } catch (error) {
    notifyError(error, '创建报告失败')
  }
}

async function openReport(item) {
  try {
    await reportsStore.open(item.id)
  } catch (error) {
    notifyError(error, '打开失败')
  }
}

async function rerun() {
  if (!current.value) return
  try {
    await reportsStore.rerun(current.value.id)
    ElMessage.success('已重新生成')
  } catch (error) {
    notifyError(error, '重跑失败')
  }
}

async function removeCurrent() {
  if (!current.value) return
  try {
    await ElMessageBox.confirm('删除这份材料？论文本身不受影响。', '删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await reportsStore.remove(current.value.id)
  ElMessage.success('已删除')
}

async function download(format) {
  if (!current.value) return
  try {
    await reportsStore.exportFile(current.value.id, format, current.value.title || '报告')
    ElMessage.success(format === 'docx' ? 'Word 已开始下载' : 'Markdown 已开始下载')
  } catch (error) {
    notifyError(error, '导出失败')
  }
}

async function printPdf() {
  if (!current.value) return
  try {
    await reportsStore.exportPdf(current.value.id)
    ElMessage.info('已打开打印视图：目标选「另存为 PDF」即可')
  } catch (error) {
    notifyError(error, '打开打印视图失败')
  }
}

/** 参考文献三种格式切换（数据在报告里，不额外请求） */
const refStyle = ref('gbt')
const refs = computed(() => (current.value?.references || {})[refStyle.value] || [])

watch(kind, (value) => {
  selected.value = []
  if (value === 'reading' && documents.value.length) {
    // 单篇类型不预选，交给用户点
  }
})

watch(baseId, loadDocuments)

onMounted(async () => {
  if (!knowledgeStore.bases.length) await knowledgeStore.loadBases()
  const first = knowledgeStore.bases[0]
  if (first) baseId.value = first.id
  await reportsStore.loadList()
  const latest = reportsStore.reports[0]
  if (latest) await openReport(latest)
  try {
    comparisons.value = await listComparisons()
  } catch {
    comparisons.value = []
  }
})

onUnmounted(() => {
  reportsStore.stopPolling()
})
</script>

<template>
  <div class="h-full overflow-y-auto scrollbar-thin">
    <div class="mx-auto w-full max-w-7xl px-4 py-6 md:px-6">
      <header class="mb-5 flex flex-wrap items-center gap-3">
        <div class="min-w-0 flex-1">
          <h1 class="text-xl font-semibold app-text">成果导出</h1>
          <p class="mt-1 text-sm app-muted">
            生成可直接编辑的学术材料：Markdown / Word 一键下载，PDF 用浏览器打印另存。
            参考文献由真实论文信息生成，不编造 DOI 与卷期。
          </p>
        </div>
        <template v-if="ready">
          <el-button :icon="Refresh" @click="rerun">重新生成</el-button>
          <el-button :icon="Delete" @click="removeCurrent">删除</el-button>
          <el-button :icon="Document" @click="download('md')">Markdown</el-button>
          <el-button :icon="Download" @click="download('docx')">Word</el-button>
          <el-button type="primary" :icon="Printer" @click="printPdf">PDF</el-button>
        </template>
      </header>

      <div class="grid gap-5 lg:grid-cols-[340px_1fr]">
        <aside class="space-y-4">
          <section class="rounded-xl border app-border app-panel p-4">
            <div class="mb-3 text-sm font-medium app-text">材料类型</div>
            <div class="space-y-1">
              <button
                v-for="item in KINDS"
                :key="item.value"
                class="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition app-hover"
                :class="kind === item.value ? 'app-active' : ''"
                @click="kind = item.value"
              >
                <span class="min-w-0 flex-1">
                  <span class="block text-xs font-medium app-text">{{ item.label }}</span>
                  <span class="block text-[11px] app-muted">{{ item.hint }}</span>
                </span>
                <el-icon v-if="kind === item.value" class="mt-0.5 shrink-0 app-accent"><Right /></el-icon>
              </button>
            </div>

            <!-- 对比报告：选已有对比 -->
            <template v-if="kind === 'comparison'">
              <el-select v-model="comparisonId" class="mt-3 w-full" placeholder="选择一条对比结果">
                <el-option
                  v-for="item in comparisons"
                  :key="item.id"
                  :label="`${item.topic || '未命名对比'}（${item.status}）`"
                  :value="item.id"
                  :disabled="item.status !== 'ready'"
                />
              </el-select>
              <p v-if="!comparisons.length" class="mt-2 text-[11px] app-muted">
                还没有对比结果，先去「论文对比」页做一次
              </p>
            </template>

            <!-- 论文选择 -->
            <template v-else>
              <el-select v-model="baseId" class="mt-3 w-full" placeholder="选择知识库">
                <el-option
                  v-for="base in knowledgeStore.bases"
                  :key="base.id"
                  :label="base.ownerType === 'team' ? `团队 · ${base.name}` : base.name"
                  :value="base.id"
                />
              </el-select>

              <div v-loading="docsLoading" class="mt-2 max-h-[240px] space-y-1 overflow-auto scrollbar-thin">
                <button
                  v-for="doc in documents"
                  :key="doc.id"
                  class="flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition app-hover"
                  :class="isSelected(doc.id) ? 'app-active' : ''"
                  @click="toggle(doc)"
                >
                  <el-icon class="mt-0.5 shrink-0 app-muted"><Document /></el-icon>
                  <span class="min-w-0 flex-1">
                    <span class="block truncate text-xs app-text">{{ doc.name }}</span>
                    <span class="block text-[11px] app-muted">{{ doc.chunks ?? 0 }} 段</span>
                  </span>
                  <el-icon v-if="isSelected(doc.id)" class="mt-0.5 shrink-0 app-accent"><Right /></el-icon>
                </button>
                <p v-if="!documents.length && !docsLoading" class="py-5 text-center text-xs app-muted">
                  该知识库还没有文档
                </p>
              </div>
            </template>

            <el-input
              v-if="kind === 'review' || kind === 'status'"
              v-model="title"
              class="mt-3"
              placeholder="报告主题（如「RAG 检索增强生成」）"
              maxlength="60"
              show-word-limit
            />

            <div v-if="needPapers" class="mt-3 flex items-center justify-between text-xs app-muted">
              <span>已选 {{ selected.length }} / {{ MAX_PAPERS }}</span>
              <el-button v-if="selected.length" link size="small" @click="selected = []">清空</el-button>
            </div>

            <el-button
              type="primary"
              class="mt-2 w-full"
              :loading="reportsStore.busy"
              @click="generate"
            >
              生成材料
            </el-button>
          </section>

          <section v-if="reportsStore.reports.length" class="rounded-xl border app-border app-panel p-3">
            <p class="mb-2 px-1 text-xs app-muted">历史材料</p>
            <button
              v-for="item in reportsStore.reports"
              :key="item.id"
              class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition app-hover"
              :class="current?.id === item.id ? 'app-active' : ''"
              @click="openReport(item)"
            >
              <span class="min-w-0 flex-1">
                <span class="block truncate text-xs app-text">{{ item.title || kindLabel(item.kind) }}</span>
                <span class="block text-[10px] app-muted">{{ kindLabel(item.kind) }}</span>
              </span>
              <el-tag v-if="item.status === 'ready'" size="small" type="success">就绪</el-tag>
              <el-tag v-else-if="item.status === 'failed'" size="small" type="danger">失败</el-tag>
              <el-tag v-else size="small" type="warning">生成中</el-tag>
            </button>
          </section>
        </aside>

        <main class="min-w-0">
          <section v-if="running" class="rounded-xl border app-border app-panel p-6">
            <p class="text-sm font-medium app-text">{{ stageText[current.stage] || '生成中' }}…</p>
            <el-progress class="mt-3" :percentage="current.progress || 0" :stroke-width="8" />
          </section>

          <section v-else-if="current?.status === 'failed'" class="rounded-xl border app-border app-panel p-6">
            <p class="text-sm font-medium text-red-500">生成失败</p>
            <p class="mt-2 whitespace-pre-wrap text-xs app-muted">{{ current.error || '未知原因' }}</p>
            <el-button class="mt-4" type="primary" :icon="Refresh" @click="rerun">重试</el-button>
          </section>

          <div v-else-if="ready" class="space-y-4">
            <section class="rounded-xl border app-border app-panel p-5">
              <div class="mb-3 flex flex-wrap items-center gap-2">
                <h2 class="text-sm font-semibold app-text">预览</h2>
                <el-tag size="small" type="info" effect="plain">{{ kindLabel(current.kind) }}</el-tag>
                <span class="text-[11px] app-muted">
                  共 {{ (current.contentMd || '').length }} 字 · 引用 {{ (current.sources || []).length }} 篇
                </span>
              </div>
              <div class="markdown-body text-sm" v-html="html" />
            </section>

            <section v-if="refs.length" class="rounded-xl border app-border app-panel p-5">
              <div class="mb-2 flex items-center justify-between">
                <h2 class="text-sm font-semibold app-text">参考文献（{{ refStyle.toUpperCase() }}）</h2>
                <el-radio-group v-model="refStyle" size="small">
                  <el-radio-button value="gbt">GB/T 7714</el-radio-button>
                  <el-radio-button value="apa">APA</el-radio-button>
                  <el-radio-button value="ieee">IEEE</el-radio-button>
                </el-radio-group>
              </div>
              <ol class="space-y-1 text-xs leading-6 app-text">
                <li v-for="(ref, index) in refs" :key="index">{{ ref }}</li>
              </ol>
              <p class="mt-2 text-[11px] app-muted">
                由论文解析结果生成，缺失字段留空；未提供 DOI 与卷期，不做推测。
              </p>
            </section>
          </div>

          <section v-else class="rounded-xl border app-border app-panel p-10 text-center">
            <p class="text-sm app-text">选择材料类型与论文，点「生成材料」</p>
            <p class="mt-2 text-xs app-muted">
              生成后可导出 Markdown / Word，或打开打印视图另存为 PDF。
            </p>
          </section>
        </main>
      </div>
    </div>
  </div>
</template>
