<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import {
  deleteTeamKey,
  deleteUserKey,
  getKeyOverview,
  getTeamKeyOverview,
  listProviders,
  saveTeamKey,
  saveUserKey,
  updateTeamKey,
  updateUserKey,
} from '@/api/keys'
import { notifyError, notifySuccess } from '@/utils/notify'

/**
 * API 密钥管理器：个人级与团队级共用。
 *
 * 安全说明（界面上也要讲清楚，避免用户误解）：
 *   - 密钥由后端加密存储，页面只显示掩码，**任何人都无法查看明文**；
 *   - 更新时密钥留空表示「只改其它字段」。
 *
 * 生效规则：
 *   - 个人密钥 → 作用于自己的个人知识库
 *   - 团队密钥 → 作用于该团队的知识库（费用归团队）
 *   - 未配置时回落到服务端全局 Key
 */
const props = defineProps({
  /** 'user' | 'team' */
  scope: { type: String, default: 'user' },
  /** scope='team' 时必填 */
  teamId: { type: String, default: '' },
})

const loading = ref(false)
const saving = ref(false)
const providers = ref([])
const keys = ref([])
const effective = ref({})
const dialogVisible = ref(false)
const editing = ref(null)

const form = reactive({
  provider: 'deepseek',
  secret: '',
  label: '',
  model: '',
  baseUrl: '',
  enabled: true,
})

const title = computed(() => (props.scope === 'team' ? '团队 API 密钥' : '我的 API 密钥'))
const currentProvider = computed(
  () => providers.value.find((item) => item.id === form.provider) || null,
)
const keyPlaceholder = computed(() => currentProvider.value?.keyHint || '粘贴密钥')
const isTeam = computed(() => props.scope === 'team')

/** 未配置任何密钥时用的是服务端全局 Key */
const usingServerKey = computed(() => !keys.value.some((k) => k.enabled))

async function load() {
  loading.value = true
  try {
    const [providerList, overview] = await Promise.all([
      listProviders(),
      isTeam.value ? getTeamKeyOverview(props.teamId) : getKeyOverview(),
    ])
    providers.value = Array.isArray(providerList) ? providerList : []
    keys.value = (isTeam.value ? overview?.teamKeys : overview?.userKeys) || []
    effective.value = overview?.effective || {}
  } catch (error) {
    notifyError(error, '密钥信息加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    provider: 'deepseek',
    secret: '',
    label: '',
    model: '',
    baseUrl: '',
    enabled: true,
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    provider: row.provider,
    secret: '',
    label: row.label || '',
    model: row.model || '',
    baseUrl: row.baseUrl || '',
    enabled: row.enabled !== false,
  })
  dialogVisible.value = true
}

/** 切换供应商时带出默认 baseUrl / 模型，省去手工填写 */
function onProviderChange(providerId) {
  const meta = providers.value.find((item) => item.id === providerId)
  if (!meta) return
  form.baseUrl = meta.defaultBaseUrl || ''
  form.model = meta.defaultChatModel || meta.defaultEmbeddingModel || ''
}

