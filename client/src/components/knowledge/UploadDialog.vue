<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Document, UploadFilled } from '@element-plus/icons-vue'

import { useKnowledgeStore } from '@/stores/knowledge'
import { UPLOAD_LIMITS } from '@/config'
import { formatBytes } from '@/utils/format'
import { notifyError } from '@/utils/notify'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  knowledgeBaseId: { type: String, default: '' },
  baseName: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'uploaded'])

const knowledgeStore = useKnowledgeStore()

const uploadRef = ref(null)
const selectedFiles = ref([])
const submitting = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const totalSize = computed(() => selectedFiles.value.reduce((sum, file) => sum + file.size, 0))

const acceptList = computed(() => UPLOAD_LIMITS.accept.split(',').join(','))

function resetFiles() {
  selectedFiles.value = []
  uploadRef.value?.clearFiles?.()
}

watch(visible, (open) => {
  if (!open) resetFiles()
})

function validate(file) {
  const maxBytes = UPLOAD_LIMITS.maxSizeMB * 1024 * 1024
  if (file.size > maxBytes) {
    ElMessage.warning(`「${file.name}」超过 ${UPLOAD_LIMITS.maxSizeMB}MB 限制`)
    return false
  }
  const duplicate = selectedFiles.value.some(
    (item) => item.name === file.name && item.size === file.size,
  )
  if (duplicate) {
    ElMessage.warning(`「${file.name}」已在待上传列表中`)
    return false
  }
  return true
}

/** el-upload 设为 auto-upload=false，这里只负责收集文件 */
function handleChange(uploadFile) {
  const raw = uploadFile?.raw
  if (!raw) return
  if (validate(raw)) selectedFiles.value.push(raw)
  // 让 el-upload 自己维护的列表保持干净，界面由我们渲染
  nextTick(() => uploadRef.value?.clearFiles?.())
}

function handleExceed() {
  ElMessage.warning('一次最多选择 20 个文件')
}

/** el-progress 的 status：非终态返回 undefined，使用组件默认值 */
function progressStatus(task) {
  if (task.status === 'failed') return 'exception'
  if (task.status === 'done') return 'success'
  return undefined
}

function statusText(task) {
  if (task.status === 'done') return '已完成'
  if (task.status === 'failed') return '失败'
  if (task.status === 'processing') return '解析中…'
  return '上传中…'
}

function removeFile(index) {
  selectedFiles.value.splice(index, 1)
}

async function submit() {
  if (!props.knowledgeBaseId) {
    ElMessage.warning('请先选择知识库')
    return
  }
  if (!selectedFiles.value.length) {
    ElMessage.warning('请先选择要上传的文件')
    return
  }

  submitting.value = true
  try {
    await knowledgeStore.uploadFiles(props.knowledgeBaseId, [...selectedFiles.value])
    const failed = knowledgeStore.uploadTasks.filter((task) => task.status === 'failed').length
    if (failed) ElMessage.warning(`有 ${failed} 个文件上传失败，请重试`)
    else ElMessage.success('上传完成，文档已进入解析队列')
    emit('uploaded')
    resetFiles()
    visible.value = false
  } catch (error) {
    notifyError(error, '上传失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="baseName ? `上传文档 · ${baseName}` : '上传文档'"
    width="560px"
    :close-on-click-modal="!submitting"
    :close-on-press-escape="!submitting"
    :show-close="!submitting"
  >
    <el-upload
      ref="uploadRef"
      drag
      multiple
      :auto-upload="false"
      :show-file-list="false"
      :accept="acceptList"
      :limit="20"
      :on-change="handleChange"
      :on-exceed="handleExceed"
    >
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">把文件拖到这里，或 <em>点击选择文件</em></div>
      <template #tip>
        <div class="el-upload__tip">
          支持 {{ acceptList }}，单个文件不超过 {{ UPLOAD_LIMITS.maxSizeMB }}MB，一次最多 20 个
        </div>
      </template>
    </el-upload>

    <div v-if="selectedFiles.length" class="mt-4">
      <div class="mb-2 flex items-center justify-between text-xs text-[#8e8e8e]">
        <span>待上传 {{ selectedFiles.length }} 个文件</span>
        <span>共 {{ formatBytes(totalSize) }}</span>
      </div>

      <ul class="scrollbar-thin max-h-56 space-y-1.5 overflow-y-auto pr-1">
        <li
          v-for="(file, index) in selectedFiles"
          :key="`${file.name}-${file.size}-${index}`"
          class="flex items-center gap-2 rounded-lg border border-[#e5e5e5] px-3 py-2 dark:border-[#3a3a3a]"
        >
          <el-icon class="shrink-0 text-brand"><Document /></el-icon>
          <span class="min-w-0 flex-1 truncate text-sm text-[#0d0d0d] dark:text-[#ececec]">
            {{ file.name }}
          </span>
          <span class="shrink-0 text-xs text-[#8e8e8e]">{{ formatBytes(file.size) }}</span>
          <button
            class="grid h-6 w-6 shrink-0 place-items-center rounded text-[#8e8e8e] transition hover:bg-black/5 hover:text-red-500 dark:hover:bg-white/10"
            title="移除"
            @click="removeFile(index)"
          >
            <el-icon :size="13"><Delete /></el-icon>
          </button>
        </li>
      </ul>
    </div>

    <!-- 上传 / 解析进度 -->
    <div v-if="knowledgeStore.uploadTasks.length" class="mt-4 space-y-2">
      <p class="text-xs text-[#8e8e8e]">处理进度</p>
      <div
        v-for="task in knowledgeStore.uploadTasks"
        :key="task.id"
        class="rounded-lg bg-[#f7f7f8] px-3 py-2 dark:bg-[#2a2a2a]"
      >
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="min-w-0 flex-1 truncate text-[#0d0d0d] dark:text-[#ececec]">
            {{ task.name }}
          </span>
          <span
            :class="{
              'text-brand': task.status === 'done',
              'text-red-500': task.status === 'failed',
              'text-[#8e8e8e]': task.status === 'uploading' || task.status === 'processing',
            }"
          >
            {{ statusText(task) }}
          </span>
        </div>
        <el-progress
          class="mt-1.5"
          :percentage="task.progress"
          :status="progressStatus(task)"
          :stroke-width="4"
          :show-text="false"
        />
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-between">
        <button
          class="text-xs text-[#8e8e8e] hover:text-brand disabled:opacity-40"
          :disabled="submitting || !knowledgeStore.uploadTasks.length"
          @click="knowledgeStore.clearFinishedTasks()"
        >
          清空进度记录
        </button>
        <span class="flex gap-2">
          <el-button :disabled="submitting" @click="visible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="submitting"
            :disabled="!selectedFiles.length"
            @click="submit"
          >
            开始上传
          </el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</template>
