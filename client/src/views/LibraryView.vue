<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft,
  ArrowRight,
  CollectionTag,
  CopyDocument,
  Delete,
  Document,
  Plus,
  Search,
  Upload,
} from '@element-plus/icons-vue'

import {
  addNote,
  createCollection,
  createTag,
  deleteLibraryItem,
  deleteNote,
  exportCitation,
  fetchCollections,
  fetchLibrary,
  fetchNotes,
  fetchTags,
  updateLibraryItem,
  uploadLibraryFile,
} from '@/api/library'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const uploading = ref(false)

const filters = reactive({ status: '', collection: '', tag: '', q: '' })

const collections = ref([])
const tags = ref([])

const drawer = reactive({
  open: false,
  item: null,
  notes: [],
  noteText: '',
  notePage: undefined,
  citationFormat: 'bibtex',
  citation: '',
  saving: false,
})

const fileInput = ref(null)

const statusLabels = { unread: '未读', reading: '阅读中', read: '已读' }
const statusTypes = { unread: 'info', reading: 'warning', read: 'success' }

const hasItems = computed(() => items.value.length > 0)

onMounted(async () => {
  await Promise.all([load(), loadMeta()])
})

async function load() {
  loading.value = true
  try {
    const data = await fetchLibrary(
      {
        status: filters.status || undefined,
        collection: filters.collection || undefined,
        tag: filters.tag || undefined,
        q: filters.q.trim() || undefined,
        page: page.value,
        pageSize,
      },
      { silent: true },
    )
    items.value = data.items || []
    total.value = data.total || 0
  } catch (err) {
    ElMessage.error(err?.message || '加载文献库失败')
  } finally {
    loading.value = false
  }
}

async function loadMeta() {
  try {
    const [cols, tagList] = await Promise.all([
      fetchCollections({ silent: true }),
      fetchTags({ silent: true }),
    ])
    collections.value = cols || []
    tags.value = tagList || []
  } catch {
    /* 元数据失败不阻塞主列表 */
  }
}

function openItem(item) {
  drawer.open = true
  drawer.item = item
  drawer.notes = []
  drawer.noteText = ''
  drawer.notePage = undefined
  drawer.citation = ''
  loadNotes(item.id)
  loadCitation(item.id, drawer.citationFormat)
}

async function loadNotes(itemId) {
  try {
    drawer.notes = await fetchNotes(itemId, { silent: true })
  } catch {
    drawer.notes = []
  }
}

async function loadCitation(itemId, format) {
  try {
    const data = await exportCitation(itemId, format)
    drawer.citation = data.content || ''
  } catch {
    drawer.citation = ''
  }
}

function applyUpdated(updated) {
  const index = items.value.findIndex((row) => row.id === updated.id)
  if (index >= 0) items.value[index] = updated
  if (drawer.item?.id === updated.id) drawer.item = updated
}

async function patch(payload) {
  if (!drawer.item) return
  drawer.saving = true
  try {
    const updated = await updateLibraryItem(drawer.item.id, payload)
    applyUpdated(updated)
  } catch (err) {
    ElMessage.error(err?.message || '更新失败')
  } finally {
    drawer.saving = false
  }
}

async function setStatus(status) {
  await patch({ status })
}

async function toggleTag(tagId) {
  const current = (drawer.item?.tags || []).map((tag) => tag.id)
  const next = current.includes(tagId)
    ? current.filter((id) => id !== tagId)
    : [...current, tagId]
  await patch({ tagIds: next })
}

async function addNewNote() {
  if (!drawer.item || !drawer.noteText.trim()) {
    ElMessage.warning('请输入笔记内容')
    return
  }
  try {
    await addNote(drawer.item.id, {
      content: drawer.noteText.trim(),
      page: drawer.notePage || null,
    })
    drawer.noteText = ''
    drawer.notePage = undefined
    await loadNotes(drawer.item.id)
    ElMessage.success('笔记已保存')
  } catch (err) {
    ElMessage.error(err?.message || '保存笔记失败')
  }
}

