<script setup>
import { computed, ref } from 'vue'
import { Refresh, Delete, Document } from '@element-plus/icons-vue'

import { formatBytes, formatDateTime } from '@/utils/format'

const props = defineProps({
  documents: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['remove', 'reindex', 'toggle', 'batch-remove'])

// 勾选的行。用 id 数组而不是 row 对象，避免刷新后引用失效。
const selectedIds = ref([])

const selectedCount = computed(() => selectedIds.value.length)

function onSelectionChange(rows) {
  selectedIds.value = (rows || []).map((row) => row.id)
}

/** 批量删除：父组件负责确认与调用接口，这里只把选中的 id 抛出去 */
function onBatchRemove() {
  if (!selectedIds.value.length) return
  emit('batch-remove', [...selectedIds.value])
}

function clearSelection() {
  selectedIds.value = []
}

const statusMap = {
  ready: { label: '已就绪', type: 'success' },
  processing: { label: '解析中', type: 'warning' },
  pending: { label: '排队中', type: 'info' },
  failed: { label: '失败', type: 'danger' },
}

function statusOf(status) {
  return statusMap[status] || { label: status || '未知', type: 'info' }
}

function extensionOf(name = '') {
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index + 1).toUpperCase() : 'FILE'
}

function typeColor(name = '') {
  const ext = extensionOf(name).toLowerCase()
  if (ext === 'pdf') return 'text-red-500'
  if (['doc', 'docx'].includes(ext)) return 'text-blue-500'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'text-emerald-500'
  if (['md', 'markdown', 'txt'].includes(ext)) return 'text-slate-500'
  return 'app-accent'
}
</script>

<template>
  <!-- 批量操作条：只在勾选后出现，避免平时占地方 -->
  <div
    v-if="selectedCount"
    class="mb-2 flex items-center gap-3 rounded-lg border app-border px-3 py-2"
  >
    <span class="text-xs app-text">已选 {{ selectedCount }} 个文档</span>
    <el-button size="small" text @click="clearSelection">清空选择</el-button>
    <el-button size="small" type="danger" plain :icon="Delete" @click="onBatchRemove">
      批量删除
    </el-button>
  </div>

  <el-table
    v-loading="loading"
    :data="documents"
    style="width: 100%"
    row-key="id"
    :header-cell-style="{ fontWeight: '600' }"
    @selection-change="onSelectionChange"
  >
    <el-table-column type="selection" width="42" reserve-selection />
    <el-table-column label="文档" min-width="260">
      <template #default="{ row }">
        <div class="flex items-center gap-2.5 py-1">
          <span
            class="grid h-8 w-8 shrink-0 place-items-center rounded-lg app-panel"
          >
            <el-icon class="text-base" :class="typeColor(row.name)"><Document /></el-icon>
          </span>
          <span class="min-w-0">
            <span class="block truncate text-sm app-text" :title="row.name">
              {{ row.name }}
            </span>
            <span class="block text-[11px] app-muted">
              {{ extensionOf(row.name) }} · {{ formatBytes(row.size) }}
            </span>
          </span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="解析状态" width="150">
      <template #default="{ row }">
        <!-- 失败时把后端给出的原因显示出来：鼠标悬停看详情，点「查看原因」看完整说明 -->
        <el-popover
          v-if="row.status === 'failed' && row.error"
          placement="top-start"
          :width="420"
          trigger="click"
          popper-class="doc-error-popover"
        >
          <template #reference>
            <span class="inline-flex items-center gap-1">
              <el-tag type="danger" size="small" effect="light" round>失败</el-tag>
              <el-button link type="danger" size="small">原因</el-button>
            </span>
          </template>
          <div class="text-xs leading-5 whitespace-pre-wrap break-words text-[--el-text-color-primary]">
            {{ row.error }}
          </div>
        </el-popover>

        <el-tag
          v-else
          :type="statusOf(row.status).type"
          size="small"
          effect="light"
          round
        >
          {{ statusOf(row.status).label }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column label="向量片段" width="100" align="right">
      <template #default="{ row }">
        <span class="text-sm app-text-secondary">
          {{ row.chunks ?? '-' }}
        </span>
      </template>
    </el-table-column>

    <el-table-column label="参与检索" width="100" align="center">
      <template #default="{ row }">
        <el-switch
          :model-value="row.enabled !== false"
          size="small"
          @change="(value) => emit('toggle', row, value)"
        />
      </template>
    </el-table-column>

    <el-table-column label="上传时间" width="170">
      <template #default="{ row }">
        <span class="text-xs app-muted">{{ formatDateTime(row.uploadedAt || row.createdAt) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="操作" width="130" align="right">
      <template #default="{ row }">
        <el-tooltip content="重新解析并向量化" placement="top" :show-after="300">
          <el-button
            link
            :icon="Refresh"
            :disabled="row.status === 'processing'"
            @click="emit('reindex', row)"
          />
        </el-tooltip>
        <el-tooltip content="删除文档" placement="top" :show-after="300">
          <el-button link type="danger" :icon="Delete" @click="emit('remove', row)" />
        </el-tooltip>
      </template>
    </el-table-column>

    <template #empty>
      <div class="py-10 text-center text-sm app-muted">
        <p>这个知识库还没有文档</p>
        <p class="mt-1 text-xs">点击右上角「上传文档」添加你的第一份资料</p>
      </div>
    </template>
  </el-table>
</template>
