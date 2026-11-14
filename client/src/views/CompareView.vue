<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  DataAnalysis,
  Delete,
  Download,
  Document,
  Refresh,
  Right,
} from '@element-plus/icons-vue'

import { getPaperProfile } from '@/api/compare'
import { listDocuments } from '@/api/knowledge'
import { useCompareStore } from '@/stores/compare'
import { useKnowledgeStore } from '@/stores/knowledge'
import { notifyError } from '@/utils/notify'

const MAX_PAPERS = 6

const compareStore = useCompareStore()
const knowledgeStore = useKnowledgeStore()

const baseId = ref('')
const documents = ref([])
const docsLoading = ref(false)
const selected = ref([])
const topic = ref('')
const paperMeta = ref({})

const current = computed(() => compareStore.current)
const running = computed(() => compareStore.isRunning)
const ready = computed(() => current.value?.status === 'ready')

const stageText = {
  cards: '解析论文',
  dimensions: '归纳对比维度',
  matrix: '生成对比矩阵',
  trends: '梳理演进与研究空白',
  verdict: '形成结论',
  done: '完成',
}

const gapKindText = {
  common_limitation: '共性局限',
  open_question: '开放问题',
  unexplored: '未被探索',
}

const confidenceText = {
  inferred: '推断',
  missing: '未提及',
}

/** 列名：优先用卡片里的标题（短），没有就退回文件名 */
function paperLabel(documentId) {
  const meta = paperMeta.value[documentId]
  if (meta?.title) return meta.title.split(':')[0].slice(0, 30)
  const doc = documents.value.find((item) => item.id === documentId)
  if (doc) return doc.name.replace(/\.pdf$/i, '').slice(0, 30)
  return documentId.slice(0, 10)
}

function paperYear(documentId) {
  return paperMeta.value[documentId]?.year || 0
}

async function ensurePaperMeta(ids) {
  const missing = (ids || []).filter((id) => id && !paperMeta.value[id])
  await Promise.all(
    missing.map(async (id) => {
      try {
        // silent：卡片是后台抽的，查询时可能还不存在，404 属于正常状态，
        // 不该弹「接口不存在」打扰用户（标题会有文件名兜底）。
        const profile = await getPaperProfile(id, { silent: true })
        paperMeta.value[id] = { title: profile.title, year: profile.year }
      } catch {
        // 卡片可能已被清理（换库/删文档），用文件名兜底即可，不打扰用户
        paperMeta.value[id] = { title: '', year: 0 }
      }
    }),
  )
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
  if (selected.value.length >= MAX_PAPERS) {
    ElMessage.warning(`一次最多对比 ${MAX_PAPERS} 篇（更多会拖慢速度也不划算）`)
    return
  }
  selected.value.push(doc.id)
}

function isSelected(id) {
  return selected.value.includes(id)
}

async function startCompare() {
  if (selected.value.length < 2) {
    ElMessage.warning('至少选择两篇论文')
    return
  }
  try {
    await compareStore.start(selected.value, topic.value.trim())
  } catch (error) {
    notifyError(error, '创建对比失败')
  }
}

async function openComparison(item) {
  try {
    const data = await compareStore.open(item.id)
    await ensurePaperMeta(data.documentIds)
  } catch (error) {
    notifyError(error, '打开对比失败')
  }
}

async function rerun() {
  if (!current.value) return
  try {
    await compareStore.rerun(current.value.id)
    ElMessage.success('已重新分析')
  } catch (error) {
    notifyError(error, '重跑失败')
  }
}