async function removeNote(noteId) {
  try {
    await deleteNote(noteId)
    await loadNotes(drawer.item.id)
  } catch (err) {
    ElMessage.error(err?.message || '删除笔记失败')
  }
}

async function copyCitation() {
  try {
    await navigator.clipboard.writeText(drawer.citation)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('浏览器不允许访问剪贴板，请手动选择复制')
  }
}

function pickFile() {
  fileInput.value?.click()
}

async function onFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  uploading.value = true
  try {
    await uploadLibraryFile(file, { collectionId: filters.collection || undefined })
    ElMessage.success('已上传并开始解析')
    await Promise.all([load(), loadMeta()])
  } catch (err) {
    ElMessage.error(err?.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function newCollection() {
  try {
    const { value } = await ElMessageBox.prompt('分类名称', '新建分类', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValidator: (text) => (text && text.trim() ? true : '名称不能为空'),
    })
    await createCollection({ name: value.trim() })
    await loadMeta()
    ElMessage.success('分类已创建')
  } catch {
    /* 用户取消 */
  }
}

async function newTag() {
  try {
    const { value } = await ElMessageBox.prompt('标签名称', '新建标签', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValidator: (text) => (text && text.trim() ? true : '名称不能为空'),
    })
    await createTag({ name: value.trim() })
    await loadMeta()
  } catch {
    /* 用户取消 */
  }
}