async function submit() {
  if (!editing.value && !form.secret.trim()) {
    notifyError(null, '请输入密钥')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      const payload = {
        label: form.label,
        model: form.model,
        baseUrl: form.baseUrl,
        enabled: form.enabled,
      }
      // 留空表示不改密钥
      if (form.secret.trim()) payload.secret = form.secret.trim()
      if (isTeam.value) {
        await updateTeamKey(props.teamId, editing.value.id, payload)
      } else {
        await updateUserKey(editing.value.id, payload)
      }
      notifySuccess('已保存')
    } else {
      const payload = { ...form, secret: form.secret.trim() }
      if (isTeam.value) {
        await saveTeamKey(props.teamId, payload)
      } else {
        await saveUserKey(payload)
      }
      notifySuccess('密钥已保存（加密存储，仅显示掩码）')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    notifyError(error, '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(row, enabled) {
  try {
    const payload = { enabled }
    if (isTeam.value) {
      await updateTeamKey(props.teamId, row.id, payload)
    } else {
      await updateUserKey(row.id, payload)
    }
    row.enabled = enabled
    notifySuccess(enabled ? '已启用' : '已停用')
    await load()
  } catch (error) {
    notifyError(error, '操作失败')
  }
}

async function remove(row) {
  try {
    if (isTeam.value) {
      await deleteTeamKey(props.teamId, row.id)
    } else {
      await deleteUserKey(row.id)
    }
    notifySuccess('已删除')
    await load()
  } catch (error) {
    notifyError(error, '删除失败')
  }
}

const capabilityLabels = { embedding: '向量化', chat: '生成' }

onMounted(load)
</script>

<template>
  <div>
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <div class="min-w-0 flex-1">
        <h3 class="text-sm font-medium app-text">{{ title }}</h3>
        <p class="mt-0.5 text-xs app-muted">
          {{
            isTeam
              ? '团队密钥作用于本团队的知识库，费用由团队承担（仅负责人/管理员可配置）。'
              : '个人密钥作用于你自己的个人知识库；团队知识库请在各团队的设置里配置。'
          }}
        </p>
      </div>
      <el-button size="small" type="primary" @click="openCreate">添加密钥</el-button>
    </div>

    <!-- 未配置时的提示 -->
    <el-alert
      v-if="usingServerKey && !loading"
      type="info"
      :closable="false"
      show-icon
      class="mb-3"
      title="当前使用服务端全局密钥"
      description="未配置自己的密钥时，向量化与生成都使用服务端 .env 里的 Key。配置自己的密钥后将优先使用。"
    />

    <div v-if="loading" class="py-6 text-center text-xs app-muted">加载中…</div>

    <el-empty v-else-if="!keys.length" description="还没有配置密钥" :image-size="60" />

    <ul v-else class="space-y-2">
      <li
        v-for="row in keys"
        :key="row.id"
        class="rounded-lg border app-border px-3 py-2"
      >
        <div class="flex flex-wrap items-center gap-2">
          <div class="min-w-0 flex-1">
            <p class="flex items-center gap-2 text-sm app-text">
              <span class="truncate">{{ row.label || row.providerLabel }}</span>
              <el-tag v-if="row.isActive" size="small" type="success">生效中</el-tag>
              <el-tag v-if="!row.enabled" size="small" type="info">已停用</el-tag>
            </p>
            <p class="mt-0.5 truncate text-[11px] app-muted">
              {{ row.providerLabel }} ·
              <code class="font-mono">{{ row.masked || '（无）' }}</code>
              <template v-if="row.model"> · {{ row.model }}</template>
              <template v-if="row.baseUrl"> · {{ row.baseUrl }}</template>
            </p>
            <p class="mt-0.5 text-[11px] app-muted">
              能力：{{ (row.capabilities || []).map((c) => capabilityLabels[c] || c).join(' / ') }}
            </p>
          </div>
          <el-switch
            :model-value="row.enabled"
            size="small"
            @update:model-value="(value) => toggleEnabled(row, value)"
          />
          <el-button size="small" text @click="openEdit(row)">编辑</el-button>
          <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
        </div>
      </li>
    </ul>

    <!-- 新增/编辑 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑密钥' : '添加密钥'"
      width="540px"
    >
      <el-form label-width="88px">
        <el-form-item label="供应商">
          <el-select
            v-model="form.provider"
            :disabled="Boolean(editing)"
            class="w-full"
            @change="onProviderChange"
          >
            <el-option
              v-for="item in providers"
              :key="item.id"
              :label="item.label"
              :value="item.id"
            >
              <span>{{ item.label }}</span>
              <span class="ml-2 text-xs app-muted">
                {{ (item.capabilities || []).map((c) => capabilityLabels[c] || c).join('/') }}
              </span>
            </el-option>
          </el-select>
          <p v-if="currentProvider" class="mt-1 text-[11px] app-muted">
            {{ currentProvider.keyHint }}
            <a
              v-if="currentProvider.applyUrl"
              :href="currentProvider.applyUrl"
              target="_blank"
              rel="noopener"
              class="ml-1 text-brand"
            >
              去申请
            </a>
          </p>
        </el-form-item>

        <el-form-item :label="editing ? '新密钥' : '密钥'">
          <el-input
            v-model="form.secret"
            type="password"
            show-password
            :placeholder="editing ? '留空表示不修改' : keyPlaceholder"
          />
          <p class="mt-1 text-[11px] app-muted">
            密钥会加密后存储，保存后<strong>无法再查看明文</strong>，只能重新填写。
          </p>
        </el-form-item>

        <el-form-item label="备注名">
          <el-input v-model="form.label" maxlength="64" placeholder="选填，便于区分" />
        </el-form-item>

        <el-form-item label="模型">
          <el-input
            v-model="form.model"
            :placeholder="currentProvider?.defaultChatModel || currentProvider?.defaultEmbeddingModel || '选填'"
          />
        </el-form-item>

        <el-form-item label="Base URL">
          <el-input v-model="form.baseUrl" :placeholder="currentProvider?.defaultBaseUrl || '选填'" />
          <p class="mt-1 text-[11px] app-muted">
            留空使用该供应商的官方地址；自建服务（Ollama / vLLM / One-API）请填写完整地址。
          </p>
        </el-form-item>

        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
