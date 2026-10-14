<script setup>
/**
 * 生成模型选择器。
 *
 * 与「知识库」选择器的区别：
 *   - 知识库决定**检索范围**（用哪个库的资料）；
 *   - 这里决定**由哪个模型生成回答**。
 * 二者完全独立：向量化模型由后端 ZHIPUAI_* 配置决定，不在此处切换。
 *
 * 模型来源有两类：
 *   · 内置（builtin=true）—— 由服务端环境变量配置，全用户共享，不可改；
 *   · 自带（editable=true）—— 用户自己添加的本地部署或云端 API，可改可删。
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Cpu, Delete, Edit, MagicStick, Plus } from '@element-plus/icons-vue'

import AddModelDialog from '@/components/chat/AddModelDialog.vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

const models = computed(() => chatStore.models)
const active = computed(() => chatStore.activeModel)

const activeLabel = computed(() => active.value?.label || '选择模型')

/** 是否至少有一个已配置完成的模型 */
const hasConfiguredModel = computed(() => models.value.some((model) => model.configured))

const dialogVisible = ref(false)
const editingModel = ref(null)

function pick(id) {
  chatStore.selectModel(id)
}

function openCreate() {
  editingModel.value = null
  dialogVisible.value = true
}

function openEdit(model) {
  editingModel.value = model
  dialogVisible.value = true
}

async function removeModel(model) {
  try {
    await ElMessageBox.confirm(
      `确定删除模型「${model.label}」吗？删除后需要重新填写密钥才能恢复。`,
      '删除模型',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await chatStore.removeModel(model.id)
    ElMessage.success('模型已删除')
  } catch (error) {
    ElMessage.error(error?.message || '删除失败')
  }
}

/** 模型来源标签 */
function hintOf(model) {
  if (!model.configured) return '未配置密钥'
  return model.kind === 'local' ? '本地部署' : 'API'
}
</script>

<template>
  <el-popover placement="bottom-end" :width="360" trigger="click" popper-class="rag-model-popover">
    <template #reference>
      <button
        class="flex h-9 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition app-border app-muted app-hover hover-app-text"
        :title="`当前生成模型：${activeLabel}`"
      >
        <el-icon :size="14"><Cpu /></el-icon>
        <span class="max-w-[7.5rem] truncate">{{ activeLabel }}</span>
      </button>
    </template>

    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <span class="text-xs font-semibold app-text">生成模型</span>
        <button
          class="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-brand transition app-hover"
          @click="openCreate"
        >
          <el-icon :size="12"><Plus /></el-icon>
          添加模型
        </button>
      </div>

      <p class="text-[11px] leading-5 app-muted">
        选择由哪个模型生成回答。检索用的向量化模型由服务端配置，与此处无关。
      </p>

      <el-scrollbar max-height="280px">
        <div class="space-y-1 pr-1">
          <div
            v-for="model in models"
            :key="model.id"
            class="group flex w-full items-start gap-2 rounded-lg px-3 py-2 transition"
            :class="model.id === chatStore.selectedModelId ? 'app-accent-soft' : 'app-hover'"
          >
            <button class="flex min-w-0 flex-1 items-start gap-2 text-left" @click="pick(model.id)">
              <el-icon
                :size="14"
                class="mt-0.5 shrink-0"
                :class="model.id === chatStore.selectedModelId ? 'text-brand' : 'app-muted'"
              >
                <MagicStick />
              </el-icon>
              <span class="min-w-0 flex-1">
                <span class="flex items-center gap-1.5">
                  <span class="truncate text-xs font-medium app-text">{{ model.label }}</span>
                  <span
                    v-if="model.isDefault"
                    class="shrink-0 rounded border px-1 text-[10px] app-muted app-border"
                  >
                    默认
                  </span>
                  <span
                    v-if="model.editable"
                    class="shrink-0 rounded border px-1 text-[10px] text-brand"
                  >
                    自带
                  </span>
                </span>
                <span class="mt-0.5 flex items-center gap-1.5 text-[10px] app-muted">
                  <span class="truncate">{{ model.model }}</span>
                  <span>·</span>
                  <span :class="model.configured ? '' : 'text-amber-500'">{{ hintOf(model) }}</span>
                </span>
              </span>
            </button>

            <!-- 自带模型的编辑/删除入口 -->
            <span v-if="model.editable" class="flex shrink-0 items-center gap-0.5">
              <button
                class="grid h-6 w-6 place-items-center rounded app-muted transition app-hover hover-app-text"
                title="编辑"
                @click.stop="openEdit(model)"
              >
                <el-icon :size="12"><Edit /></el-icon>
              </button>
              <button
                class="grid h-6 w-6 place-items-center rounded app-muted transition hover:text-red-500"
                title="删除"
                @click.stop="removeModel(model)"
              >
                <el-icon :size="12"><Delete /></el-icon>
              </button>
            </span>
          </div>

          <p v-if="!models.length" class="px-3 py-2 text-[11px] app-muted">
            还没有可用模型，点上方「添加模型」接入本地服务或云端 API。
          </p>
        </div>
      </el-scrollbar>

      <!-- 一个都没配置完成时给出明确指引 -->
      <div
        v-if="models.length && !hasConfiguredModel"
        class="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300"
      >
        <p class="font-medium">尚未配置可用的模型</p>
        <p class="mt-0.5">
          点上方「添加模型」：本地部署可选 Ollama / vLLM / LM Studio 预设一键填入；
          云端 API 填写服务商地址与自己的密钥即可。当前仍可检索知识库，但不会生成真实回答。
        </p>
      </div>

      <p class="border-t app-border pt-2 text-[11px] leading-5 app-muted">
        <template v-if="chatStore.fallbackToModel">
          知识库中检索不到依据时，会由所选模型基于通用知识回答，并明确标注「非知识库依据」。
        </template>
        <template v-else>
          当前为严格模式：知识库检索不到依据时只作提示，不由模型自行作答。
        </template>
      </p>
    </div>
  </el-popover>

  <AddModelDialog v-model="dialogVisible" :model="editingModel" @saved="dialogVisible = false" />
</template>
