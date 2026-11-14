<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Collection, Document, Setting } from '@element-plus/icons-vue'

import { listDocuments } from '@/api/knowledge'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useTeamStore } from '@/stores/team'

const router = useRouter()
const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()
const teamStore = useTeamStore()

const bases = computed(() => knowledgeStore.bases)
const selectedIds = computed(() => chatStore.selectedKnowledgeBaseIds)
const selectedDocIds = computed(() => chatStore.selectedDocumentIds)

const allSelected = computed(
  () => bases.value.length > 0 && selectedIds.value.length === bases.value.length,
)

// 团队名称，用来在列表里标出「这是哪个团队的库」
const teamNameById = computed(() => {
  const map = new Map()
  for (const team of teamStore.teams || []) map.set(team.id, team.name)
  return map
})

function teamNameOf(base) {
  if (base.ownerType !== 'team') return ''
  return teamNameById.value.get(base.ownerId) || '团队'
}

/**
 * 论文范围（模块六「单篇 / 多篇论文问答」）。
 *
 * 只在已选的知识库里拉文档：用户只选了一个库时，列表就是这个库的全部论文，
 * 勾上即「只问这几篇」。不勾则维持知识库范围，行为与以前完全一致。
 */
const docPool = ref([])
const docsLoading = ref(false)

async function loadScopedDocs() {
  const ids = selectedIds.value
  if (!ids.length) {
    docPool.value = []
    return
  }
  docsLoading.value = true
  try {
    const lists = await Promise.all(
      ids.map((id) => listDocuments(id).catch(() => [])),
    )
    const seen = new Set()
    docPool.value = lists
      .flat()
      .filter((doc) => {
        if (seen.has(doc.id)) return false
        seen.add(doc.id)
        return true
      })
      .slice(0, 60)
  } finally {
    docsLoading.value = false
  }
}

watch(() => selectedIds.value.join(','), loadScopedDocs, { immediate: true })

onMounted(() => {
  // 只为把团队库标上团队名；失败不影响主流程
  teamStore.loadTeams().catch(() => {})
})

function isSelected(id) {
  return selectedIds.value.includes(id)
}

function toggle(id) {
  chatStore.toggleKnowledgeBase(id)
}

function selectAll() {
  chatStore.setSelectedKnowledgeBases(allSelected.value ? [] : bases.value.map((base) => base.id))
}

function isDocSelected(id) {
  return selectedDocIds.value.includes(id)
}

function toggleDoc(id) {
  chatStore.toggleDocumentScope(id)
}

function resetParams() {
  chatStore.topK = 5
  chatStore.scoreThreshold = 0.2
}
</script>