async function removeCurrent() {
  if (!current.value) return
  try {
    await ElMessageBox.confirm('删除这份对比结果？论文本身不会受影响。', '删除对比', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await compareStore.remove(current.value.id)
  ElMessage.success('已删除')
}

async function exportReport() {
  if (!current.value) return
  try {
    await compareStore.exportReport(current.value.id, current.value.topic || '论文对比报告')
    ElMessage.success('报告已开始下载')
  } catch (error) {
    notifyError(error, '导出失败')
  }
}

/** 论文列（按 documentIds 顺序），供矩阵表头使用 */
const papers = computed(() => current.value?.documentIds || [])

watch(
  () => [current.value?.id, current.value?.status],
  ([id, status]) => {
    // 卡片由后台任务抽取：pending/running 阶段还没有 profile 记录，
    // 这时去查必然是 404。等 ready 再补标题，省掉无意义的请求。
    if (id && status === 'ready') ensurePaperMeta(current.value?.documentIds)
  },
)

watch(baseId, loadDocuments)

onMounted(async () => {
  if (!knowledgeStore.bases.length) await knowledgeStore.loadBases()
  const first = knowledgeStore.bases[0]
  if (first) baseId.value = first.id
  await compareStore.loadList()
  const latest = compareStore.comparisons[0]
  if (latest) await openComparison(latest)
})

onUnmounted(() => {
  compareStore.stopPolling()
})
</script>

<template>
  <!--
    外层 AppLayout 是 `h-screen overflow-hidden`，页面自身必须提供滚动容器，
    否则内容会被裁掉、整个页面滚不动（对比结果很长，必须能滚）。
  -->
  <div class="h-full overflow-y-auto scrollbar-thin">
    <div class="mx-auto w-full max-w-7xl px-4 py-6 md:px-6">
    <header class="mb-5 flex flex-wrap items-center gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="text-xl font-semibold app-text">论文对比</h1>
        <p class="mt-1 text-sm app-muted">
          选两篇以上论文，自动归纳对比维度并逐维度横向比较 —— 结论、矩阵、演进与空白都带原文页码。
        </p>
      </div>
      <template v-if="ready">
        <el-button :icon="Refresh" @click="rerun">重新分析</el-button>
        <el-button :icon="Delete" @click="removeCurrent">删除</el-button>
        <el-button type="primary" :icon="Download" @click="exportReport">导出报告</el-button>
      </template>
    </header>

    <div class="grid gap-5 lg:grid-cols-[340px_1fr]">
      <!-- ============ 左：选择 ============ -->
      <aside class="space-y-4">
        <section class="rounded-xl border app-border app-panel p-4">
          <div class="mb-3 flex items-center gap-2">
            <el-icon class="text-base app-accent"><DataAnalysis /></el-icon>
            <span class="text-sm font-medium app-text">选择论文</span>
          </div>

          <el-select v-model="baseId" placeholder="选择知识库" class="w-full">
            <el-option
              v-for="base in knowledgeStore.bases"
              :key="base.id"
              :label="base.ownerType === 'team' ? `团队 · ${base.name}` : base.name"
              :value="base.id"
            />
          </el-select>

          <div v-loading="docsLoading" class="mt-3 max-h-[320px] space-y-1 overflow-auto scrollbar-thin">
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
                <span class="block text-[11px] app-muted">
                  {{ doc.chunks }} 段
                  <span v-if="doc.status === 'failed'" class="text-red-500">· 解析失败（仍可对比原文）</span>
                </span>
              </span>
              <el-icon v-if="isSelected(doc.id)" class="mt-0.5 shrink-0 app-accent">
                <Right />
              </el-icon>
            </button>

            <p v-if="!documents.length && !docsLoading" class="py-6 text-center text-xs app-muted">
              该知识库还没有文档，先去「知识库管理」上传论文 PDF
            </p>
          </div>

          <el-input
            v-model="topic"
            class="mt-3"
            placeholder="研究主题（可选，会作为报告标题）"
            maxlength="80"
            show-word-limit
          />

          <div class="mt-3 flex items-center justify-between text-xs app-muted">
            <span>已选 {{ selected.length }} / {{ MAX_PAPERS }}</span>
            <el-button v-if="selected.length" link size="small" @click="selected = []">清空</el-button>
          </div>

          <el-button
            type="primary"
            class="mt-2 w-full"
            :disabled="selected.length < 2"
            :loading="compareStore.busy"
            @click="startCompare"
          >
            开始对比
          </el-button>
        </section>

        <section v-if="compareStore.comparisons.length" class="rounded-xl border app-border app-panel p-3">
          <p class="mb-2 px-1 text-xs app-muted">历史对比</p>
          <button
            v-for="item in compareStore.comparisons"
            :key="item.id"
            class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition app-hover"
            :class="current?.id === item.id ? 'app-active' : ''"
            @click="openComparison(item)"
          >
            <span class="min-w-0 flex-1 truncate text-xs app-text">
              {{ item.topic || '未命名对比' }}
            </span>
            <el-tag v-if="item.status === 'ready'" size="small" type="success">就绪</el-tag>
            <el-tag v-else-if="item.status === 'failed'" size="small" type="danger">失败</el-tag>
            <el-tag v-else size="small" type="warning">分析中</el-tag>
          </button>
        </section>
      </aside>

      <!-- ============ 右：结果 ============ -->
      <main class="min-w-0">
        <!-- 进行中 -->
        <section v-if="running" class="rounded-xl border app-border app-panel p-6">
          <p class="text-sm font-medium app-text">
            {{ stageText[current.stage] || '分析中' }}…
          </p>
          <el-progress class="mt-3" :percentage="current.progress || 0" :stroke-width="8" />
          <p class="mt-3 text-xs app-muted">
            正在逐篇解析论文并做跨篇对齐，通常需要 1~3 分钟（首次要抽卡片，之后命中缓存会快很多）。
          </p>
        </section>

        <!-- 失败 -->
        <section v-else-if="current?.status === 'failed'" class="rounded-xl border app-border app-panel p-6">
          <p class="text-sm font-medium text-red-500">对比失败</p>
          <p class="mt-2 whitespace-pre-wrap text-xs app-muted">{{ current.error || '未知原因' }}</p>
          <el-button class="mt-4" type="primary" :icon="Refresh" @click="rerun">重试</el-button>
        </section>

        <!-- 结果 -->
        <div v-else-if="ready" class="space-y-4">
          <section class="rounded-xl border app-border app-panel p-5">
            <h2 class="text-sm font-semibold app-text">总体结论</h2>
            <p class="mt-2 whitespace-pre-wrap text-sm leading-7 app-text">
              {{ current.verdict || '（模型未给出结论）' }}
            </p>
          </section>

          <section
            v-if="current.scenarios?.length"
            class="rounded-xl border app-border app-panel p-5"
          >
            <h2 class="text-sm font-semibold app-text">场景适配建议</h2>
            <div class="mt-3 overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead>
                  <tr class="app-muted">
                    <th class="pb-2 pr-3 font-medium">场景</th>
                    <th class="pb-2 pr-3 font-medium">更合适</th>
                    <th class="pb-2 font-medium">理由</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(item, index) in current.scenarios"
                    :key="index"
                    class="border-t app-border"
                  >
                    <td class="py-2 pr-3 app-text">{{ item.scenario }}</td>
                    <td class="py-2 pr-3">
                      <span class="app-accent">{{ item.betterLabel || item.better }}</span>
                    </td>
                    <td class="py-2 app-muted">{{ item.reason }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section v-if="current.matrix?.length" class="rounded-xl border app-border app-panel p-5">
            <h2 class="text-sm font-semibold app-text">对比矩阵</h2>
            <p class="mt-1 text-xs app-muted">
              每一行把全部论文放在一起比较；<span class="app-accent">(p.N)</span> 是原文页码，
              「推断」表示由原文推断、「未提及」表示该论文没涉及。
            </p>
            <div class="mt-3 overflow-x-auto scrollbar-thin">
              <table class="w-full text-left text-xs">
                <thead>
                  <tr class="app-muted">
                    <th
                      class="sticky left-0 z-10 w-24 bg-[var(--app-panel)] pb-2 pr-3 font-medium"
                    >
                      维度
                    </th>
                    <th
                      v-for="paper in papers"
                      :key="paper"
                      class="min-w-[180px] pb-2 pr-3 font-medium"
                    >
                      {{ paperLabel(paper) }}
                      <span v-if="paperYear(paper)" class="app-muted">({{ paperYear(paper) }})</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in current.matrix"
                    :key="row.dimension"
                    class="border-t app-border align-top"
                  >
                    <td
                      class="sticky left-0 z-10 bg-[var(--app-panel)] py-2 pr-3 font-medium app-text"
                    >
                      {{ row.dimension }}
                    </td>
                    <td
                      v-for="paper in papers"
                      :key="paper"
                      class="py-2 pr-3"
                      :class="row.cells.find((c) => c.documentId === paper)?.confidence === 'missing' ? 'app-muted' : 'app-text'"
                    >
                      <template
                        v-for="cell in [
                          row.cells.find((c) => c.documentId === paper) || {
                            value: '',
                            confidence: 'missing',
                          },
                        ]"
                        :key="cell.documentId"
                      >
                        <span>{{ cell.value || '未提及' }}</span>
                        <span v-if="cell.page" class="ml-1 text-[11px] app-accent">
                          (p.{{ cell.page }})
                        </span>
                        <el-tag
                          v-if="confidenceText[cell.confidence]"
                          size="small"
                          :type="cell.confidence === 'missing' ? 'info' : 'warning'"
                          effect="plain"
                          class="ml-1"
                        >
                          {{ confidenceText[cell.confidence] }}
                        </el-tag>
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section
            v-if="(current.trends?.timeline || []).length"
            class="rounded-xl border app-border app-panel p-5"
          >
            <h2 class="text-sm font-semibold app-text">研究方向演进</h2>
            <div class="mt-3 space-y-2">
              <div
                v-for="(item, index) in current.trends.timeline"
                :key="index"
                class="flex items-start gap-3"
              >
                <span class="mt-0.5 shrink-0 rounded-md bg-brand/15 px-2 py-0.5 text-[11px] font-semibold app-accent">
                  {{ item.year || '—' }}
                </span>
                <p class="min-w-0 flex-1 text-xs leading-6 app-text">
                  <span class="font-medium">{{ paperLabel(item.documentId) }}</span>
                  ：{{ item.label }}（{{ item.method }}）
                </p>
              </div>
            </div>
            <ul v-if="(current.trends?.trends || []).length" class="mt-3 space-y-2 border-t app-border pt-3">
              <li
                v-for="(item, index) in current.trends.trends"
                :key="index"
                class="text-xs leading-6 app-text"
              >
                <span class="app-accent">{{ item.period }}</span>：{{ item.summary }}
              </li>
            </ul>
          </section>

          <section v-if="current.gaps?.length" class="rounded-xl border app-border app-panel p-5">
            <h2 class="text-sm font-semibold app-text">研究空白</h2>
            <div class="mt-3 space-y-2">
              <div
                v-for="(gap, index) in current.gaps"
                :key="index"
                class="rounded-lg border app-border px-3 py-2"
              >
                <div class="flex items-start gap-2">
                  <span class="text-xs app-muted">{{ index + 1 }}.</span>
                  <p class="min-w-0 flex-1 text-xs leading-6 app-text">{{ gap.gap }}</p>
                  <el-tag size="small" type="info" effect="plain" class="shrink-0">
                    {{ gapKindText[gap.kind] || gap.kind }}
                  </el-tag>
                </div>
                <p v-if="gap.why" class="mt-1 pl-4 text-[11px] app-muted">{{ gap.why }}</p>
              </div>
            </div>
          </section>
        </div>

        <!-- 空态 -->
        <section v-else class="rounded-xl border app-border app-panel p-10 text-center">
          <p class="text-sm app-text">从左侧选择两篇以上论文，点「开始对比」</p>
          <p class="mt-2 text-xs app-muted">
            系统会先逐篇抽取结构化信息，再做跨篇对齐 —— 给出维度矩阵、演进脉络与研究空白。
          </p>
        </section>
      </main>
      </div>
    </div>
  </div>
</template>
