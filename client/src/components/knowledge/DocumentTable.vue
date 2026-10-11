<script setup>
import { Refresh, Delete, Document } from '@element-plus/icons-vue'

import { formatBytes, formatDateTime } from '@/utils/format'

defineProps({
  documents: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['remove', 'reindex', 'toggle'])

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
  return 'text-brand'
}
</script>

<template>
  <el-table
    v-loading="loading"
    :data="documents"
    style="width: 100%"
    row-key="id"
    :header-cell-style="{ fontWeight: '600' }"
  >
    <el-table-column label="文档" min-width="260">
      <template #default="{ row }">
        <div class="flex items-center gap-2.5 py-1">
          <span
            class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-black/5 dark:bg-white/10"
          >
            <el-icon class="text-base" :class="typeColor(row.name)"><Document /></el-icon>
          </span>
          <span class="min-w-0">
            <span class="block truncate text-sm text-[#0d0d0d] dark:text-[#ececec]" :title="row.name">
              {{ row.name }}
            </span>
            <span class="block text-[11px] text-[#8e8e8e]">
              {{ extensionOf(row.name) }} · {{ formatBytes(row.size) }}
            </span>
          </span>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="解析状态" width="120">
      <template #default="{ row }">
        <el-tag :type="statusOf(row.status).type" size="small" effect="light" round>
          {{ statusOf(row.status).label }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column label="向量片段" width="100" align="right">
      <template #default="{ row }">
        <span class="text-sm text-[#5d5d5d] dark:text-[#b4b4b4]">
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
        <span class="text-xs text-[#8e8e8e]">{{ formatDateTime(row.uploadedAt || row.createdAt) }}</span>
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
      <div class="py-10 text-center text-sm text-[#8e8e8e]">
        <p>这个知识库还没有文档</p>
        <p class="mt-1 text-xs">点击右上角「上传文档」添加你的第一份资料</p>
      </div>
    </template>
  </el-table>
</template>
