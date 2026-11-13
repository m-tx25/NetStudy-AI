<script setup>
/**
 * 团队知识库面板
 *
 * 背景：团队知识库原先只能在「知识库管理 → 新建 → 归属选团队」创建，
 * 团队页只有一个数字（N 个知识库），成员根本找不到入口。
 * 这里把「查看 + 新建 + 跳转上传」搬到团队详情里。
 *
 * 后端无需改动：
 *   GET  /knowledge-bases      返回「我的个人库 + 我所在团队的库」，前端按 ownerId 过滤
 *   POST /knowledge-bases      传 { name, description, teamId } 即建成团队库
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { FolderOpened, Plus } from '@element-plus/icons-vue'

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBases,
} from '@/api/knowledge'
import { notifyError, notifySuccess } from '@/utils/notify'

const props = defineProps({
  teamId: { type: String, required: true },
  /** 是否能新建（团队成员都可以，与后端 /knowledge-bases 的成员校验一致） */
  canCreate: { type: Boolean, default: false },
  /** 是否能删除（仅负责人/管理员；后端目前只要成员即可，这里收得更严） */
  canDelete: { type: Boolean, default: false },
})

const router = useRouter()

const loading = ref(false)
const allBases = ref([])
const createVisible = ref(false)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({ name: '', description: '' })

const rules = {
  name: [
    { required: true, message: '请输入知识库名称', trigger: 'blur' },
    { max: 40, message: '名称不超过 40 个字符', trigger: 'blur' },
  ],
}

/** 只保留属于当前团队的库 */
const bases = computed(() =>
  allBases.value.filter(
    (base) => base.ownerType === 'team' && base.ownerId === props.teamId,
  ),
)

async function loadBases() {
  loading.value = true
  try {
    const list = await listKnowledgeBases()
    allBases.value = Array.isArray(list) ? list : []
  } catch (error) {
    notifyError(error, '加载团队知识库失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.name = ''
  form.description = ''
  createVisible.value = true
}

async function onSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      await createKnowledgeBase({
        name: form.name.trim(),
        description: form.description.trim(),
        teamId: props.teamId,
      })
      notifySuccess('团队知识库已创建')
      createVisible.value = false
      await loadBases()
    } catch (error) {
      notifyError(error, '创建失败')
    } finally {
      submitting.value = false
    }
  })
}

async function onDelete(base) {
  try {
    await ElMessageBox.confirm(
      `删除「${base.name}」会同时删除其中的文档与向量数据，且无法恢复。确定删除吗？`,
      '删除团队知识库',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteKnowledgeBase(base.id)
    notifySuccess('已删除')
    await loadBases()
  } catch (error) {
    notifyError(error, '删除失败')
  }
}

/** 跳到知识库管理页并选中该库，方便直接上传文档 */
function goUpload(base) {
  router.push({ name: 'knowledge', query: { base: base.id } })
}

onMounted(loadBases)
watch(() => props.teamId, loadBases)
</script>

<template>
  <div class="h-full overflow-y-auto pb-6">
    <div class="mb-3 flex items-center justify-between gap-3">
      <p class="text-xs leading-5 app-muted">
        团队知识库全员共享：成员都能上传，检索全员可用。
      </p>
      <el-button
        v-if="canCreate"
        type="primary"
        size="small"
        :icon="Plus"
        @click="openCreate"
      >
        新建
      </el-button>
    </div>

    <div v-if="loading" class="py-6 text-center app-muted">加载中…</div>

    <el-empty
      v-else-if="!bases.length"
      description="还没有团队知识库，新建一个后就能上传文档"
    />

    <ul v-else class="space-y-2">
      <li
        v-for="base in bases"
        :key="base.id"
        class="flex flex-wrap items-center gap-3 rounded-lg border app-border px-3 py-2"
      >
        <span
          class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-light to-brand text-white"
        >
          <el-icon><FolderOpened /></el-icon>
        </span>
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm app-text">{{ base.name }}</p>
          <p class="truncate text-[11px] app-muted">
            {{ base.documentCount ?? 0 }} 篇文档 · {{ base.chunkCount ?? 0 }} 个切片
            <span v-if="base.description"> · {{ base.description }}</span>
          </p>
        </div>
        <el-button size="small" @click="goUpload(base)">上传文档</el-button>
        <el-button
          v-if="canDelete"
          size="small"
          text
          type="danger"
          @click="onDelete(base)"
        >
          删除
        </el-button>
      </li>
    </ul>

    <el-dialog v-model="createVisible" title="新建团队知识库" width="440px">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="名称" prop="name">
          <el-input
            v-model="form.name"
            placeholder="例如：团队制度与流程"
            maxlength="40"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="简单说明这个库放什么资料"
          />
        </el-form-item>
        <p class="text-xs leading-5 app-muted">
          向量化与生成优先使用该团队的 API 密钥，未配置则用成员个人密钥或服务端密钥。
        </p>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">
          创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
