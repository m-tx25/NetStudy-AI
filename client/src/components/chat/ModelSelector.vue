<script setup>
/**
 * 生成模型选择器（只读 + 选择）。
 *
 * 职责边界（合并后确定的方案）：
 *   · **密钥与模型的新增/修改/删除**在「设置 → API 密钥」页完成
 *     （个人密钥 /api/keys，团队密钥 /api/teams/{id}/keys）；
 *   · 这里只负责**选用哪一个**，数据来自 GET /api/chat/models
 *     （服务端 .env 配置的模型 + 我的个人密钥 + 我所在团队的密钥）。
 *
 * 因此本组件不再提供「添加模型」—— 那会与密钥页重复，且已在合并中移除。
 *
 * 另外：模型与向量化是两件事。检索用的向量化模型由密钥页按知识库归属决定，
 * 不在此处切换。
 */
import { computed } from 'vue'
import { Cpu, MagicStick, Setting } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'

import { useChatStore } from '@/stores/chat'

const router = useRouter()
const chatStore = useChatStore()

const models = computed(() => chatStore.models)
const activeLabel = computed(() => chatStore.activeModel?.label || '选择模型')

/** 是否至少有一个可用的模型（服务端配置或已配密钥） */
const hasConfiguredModel = computed(() => models.value.some((model) => model.configured))

/** 来源标签：server=服务端配置，user/team=个人/团队密钥 */
function sourceLabel(model) {
  if (model.source === 'team') return '团队'
  if (model.source === 'user') return '个人'
  if (model.source === 'server') return '服务端'
  return model.source || ''
}

function hintOf(model) {
  if (!model.configured) return '未配置密钥'
  return sourceLabel(model)
}

function pick(id) {
  chatStore.selectModel(id)
}

function goSettings() {
  router.push('/app/settings')
}
</script>

<template>
  <el-popover placement="bottom-end" :width="340" trigger="click" popper-class="rag-model-popover">
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
          @click="goSettings"
        >
          <el-icon :size="12"><Setting /></el-icon>
          管理密钥
        </button>
      </div>

      <p class="text-[11px] leading-5 app-muted">
        选择由哪个模型生成回答。向量化模型按知识库归属自动选用，与此处无关。
      </p>

      <el-scrollbar max-height="260px">
        <div class="space-y-1 pr-1">
          <button
            v-for="model in models"
            :key="model.id"
            class="flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left transition"
            :class="model.id === chatStore.selectedModelId ? 'app-accent-soft' : 'app-hover'"
            @click="pick(model.id)"
          >
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
              </span>
              <span class="mt-0.5 flex items-center gap-1.5 text-[10px] app-muted">
                <span class="truncate">{{ model.model }}</span>
                <span>·</span>
                <span :class="model.configured ? '' : 'text-amber-500'">{{ hintOf(model) }}</span>
              </span>
            </span>
          </button>

          <p v-if="!models.length" class="px-3 py-2 text-[11px] app-muted">
            还没有可用模型。请到「设置 → API 密钥」添加你的密钥。
          </p>
        </div>
      </el-scrollbar>

      <!-- 一个都没配置时给出可操作指引 -->
      <div
        v-if="models.length && !hasConfiguredModel"
        class="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300"
      >
        <p class="font-medium">尚未配置可用的模型</p>
        <p class="mt-0.5">
          到「设置 → API 密钥」填写自己的密钥即可（支持个人级与团队级）。
          当前仍可检索知识库，但不会生成真实回答。
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
</template>
