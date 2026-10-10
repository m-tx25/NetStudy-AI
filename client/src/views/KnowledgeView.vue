<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Collection,
  Edit,
  Expand,
  Plus,
  Refresh,
  Search,
  Upload,
} from '@element-plus/icons-vue'

import DocumentTable from '@/components/knowledge/DocumentTable.vue'
import UploadDialog from '@/components/knowledge/UploadDialog.vue'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useChatStore } from '@/stores/chat'
import { useSidebar } from '@/composables/useSidebar'
import { formatDateTime } from '@/utils/format'
import { notifyError } from '@/utils/notify'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()
const chatStore = useChatStore()
const { openMobileSidebar } = useSidebar()

const uploadVisible = ref(false)
const baseDialogVisible = ref(false)
const baseDialogMode = ref('create')
const baseFormRef = ref(null)
const baseSaving = ref(false)

const baseForm = reactive({ id: '', name: '', description: '' })

const baseRules = {
  name: [
    { required: true, message: '请输入知识库名称', trigger: 'blur' },
    { min: 1, max: 40, message: '名称长度为 1~40 个字符', trigger: 'blur' },
  ],
}

const activeBase = computed(() => knowledgeStore.activeBase)
const documents = computed(() => knowledgeStore.filteredDocuments)

const baseStats = computed(() => {
  const base = activeBase.value
  if (!base) return []
  return [
    { label: '文档', value: base.documentCount ?? knowledgeStore.documents.length },
    { label: '向量片段', value: base.chunkCount ?? knowledgeStore.totalChunks },
    { label: 'Embedding', value: base.embeddingModel || '未配置' },
    { label: '更新时间', value: formatDateTime(base.updatedAt) },
  ]
})

onMounted(async () => {
  await knowledgeStore.loadBases()
  if (knowledgeStore.activeBaseId) await knowledgeStore.loadDocuments()
})

// 切换知识库时加载对应文档
watch(
  () => knowledgeStore.activeBaseId,
  async (id, previous) => {
    if (!id || id === previous) return
    await knowledgeStore.loadDocuments(id)
  },
)

function openCreateDialog() {
  baseDialogMode.value = 'create'
  Object.assign(baseForm, { id: '', name: '', description: '' })
  baseDialogVisible.value = true
}

function openEditDialog(base) {
  baseDialogMode.value = 'edit'
  Object.assign(baseForm, {
    id: base.id,
    name: base.name,
    description: base.description || '',
  })
  baseDialogVisible.value = true
}

async function submitBaseForm() {
  if (!baseFormRef.value) return
  try {
    await baseFormRef.value.validate()
  } catch {
    return
  }

  baseSaving.value = true
  try {
    if (baseDialogMode.value === 'create') {
      const created = await knowledgeStore.createBase({
        name: baseForm.name.trim(),
        description: baseForm.description.trim(),
      })
      if (!created) return
      knowledgeStore.activeBaseId = created.id
      await knowledgeStore.loadDocuments(created.id)
      ElMessage.success('知识库创建成功，去上传文档吧')
    } else {
      const updated = await knowledgeStore.renameBase(baseForm.id, {
        name: baseForm.name.trim(),
        description: baseForm.description.trim(),
      })
      if (!updated) return
      ElMessage.success('已保存')
    }
    baseDialogVisible.value = false
  } finally {
    baseSaving.value = false
  }
}

