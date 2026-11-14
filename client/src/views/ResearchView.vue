<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Download, Document, Refresh, Right, Star } from '@element-plus/icons-vue'

import { listDocuments } from '@/api/knowledge'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useResearchStore } from '@/stores/research'
import { notifyError } from '@/utils/notify'

const MAX_PAPERS = 8

const researchStore = useResearchStore()
const knowledgeStore = useKnowledgeStore()

const baseId = ref('')
const documents = ref([])
const docsLoading = ref(false)
const selected = ref([])
const goal = ref('')

const current = computed(() => researchStore.current)
const running = computed(() => researchStore.isRunning)
const ready = computed(() => current.value?.status === 'ready')

const stageText = {
  cards: '解析论文',
  directions: '推荐研究方向',
  questions: '发现研究问题',
  roadmap: '生成技术路线与计划',
  novelty: '分析创新空间',
  related: '梳理相关工作',
  done: '完成',
}

/** 证据类型标签：这是模块七的核心要求 —— 必须区分文献结论与 AI 推测 */
const kindMeta = {
  evidence: { label: '文献依据', type: 'success' },
  hypothesis: { label: 'AI 假设', type: 'warning' },
  suggestion: { label: '建议', type: 'info' },
}

function kindOf(item) {
  return kindMeta[item?.kind] || kindMeta.hypothesis
}

function evidenceText(item) {
  const list = item?.evidence || []
  if (!list.length) return ''
  return list
    .map((ev) => {
      const name = paperName(ev.documentId)
      return ev.page ? `${name} p${ev.page}` : name
    })
    .join('、')
}

function paperName(documentId) {
  const doc = documents.value.find((item) => item.id === documentId)
  return doc ? doc.name.replace(/\.pdf$/i, '').slice(0, 24) : documentId.slice(0, 8)
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
    ElMessage.warning(`最多选择 ${MAX_PAPERS} 篇`)
    return
  }
  selected.value.push(doc.id)
}

function isSelected(id) {
  return selected.value.includes(id)
}

async function startResearch() {
  if (!selected.value.length) {
    ElMessage.warning('至少选择一篇论文')
    return
  }
  try {
    await researchStore.start(selected.value, goal.value.trim())
  } catch (error) {
    notifyError(error, '创建研究任务失败')
  }
}

async function openBrief(item) {
  try {
    await researchStore.open(item.id)
  } catch (error) {
    notifyError(error, '打开失败')
  }
}

async function rerun() {
  if (!current.value) return
  try {
    await researchStore.rerun(current.value.id)
    ElMessage.success('已重新生成')
  } catch (error) {
    notifyError(error, '重跑失败')
  }
}

