<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Collection, Setting } from '@element-plus/icons-vue'

import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'

const router = useRouter()
const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()

const bases = computed(() => knowledgeStore.bases)
const selectedIds = computed(() => chatStore.selectedKnowledgeBaseIds)

const allSelected = computed(
  () => bases.value.length > 0 && selectedIds.value.length === bases.value.length,
)

function isSelected(id) {
  return selectedIds.value.includes(id)
}

function toggle(id) {
  chatStore.toggleKnowledgeBase(id)
}

function selectAll() {
  chatStore.setSelectedKnowledgeBases(allSelected.value ? [] : bases.value.map((base) => base.id))
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
            <span class="block truncate text-sm app-text">
              {{ base.name }}
            </span>
            <span class="block text-[11px] app-muted">
              {{ base.documentCount ?? 0 }} 篇文档 · {{ base.chunkCount ?? 0 }} 个片段
            </span>
          </span>
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