async function removeBase(base) {
  try {
    await ElMessageBox.confirm(
      `删除知识库「${base.name}」会同时删除其中的 ${base.documentCount ?? 0} 篇文档，且不可恢复。`,
      '删除知识库',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const ok = await knowledgeStore.removeBase(base.id)
    if (!ok) return
    ElMessage.success('已删除')
    if (knowledgeStore.activeBaseId) await knowledgeStore.loadDocuments()
  } catch (error) {
    notifyError(error, '删除失败')
  }
}

async function removeDocument(row) {
  try {
    await ElMessageBox.confirm(`确定删除文档「${row.name}」吗？`, '删除文档', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await knowledgeStore.removeDocument(row.id)
    ElMessage.success('已删除')
  } catch (error) {
    notifyError(error, '删除失败')
  }
}

async function reindex(row) {
  ElMessage.info(`正在重新解析「${row.name}」…`)
  const updated = await knowledgeStore.reindex(row.id)
  if (updated) ElMessage.success('重新索引完成')
}

async function toggleDocument(row, enabled) {
  try {
    await knowledgeStore.toggleDocument(row.id, enabled)
    ElMessage.success(enabled ? '已加入检索范围' : '已移出检索范围')
  } catch (error) {
    notifyError(error, '更新失败')
  }
}

function openUpload() {
  if (!knowledgeStore.activeBaseId) {
    ElMessage.warning('请先创建或选择一个知识库')
    return
  }
  uploadVisible.value = true
}

function goChat() {
  chatStore.startNewConversation()
  router.push({ name: 'chat-new' })
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-white dark:bg-[#212121]">
    <!-- 顶部栏 -->
    <header
      class="flex h-14 shrink-0 items-center gap-2 border-b border-[#e5e5e5] px-3 md:px-5 dark:border-[#2f2f2f]"
    >
      <button
        class="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-[#5d5d5d] transition hover:bg-black/5 md:hidden dark:text-[#b4b4b4] dark:hover:bg-white/10"
        title="打开侧边栏"
        @click="openMobileSidebar"
      >
        <el-icon><Expand /></el-icon>
      </button>

      <div class="min-w-0 flex-1">
        <h1 class="truncate text-sm font-semibold text-[#0d0d0d] dark:text-[#ececec]">知识库管理</h1>
        <p class="truncate text-[11px] text-[#8e8e8e]">
          上传文档 → 自动解析分块 → 向量化入库 → 问答时按相似度召回
        </p>
      </div>

      <el-button :icon="Refresh" text @click="knowledgeStore.loadBases()">刷新</el-button>
      <el-button :icon="Plus" type="primary" @click="openCreateDialog">新建知识库</el-button>
    </header>

    <div class="flex min-h-0 flex-1">
      <!-- 左：知识库列表（桌面端） -->
      <aside
        class="hidden w-[268px] shrink-0 overflow-y-auto border-r border-[#e5e5e5] p-3 scrollbar-thin md:block dark:border-[#2f2f2f]"
      >
        <div v-if="knowledgeStore.basesLoading" class="py-8 text-center text-xs text-[#8e8e8e]">
          加载中…
        </div>

        <div
          v-else-if="!knowledgeStore.bases.length"
          class="rounded-xl border border-dashed border-[#dcdcdc] p-4 text-center text-xs leading-5 text-[#8e8e8e] dark:border-[#3a3a3a]"
        >
          还没有知识库<br />点击右上角「新建知识库」开始
        </div>

        <div v-else class="space-y-1">
          <div
            v-for="base in knowledgeStore.bases"
            :key="base.id"
            class="group cursor-pointer rounded-xl border px-3 py-2.5 transition"
            :class="
              base.id === knowledgeStore.activeBaseId
                ? 'border-brand/40 bg-brand/10'
                : 'border-transparent hover:bg-black/5 dark:hover:bg-white/10'
            "
            @click="knowledgeStore.selectBase(base.id)"
          >
            <div class="flex items-start gap-2">
              <el-icon
                class="mt-0.5 shrink-0 text-base"
                :class="base.id === knowledgeStore.activeBaseId ? 'text-brand' : 'text-[#8e8e8e]'"
              >
                <Collection />
              </el-icon>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium text-[#0d0d0d] dark:text-[#ececec]">
                  {{ base.name }}
                </p>
                <p class="mt-0.5 truncate text-[11px] text-[#8e8e8e]">
                  {{ base.documentCount ?? 0 }} 篇 · {{ base.chunkCount ?? 0 }} 片段
                </p>
              </div>
            </div>

            <div class="mt-1.5 flex items-center gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100">
              <button
                class="rounded px-1.5 py-0.5 text-[11px] text-[#8e8e8e] transition hover:bg-black/5 hover:text-brand dark:hover:bg-white/10"
                @click.stop="openEditDialog(base)"
              >
                编辑
              </button>
              <button
                class="rounded px-1.5 py-0.5 text-[11px] text-[#8e8e8e] transition hover:bg-black/5 hover:text-red-500 dark:hover:bg-white/10"
                @click.stop="removeBase(base)"
              >
                删除
              </button>
            </div>
          </div>
        </div>

        <button
          class="mt-3 w-full rounded-xl border border-dashed border-[#dcdcdc] py-2 text-xs text-[#8e8e8e] transition hover:border-brand hover:text-brand dark:border-[#3a3a3a]"
          @click="openCreateDialog"
        >
          + 新建知识库
        </button>
      </aside>

      <!-- 右：文档区 -->
      <section class="flex min-w-0 flex-1 flex-col">
        <!-- 移动端知识库切换 -->
        <div class="border-b border-[#e5e5e5] p-3 md:hidden dark:border-[#2f2f2f]">
          <el-select
            :model-value="knowledgeStore.activeBaseId"
            placeholder="选择知识库"
            class="w-full"
            @update:model-value="knowledgeStore.selectBase($event)"
          >
            <el-option
              v-for="base in knowledgeStore.bases"
              :key="base.id"
              :label="`${base.name}（${base.documentCount ?? 0} 篇）`"
              :value="base.id"
            />
          </el-select>
        </div>

        <template v-if="activeBase">
          <!-- 知识库信息 -->
          <div class="border-b border-[#e5e5e5] px-4 py-4 md:px-6 dark:border-[#2f2f2f]">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="truncate text-base font-semibold text-[#0d0d0d] dark:text-[#ececec]">
                  {{ activeBase.name }}
                </h2>
                <p class="mt-1 text-xs leading-5 text-[#8e8e8e]">
                  {{ activeBase.description || '暂无描述' }}
                </p>
              </div>

              <div class="flex shrink-0 items-center gap-2">
                <el-button :icon="Edit" text @click="openEditDialog(activeBase)">编辑</el-button>
                <el-button :icon="Upload" type="primary" @click="openUpload">上传文档</el-button>
              </div>
            </div>

            <div class="mt-3 flex flex-wrap gap-x-6 gap-y-2">
              <div v-for="stat in baseStats" :key="stat.label">
                <p class="text-[11px] text-[#8e8e8e]">{{ stat.label }}</p>
                <p class="text-sm font-medium text-[#0d0d0d] dark:text-[#ececec]">{{ stat.value }}</p>
              </div>
            </div>
          </div>

          <!-- 工具条 -->
          <div class="flex flex-wrap items-center gap-2 px-4 py-3 md:px-6">
            <el-input
              v-model="knowledgeStore.keyword"
              placeholder="按文件名搜索"
              clearable
              :prefix-icon="Search"
              class="max-w-[240px]"
            />
            <span class="text-xs text-[#8e8e8e]">
              共 {{ documents.length }} 个文档
              <template v-if="knowledgeStore.keyword">
                （全部 {{ knowledgeStore.documents.length }} 个）
              </template>
            </span>
            <span class="flex-1" />
            <el-button :icon="Refresh" text @click="knowledgeStore.loadDocuments()">刷新</el-button>
            <el-button text type="primary" @click="goChat">去提问</el-button>
          </div>

          <!-- 文档表格 -->
          <div class="min-h-0 flex-1 overflow-auto px-4 pb-6 md:px-6 scrollbar-thin">
            <DocumentTable
              :documents="documents"
              :loading="knowledgeStore.documentsLoading"
              @remove="removeDocument"
              @reindex="reindex"
              @toggle="toggleDocument"
            />
          </div>
        </template>

        <div v-else class="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <el-icon class="text-4xl text-[#d0d0d0]"><Collection /></el-icon>
          <p class="text-sm text-[#8e8e8e]">请选择或创建一个知识库</p>
          <el-button type="primary" :icon="Plus" @click="openCreateDialog">新建知识库</el-button>
        </div>
      </section>
    </div>

    <!-- 上传弹窗 -->
    <UploadDialog
      v-model="uploadVisible"
      :knowledge-base-id="knowledgeStore.activeBaseId || ''"
      :base-name="activeBase?.name || ''"
      @uploaded="knowledgeStore.loadDocuments()"
    />

    <!-- 新建 / 编辑知识库 -->
    <el-dialog
      v-model="baseDialogVisible"
      :title="baseDialogMode === 'create' ? '新建知识库' : '编辑知识库'"
      width="460px"
    >
      <el-form ref="baseFormRef" :model="baseForm" :rules="baseRules" label-position="top">
        <el-form-item label="名称" prop="name">
          <el-input v-model="baseForm.name" placeholder="例如：产品需求文档库" maxlength="40" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="baseForm.description"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="简单说明这个知识库放什么资料，方便团队协作"
          />
        </el-form-item>
        <p v-if="baseDialogMode === 'create'" class="text-xs leading-5 text-[#8e8e8e]">
          创建后即可上传文档。文档会经过解析 → 分块 → 向量化，完成后自动参与问答检索。
        </p>
      </el-form>

      <template #footer>
        <el-button @click="baseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="baseSaving" @click="submitBaseForm">
          {{ baseDialogMode === 'create' ? '创建' : '保存' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