async function removeCurrent() {
  if (!current.value) return
  try {
    await ElMessageBox.confirm('删除这份研究辅助报告？论文本身不受影响。', '删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await researchStore.remove(current.value.id)
  ElMessage.success('已删除')
}

async function exportReport() {
  if (!current.value) return
  try {
    await researchStore.exportReport(current.value.id, current.value.goal || '研究辅助报告')
    ElMessage.success('报告已开始下载')
  } catch (error) {
    notifyError(error, '导出失败')
  }
}

watch(baseId, loadDocuments)

onMounted(async () => {
  if (!knowledgeStore.bases.length) await knowledgeStore.loadBases()
  const first = knowledgeStore.bases[0]
  if (first) baseId.value = first.id
  await researchStore.loadList()
  const latest = researchStore.briefs[0]
  if (latest) await openBrief(latest)
})

onUnmounted(() => {
  researchStore.stopPolling()
})
</script>

<template>
  <div class="h-full overflow-y-auto scrollbar-thin">
    <div class="mx-auto w-full max-w-7xl px-4 py-6 md:px-6">
      <header class="mb-5 flex flex-wrap items-center gap-3">
        <div class="min-w-0 flex-1">
          <h1 class="text-xl font-semibold app-text">研究助手</h1>
          <p class="mt-1 text-sm app-muted">
            基于所选论文给出方向、问题、思路、技术路线与阶段计划。
            <span class="app-accent">文献依据</span>与
            <span class="text-amber-500">AI 假设</span>分开标注，不保证创新性。
          </p>
        </div>
        <template v-if="ready">
          <el-button :icon="Refresh" @click="rerun">重新生成</el-button>
          <el-button :icon="Delete" @click="removeCurrent">删除</el-button>
          <el-button type="primary" :icon="Download" @click="exportReport">导出报告</el-button>
        </template>
      </header>

      <div class="grid gap-5 lg:grid-cols-[340px_1fr]">
        <!-- 左侧 -->
        <aside class="space-y-4">
          <section class="rounded-xl border app-border app-panel p-4">
            <div class="mb-3 flex items-center gap-2">
              <el-icon class="text-base app-accent"><Star /></el-icon>
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

            <div v-loading="docsLoading" class="mt-3 max-h-[260px] space-y-1 overflow-auto scrollbar-thin">
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
              <p v-if="!documents.length && !docsLoading" class="py-6 text-center text-xs app-muted">
                该知识库还没有文档
              </p>
            </div>

            <el-input
              v-model="goal"
              class="mt-3"
              type="textarea"
              :rows="3"
              maxlength="200"
              show-word-limit
              placeholder="你的研究目标（可选）：例如「探索 RAG 在垂直领域小样本场景下的检索质量优化」"
            />

            <div class="mt-3 flex items-center justify-between text-xs app-muted">
              <span>已选 {{ selected.length }} / {{ MAX_PAPERS }}</span>
              <el-button v-if="selected.length" link size="small" @click="selected = []">清空</el-button>
            </div>

            <el-button
              type="primary"
              class="mt-2 w-full"
              :disabled="!selected.length"
              :loading="researchStore.busy"
              @click="startResearch"
            >
              生成研究建议
            </el-button>
          </section>

          <section v-if="researchStore.briefs.length" class="rounded-xl border app-border app-panel p-3">
            <p class="mb-2 px-1 text-xs app-muted">历史报告</p>
            <button
              v-for="item in researchStore.briefs"
              :key="item.id"
              class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition app-hover"
              :class="current?.id === item.id ? 'app-active' : ''"
              @click="openBrief(item)"
            >
              <span class="min-w-0 flex-1 truncate text-xs app-text">
                {{ item.goal || '未命名研究' }}
              </span>
              <el-tag v-if="item.status === 'ready'" size="small" type="success">就绪</el-tag>
              <el-tag v-else-if="item.status === 'failed'" size="small" type="danger">失败</el-tag>
              <el-tag v-else size="small" type="warning">生成中</el-tag>
            </button>
          </section>
        </aside>

        <!-- 右侧 -->
        <main class="min-w-0">
          <section v-if="running" class="rounded-xl border app-border app-panel p-6">
            <p class="text-sm font-medium app-text">
              {{ stageText[current.stage] || '分析中' }}…
            </p>
            <el-progress class="mt-3" :percentage="current.progress || 0" :stroke-width="8" />
            <p class="mt-3 text-xs app-muted">
              正在逐篇抽取文献事实并生成建议，通常 1~2 分钟（卡片有缓存会更快）。
            </p>
          </section>

          <section v-else-if="current?.status === 'failed'" class="rounded-xl border app-border app-panel p-6">
            <p class="text-sm font-medium text-red-500">生成失败</p>
            <p class="mt-2 whitespace-pre-wrap text-xs app-muted">{{ current.error || '未知原因' }}</p>
            <el-button class="mt-4" type="primary" :icon="Refresh" @click="rerun">重试</el-button>
          </section>

          <div v-else-if="ready" class="space-y-4">
            <!-- 研究方向 -->
            <section v-if="current.directions?.length" class="rounded-xl border app-border app-panel p-5">
              <h2 class="text-sm font-semibold app-text">一、值得探索的研究方向</h2>
              <div class="mt-3 space-y-3">
                <div
                  v-for="(item, index) in current.directions"
                  :key="index"
                  class="rounded-lg border app-border p-3"
                >
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-sm font-medium app-text">{{ index + 1 }}. {{ item.title }}</span>
                    <el-tag size="small" :type="kindOf(item).type" effect="plain">
                      {{ kindOf(item).label }}
                    </el-tag>
                  </div>
                  <p class="mt-1.5 text-xs leading-6 app-text">{{ item.rationale }}</p>
                  <p class="mt-1 text-xs leading-6 app-muted">
                    <span class="app-accent">已做到：</span>{{ item.already_done }}
                    <span class="ml-2 app-accent">尚未覆盖：</span>{{ item.gap }}
                  </p>
                  <p class="mt-1 text-[11px] app-muted">门槛与风险：{{ item.risk }}</p>
                  <p v-if="evidenceText(item)" class="mt-1 text-[11px] app-accent">
                    依据：{{ evidenceText(item) }}
                  </p>
                </div>
              </div>
            </section>

            <!-- 研究问题 -->
            <section v-if="current.questions?.length" class="rounded-xl border app-border app-panel p-5">
              <h2 class="text-sm font-semibold app-text">二、可研究的问题与思路</h2>
              <div class="mt-3 space-y-3">
                <div
                  v-for="(item, index) in current.questions"
                  :key="index"
                  class="rounded-lg border app-border p-3"
                >
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-sm font-medium app-text">问题 {{ index + 1 }}：{{ item.question }}</span>
                    <el-tag size="small" :type="kindOf(item).type" effect="plain">
                      {{ kindOf(item).label }}
                    </el-tag>
                  </div>
                  <p v-if="item.why" class="mt-1.5 text-xs leading-6 app-muted">{{ item.why }}</p>
                  <p v-if="evidenceText(item)" class="mt-1 text-[11px] app-accent">
                    依据：{{ evidenceText(item) }}
                  </p>
                  <ul class="mt-2 space-y-1">
                    <li
                      v-for="(approach, ai) in item.approaches || []"
                      :key="ai"
                      class="text-xs leading-6 app-text"
                    >
                      · <span class="font-medium">{{ approach.title }}</span>
                      <span class="app-muted">（成本 {{ approach.cost }}）</span>：{{ approach.how }}
                      <span class="app-muted">｜风险：{{ approach.risk }}</span>
                    </li>
                  </ul>
                </div>
              </div>
            </section>

            <!-- 创新空间 -->
            <section v-if="current.novelty?.coverage?.length || current.novelty?.openings?.length" class="rounded-xl border app-border app-panel p-5">
              <h2 class="text-sm font-semibold app-text">三、创新空间分析</h2>
              <div class="mt-3 space-y-2">
                <p
                  v-for="(item, index) in current.novelty.coverage || []"
                  :key="`c${index}`"
                  class="text-xs leading-6 app-text"
                >
                  <el-tag size="small" type="success" effect="plain">已覆盖</el-tag>
                  <span class="ml-2 font-medium">{{ item.aspect }}</span>：{{ item.covered }}
                </p>
                <p
                  v-for="(item, index) in current.novelty.openings || []"
                  :key="`o${index}`"
                  class="text-xs leading-6 app-text"
                >
                  <el-tag size="small" type="warning" effect="plain">尚未覆盖</el-tag>
                  <span class="ml-2 font-medium">{{ item.opening }}</span>
                  <span class="app-muted">（把握度 {{ item.confidence }}）：{{ item.why_open }}</span>
                </p>
              </div>
              <p class="mt-3 rounded-lg bg-amber-500/10 px-3 py-2 text-[11px] leading-5 text-amber-600 dark:text-amber-300">
                ⚠️ {{ current.novelty.caveat }}
              </p>
            </section>

            <!-- 技术路线与计划 -->
            <section v-if="current.roadmap?.routes?.length || current.roadmap?.roadmap?.length" class="rounded-xl border app-border app-panel p-5">
              <h2 class="text-sm font-semibold app-text">四、技术路线与阶段计划</h2>
              <div class="mt-3 space-y-2">
                <p
                  v-for="(route, index) in current.roadmap.routes || []"
                  :key="index"
                  class="text-xs leading-6 app-text"
                >
                  <el-tag size="small" type="info" effect="plain">路线</el-tag>
                  <span class="ml-2 font-medium">{{ route.title }}</span>
                  <span class="app-muted">（成本 {{ route.cost }}）：适用 {{ route.when }}；{{ route.how }}；风险 {{ route.risk }}</span>
                </p>
              </div>
              <div v-if="current.roadmap.roadmap?.length" class="mt-3 overflow-x-auto scrollbar-thin">
                <table class="w-full text-left text-xs">
                  <thead>
                    <tr class="app-muted">
                      <th class="pb-2 pr-3 font-medium">阶段</th>
                      <th class="pb-2 pr-3 font-medium">目标</th>
                      <th class="pb-2 pr-3 font-medium">任务</th>
                      <th class="pb-2 pr-3 font-medium">产出</th>
                      <th class="pb-2 font-medium">风险</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(phase, index) in current.roadmap.roadmap"
                      :key="index"
                      class="border-t app-border align-top"
                    >
                      <td class="py-2 pr-3 app-text">{{ phase.phase }}</td>
                      <td class="py-2 pr-3 app-text">{{ phase.goal }}</td>
                      <td class="py-2 pr-3 app-muted">{{ (phase.tasks || []).join('；') }}</td>
                      <td class="py-2 pr-3 app-muted">{{ phase.deliverable }}</td>
                      <td class="py-2 app-muted">{{ phase.risk }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <!-- 相关工作 -->
            <section v-if="current.relatedWork?.groups?.length" class="rounded-xl border app-border app-panel p-5">
              <h2 class="text-sm font-semibold app-text">五、相关工作梳理</h2>
              <ul class="mt-3 space-y-1">
                <li
                  v-for="(group, index) in current.relatedWork.groups"
                  :key="index"
                  class="text-xs leading-6 app-text"
                >
                  · <span class="font-medium">{{ group.theme }}</span>：{{ group.summary }}
                </li>
              </ul>
              <template v-if="current.relatedWork.further_reading?.length">
                <p class="mt-3 text-xs app-muted">建议补充检索（只是检索建议，不是文献引用）：</p>
                <ul class="mt-1 space-y-1">
                  <li
                    v-for="(item, index) in current.relatedWork.further_reading"
                    :key="index"
                    class="text-[11px] leading-5 app-muted"
                  >
                    · {{ item.topic }} —— {{ item.why }}
                    <span v-if="item.keywords?.length">（{{ item.keywords.join('、') }}）</span>
                  </li>
                </ul>
              </template>
            </section>

            <!-- 本地相关文献 -->
            <section v-if="current.relatedDocs?.length" class="rounded-xl border app-border app-panel p-5">
              <h2 class="text-sm font-semibold app-text">六、库里可能相关的其它文献</h2>
              <ul class="mt-2 space-y-1">
                <li v-for="doc in current.relatedDocs" :key="doc.documentId" class="text-xs app-text">
                  · {{ doc.name }}
                </li>
              </ul>
              <p class="mt-2 text-[11px] app-muted">
                按标题相似度推荐，<span class="font-medium">没有</span>经过相关性验证。
              </p>
            </section>
          </div>

          <section v-else class="rounded-xl border app-border app-panel p-10 text-center">
            <el-icon class="text-2xl app-accent"><Star /></el-icon>
            <p class="mt-3 text-sm app-text">选择论文、填一个研究目标，点「生成研究建议」</p>
            <p class="mt-2 text-xs app-muted">
              会给出研究方向、研究问题与思路、创新空间、技术路线与阶段计划 ——
              每条都标了是「文献依据」还是「AI 假设」。
            </p>
          </section>
        </main>
      </div>
    </div>
  </div>
</template>