async function removeItem() {
  if (!drawer.item) return
  try {
    await ElMessageBox.confirm('确定从文献库移除这篇文献吗？（不影响已上传的文档）', '移除文献', {
      type: 'warning',
      confirmButtonText: '移除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteLibraryItem(drawer.item.id)
    drawer.open = false
    await load()
    ElMessage.success('已移除')
  } catch (err) {
    ElMessage.error(err?.message || '移除失败')
  }
}

function changePage(delta) {
  const next = page.value + delta
  if (next < 1) return
  if (delta > 0 && items.value.length < pageSize) return
  page.value = next
  load()
}

function sourceLabel(source) {
  return (
    { openalex: 'OpenAlex', crossref: 'Crossref', arxiv: 'arXiv', semantic_scholar: 'Semantic Scholar', upload: '本地上传' }[
      source
    ] || source
  )
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-6 md:px-8">
    <header class="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold app-text">我的文献库</h1>
        <p class="mt-1 text-sm app-muted">
          共 {{ total }} 篇 · 支持收藏、分类、标签、阅读状态与引用导出
        </p>
      </div>
      <div class="flex gap-2">
        <el-button :icon="CollectionTag" @click="newCollection">新建分类</el-button>
        <el-button :icon="Plus" @click="newTag">新建标签</el-button>
        <el-button type="primary" :icon="Upload" :loading="uploading" @click="pickFile">
          上传 PDF
        </el-button>
        <input
          ref="fileInput"
          type="file"
          class="hidden"
          accept=".pdf,.docx,.doc,.md,.markdown,.txt"
          @change="onFileChange"
        />
      </div>
    </header>

    <!-- 筛选 -->
    <section class="app-panel rounded-xl border app-border p-3">
      <div class="grid gap-2 md:grid-cols-5">
        <el-input
          v-model="filters.q"
          placeholder="搜索标题 / 摘要"
          :prefix-icon="Search"
          clearable
          @keyup.enter="((page = 1), load())"
          @clear="((page = 1), load())"
        />
        <el-select v-model="filters.status" placeholder="全部状态" clearable @change="((page = 1), load())">
          <el-option label="未读" value="unread" />
          <el-option label="阅读中" value="reading" />
          <el-option label="已读" value="read" />
        </el-select>
        <el-select v-model="filters.collection" placeholder="全部分类" clearable @change="((page = 1), load())">
          <el-option v-for="col in collections" :key="col.id" :label="`${col.name}（${col.count}）`" :value="col.id" />
        </el-select>
        <el-select v-model="filters.tag" placeholder="全部标签" clearable @change="((page = 1), load())">
          <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" />
        </el-select>
        <el-button :icon="Search" @click="((page = 1), load())">筛选</el-button>
      </div>
    </section>

    <!-- 列表 -->
    <section class="mt-4">
      <div v-if="loading" class="py-16 text-center text-sm app-muted">加载中…</div>

      <div v-else-if="!hasItems" class="app-panel rounded-2xl border app-border px-6 py-16 text-center">
        <p class="text-sm font-medium app-text">文献库还是空的</p>
        <p class="mt-2 text-xs app-muted">
          去「文献检索」收藏论文，或直接上传本地 PDF。
        </p>
      </div>

      <div v-else class="space-y-2">
        <article
          v-for="item in items"
          :key="item.id"
          class="app-card cursor-pointer rounded-xl border app-border p-4 transition hover:border-brand/40"
          @click="openItem(item)"
        >
          <div class="flex items-start gap-3">
            <span class="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand">
              <el-icon><Document /></el-icon>
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex items-start justify-between gap-3">
                <h3 class="text-[15px] font-semibold leading-6 app-text">{{ item.paper.title }}</h3>
                <el-tag :type="statusTypes[item.status]" size="small" effect="plain">
                  {{ statusLabels[item.status] }}
                </el-tag>
              </div>
              <p class="mt-1 truncate text-xs app-muted">
                {{ (item.paper.authors || []).map((a) => a.name).slice(0, 3).join('、') || '作者信息缺失' }}
              </p>
              <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs app-muted">
                <span v-if="item.paper.venue">{{ item.paper.venue }}</span>
                <span v-if="item.paper.year">{{ item.paper.year }}</span>
                <span class="rounded bg-white/5 px-1.5 py-0.5 text-[11px]">{{ sourceLabel(item.paper.source) }}</span>
                <span v-if="item.hasPdf" class="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[11px] text-emerald-500">已解析 PDF</span>
                <span v-if="item.progress" class="text-[11px]">进度 {{ item.progress }}%</span>
              </div>
              <div v-if="item.tags?.length" class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="tag in item.tags"
                  :key="tag.id"
                  class="rounded-full px-2 py-0.5 text-[11px]"
                  :style="{ backgroundColor: `${tag.color || '#38bdf8'}22`, color: tag.color || '#38bdf8' }"
                >
                  {{ tag.name }}
                </span>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <!-- 分页 -->
    <div v-if="hasItems" class="mt-5 flex items-center justify-center gap-3">
      <el-button size="small" :icon="ArrowLeft" :disabled="page <= 1" @click="changePage(-1)">上一页</el-button>
      <span class="text-xs app-muted">第 {{ page }} 页</span>
      <el-button size="small" :disabled="items.length < pageSize" @click="changePage(1)">
        下一页<el-icon class="ml-1"><ArrowRight /></el-icon>
      </el-button>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawer.open" size="600px" :with-header="false">
      <div v-if="drawer.item" class="flex h-full flex-col">
        <div class="flex-1 overflow-y-auto scrollbar-thin p-6">
          <p class="text-xs app-muted">{{ sourceLabel(drawer.item.paper.source) }}</p>
          <h2 class="mt-2 text-lg font-semibold leading-7 app-text">{{ drawer.item.paper.title }}</h2>
          <p class="mt-2 text-xs leading-6 app-text-secondary">
            {{ (drawer.item.paper.authors || []).map((a) => a.name).join('、') || '作者信息缺失' }}
          </p>
          <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs app-muted">
            <span v-if="drawer.item.paper.venue">{{ drawer.item.paper.venue }}</span>
            <span v-if="drawer.item.paper.year">{{ drawer.item.paper.year }}</span>
            <span v-if="drawer.item.paper.citedBy">被引 {{ drawer.item.paper.citedBy }}</span>
            <a v-if="drawer.item.paper.doi" :href="`https://doi.org/${drawer.item.paper.doi}`" target="_blank" class="text-brand">
              DOI
            </a>
          </div>

          <h3 class="mt-5 text-sm font-semibold app-text">阅读状态</h3>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <el-button
              v-for="(label, key) in statusLabels"
              :key="key"
              size="small"
              :type="drawer.item.status === key ? 'primary' : ''"
              @click="setStatus(key)"
            >
              {{ label }}
            </el-button>
            <el-select
              :model-value="drawer.item.collectionId"
              placeholder="未分类"
              size="small"
              class="w-40"
              @change="(value) => patch({ collectionId: value })"
            >
              <el-option label="未分类" value="" />
              <el-option v-for="col in collections" :key="col.id" :label="col.name" :value="col.id" />
            </el-select>
          </div>

          <h3 class="mt-5 text-sm font-semibold app-text">标签</h3>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <button
              v-for="tag in tags"
              :key="tag.id"
              class="rounded-full px-2.5 py-1 text-[11px] transition"
              :class="
                (drawer.item.tags || []).some((row) => row.id === tag.id)
                  ? 'bg-brand text-white'
                  : 'app-hover app-muted'
              "
              :style="
                (drawer.item.tags || []).some((row) => row.id === tag.id) && tag.color
                  ? { backgroundColor: tag.color }
                  : {}
              "
              @click="toggleTag(tag.id)"
            >
              {{ tag.name }}
            </button>
            <button class="rounded-full px-2.5 py-1 text-[11px] app-muted app-hover" @click="newTag">
              + 新建
            </button>
          </div>

          <h3 class="mt-5 text-sm font-semibold app-text">摘要</h3>
          <p class="mt-2 whitespace-pre-wrap text-[13px] leading-7 app-text-secondary">
            {{ drawer.item.paper.abstract || '暂无摘要。' }}
          </p>

          <h3 class="mt-5 text-sm font-semibold app-text">阅读笔记</h3>
          <div class="mt-2 space-y-2">
            <div v-for="note in drawer.notes" :key="note.id" class="rounded-lg border app-border p-2.5">
              <div class="flex items-start justify-between gap-2">
                <p class="whitespace-pre-wrap text-xs leading-6 app-text-secondary">{{ note.content }}</p>
                <button class="text-xs app-muted hover:text-red-500" @click="removeNote(note.id)">
                  <el-icon><Delete /></el-icon>
                </button>
              </div>
              <p v-if="note.page" class="mt-1 text-[11px] app-muted">第 {{ note.page }} 页</p>
            </div>
            <div class="flex gap-2">
              <el-input-number v-model="drawer.notePage" :min="1" :controls="false" placeholder="页码" class="w-20" />
              <el-input v-model="drawer.noteText" placeholder="记录一条阅读笔记…" @keyup.enter="addNewNote" />
              <el-button :icon="Plus" @click="addNewNote" />
            </div>
          </div>

          <h3 class="mt-5 text-sm font-semibold app-text">引用导出</h3>
          <div class="mt-2 flex items-center gap-2">
            <el-select
              v-model="drawer.citationFormat"
              size="small"
              class="w-36"
              @change="(value) => loadCitation(drawer.item.id, value)"
            >
              <el-option label="BibTeX" value="bibtex" />
              <el-option label="RIS" value="ris" />
              <el-option label="APA" value="apa" />
              <el-option label="GB/T 7714" value="gbt7714" />
            </el-select>
            <el-button size="small" :icon="CopyDocument" @click="copyCitation">复制</el-button>
          </div>
          <pre class="mt-2 max-h-40 overflow-auto rounded-lg bg-black/30 p-3 text-[11px] leading-5 text-slate-300">{{ drawer.citation }}</pre>
        </div>

        <div class="flex gap-2 border-t app-border p-4">
          <el-button class="flex-1" @click="drawer.open = false">关闭</el-button>
          <el-button type="danger" plain :icon="Delete" @click="removeItem">移除</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>