<template>
  <el-popover placement="bottom-end" :width="320" trigger="click" popper-class="rag-kb-popover">
    <template #reference>
      <button
        class="flex h-9 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition"
        :class="
          selectedIds.length
            ? 'app-accent-soft border-brand-light/40'
            : 'app-border app-muted app-hover hover-app-text'
        "
      >
        <el-icon :size="14"><Collection /></el-icon>
        <span>知识库</span>
        <span
          v-if="selectedIds.length"
          class="rounded-full bg-brand-light px-1.5 text-[10px] font-semibold leading-4 text-[#04140f]"
        >
          {{ selectedIds.length }}
        </span>
      </button>
    </template>

    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <p class="text-sm font-medium app-text">检索范围</p>
        <button
          v-if="bases.length"
          class="text-xs app-accent underline-offset-2 hover:underline"
          @click="selectAll"
        >
          {{ allSelected ? '清空' : '全选' }}
        </button>
      </div>

      <div v-if="knowledgeStore.basesLoading" class="py-4 text-center text-xs app-muted">
        加载中…
      </div>

      <div v-else-if="!bases.length" class="rounded-lg bg-amber-500/10 p-3 text-xs text-amber-600 dark:text-amber-300">
        还没有知识库，先去创建一个吧。
      </div>

      <div v-else class="max-h-56 space-y-1 overflow-y-auto scrollbar-thin pr-1">
        <div
          v-for="base in bases"
          :key="base.id"
          class="flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 transition app-hover"
          @click="toggle(base.id)"
        >
          <!-- 点击由外层容器统一处理，避免 label 嵌套导致的双向切换 -->
          <el-checkbox
            :model-value="isSelected(base.id)"
            class="pointer-events-none mt-0.5"
            tabindex="-1"
          />
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-1.5">
              <!-- 团队库要能一眼看出来：否则同一批列表里个人库与团队库长得一样 -->
              <el-tag
                v-if="base.ownerType === 'team'"
                size="small"
                type="primary"
                effect="plain"
                class="shrink-0"
              >
                团队
              </el-tag>
              <span class="truncate text-sm app-text">{{ base.name }}</span>
            </span>
            <span class="block truncate text-[11px] app-muted">
              <template v-if="base.ownerType === 'team'">
                团队「{{ teamNameOf(base) }}」·
              </template>
              {{ base.documentCount ?? 0 }} 篇文档 · {{ base.chunkCount ?? 0 }} 个片段
            </span>
          </span>
        </div>
      </div>

      <el-divider class="!my-2" />

      <!-- 论文范围：勾选后只在这几篇论文里检索（单篇 / 多篇论文问答） -->
      <div v-if="selectedIds.length" class="space-y-1.5">
        <div class="flex items-center justify-between">
          <p class="text-sm font-medium app-text">
            论文范围
            <span class="text-[11px] app-muted">（可选）</span>
          </p>
          <button
            v-if="selectedDocIds.length"
            class="text-xs app-accent underline-offset-2 hover:underline"
            @click="chatStore.clearDocumentScope()"
          >
            清空
          </button>
        </div>
        <p class="text-[11px] leading-4 app-muted">
          <template v-if="selectedDocIds.length">
            只在这 {{ selectedDocIds.length }} 篇里检索，回答会逐篇说明依据。
          </template>
          <template v-else>不选则按整个知识库检索。</template>
        </p>

        <div v-loading="docsLoading" class="max-h-36 space-y-0.5 overflow-y-auto scrollbar-thin pr-1">
          <div
            v-for="doc in docPool"
            :key="doc.id"
            class="flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1 transition app-hover"
            @click="toggleDoc(doc.id)"
          >
            <el-checkbox
              :model-value="isDocSelected(doc.id)"
              class="pointer-events-none mt-0.5"
              tabindex="-1"
            />
            <span class="min-w-0 flex-1">
              <span class="block truncate text-[12px] app-text">{{ doc.name }}</span>
              <span class="block text-[10px] app-muted">
                {{ doc.chunks ?? 0 }} 段
                <span v-if="doc.status === 'failed'" class="text-red-500">· 未完成向量化</span>
              </span>
            </span>
          </div>
          <p
            v-if="!docPool.length && !docsLoading"
            class="py-2 text-center text-[11px] app-muted"
          >
            该知识库还没有文档
          </p>
        </div>
      </div>

      <el-divider class="!my-2" />

      <div class="space-y-3">
        <div>
          <div class="mb-1 flex items-center justify-between text-xs">
            <span class="app-muted">召回数量 Top-K</span>
            <span class="font-medium app-text">{{ chatStore.topK }}</span>
          </div>
          <el-slider v-model="chatStore.topK" :min="1" :max="10" :step="1" size="small" />
        </div>

        <div>
          <div class="mb-1 flex items-center justify-between text-xs">
            <span class="app-muted">相似度阈值</span>
            <span class="font-medium app-text">
              {{ chatStore.scoreThreshold.toFixed(2) }}
            </span>
          </div>
          <el-slider
            v-model="chatStore.scoreThreshold"
            :min="0"
            :max="0.9"
            :step="0.05"
            size="small"
          />
        </div>
      </div>

      <div class="flex items-center justify-between pt-1">
        <button class="text-xs app-muted transition hover-app-accent" @click="resetParams">
          恢复默认
        </button>
        <button
          class="inline-flex items-center gap-1 text-xs app-accent hover:underline"
          @click="router.push({ name: 'knowledge' })"
        >
          <el-icon :size="13"><Setting /></el-icon>
          管理知识库
        </button>
      </div>
    </div>
  </el-popover>
</template>
