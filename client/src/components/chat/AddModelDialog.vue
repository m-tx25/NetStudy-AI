<script setup>
/**
 * 添加 / 编辑模型对话框（BYOM：Bring Your Own Model）。
 *
 * 两条路径：
 *   1. 本地部署 —— 选预设（Ollama / vLLM / LM Studio）或手填地址，通常无需真实密钥；
 *   2. 云端 API —— 填服务商地址 + 模型名 + 自己的 API Key。
 *
 * 密钥说明：提交后由后端**加密存储**，不会再回显到界面。
 * 因此编辑时密钥留空 = 沿用原密钥，不会被清空。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Connection, InfoFilled } from '@element-plus/icons-vue'

import { useChatStore } from '@/stores/chat'

const visible = defineModel({ type: Boolean, default: false })

const props = defineProps({
  /** 传入表示编辑，为空表示新增 */
  model: { type: Object, default: null },
})

const emit = defineEmits(['saved'])

const chatStore = useChatStore()

const formRef = ref(null)
const submitting = ref(false)
const probing = ref(false)
const probeResult = ref(null)

const isEdit = computed(() => Boolean(props.model?.id))

const form = reactive({
  label: '',
  baseUrl: '',
  apiKey: '',
  model: '',
  isLocal: true,
  temperature: 0.3,
})

const rules = {
  label: [{ required: true, message: '请填写显示名称，例如「本地 Qwen」', trigger: 'blur' }],
  baseUrl: [
    { required: true, message: '请填写接口地址', trigger: 'blur' },
    {
      pattern: /^https?:\/\/.+/,
      message: '地址需以 http:// 或 https:// 开头',
      trigger: 'blur',
    },
  ],
  model: [{ required: true, message: '请填写模型名，例如 qwen2.5:7b', trigger: 'blur' }],
}

const presets = computed(() => chatStore.modelPresets || [])

function resetForm() {
  const source = props.model
  form.label = source?.label || ''
  form.baseUrl = source?.baseUrl || ''
  form.apiKey = ''
  form.model = source?.model || ''
  form.isLocal = source ? source.isLocal !== false : true
  form.temperature = typeof source?.temperature === 'number' ? source.temperature : 0.3
  probeResult.value = null
}

watch(visible, (open) => {
  if (open) resetForm()
})

watch(
  () => props.model,
  () => {
    if (visible.value) resetForm()
  },
)

/** 一键填入本地预设，省去记端口 */
function applyPreset(preset) {
  form.label = form.label || preset.label
  form.baseUrl = preset.baseUrl
  form.model = preset.model
  form.isLocal = true
  if (!form.apiKey) {
    // 本地服务一般不校验密钥，但后端要求非空才视为「已配置」
    form.apiKey = 'local'
  }
  probeResult.value = null
}

async function validate() {
  if (!formRef.value) return true
  try {
    await formRef.value.validate()
    return true
  } catch {
    return false
  }
}

function buildPayload() {
  const payload = {
    label: form.label.trim(),
    baseUrl: form.baseUrl.trim(),
    model: form.model.trim(),
    isLocal: form.isLocal,
    temperature: Number(form.temperature),
  }
  // 新增时必须带密钥；编辑时留空表示沿用原密钥
  if (!isEdit.value || form.apiKey.trim()) {
    payload.apiKey = form.apiKey.trim() || (form.isLocal ? 'local' : '')
  }
  return payload
}

/** 保存后立刻探测一次：本地服务没启动是最常见的失败原因 */
async function submit() {
  if (!(await validate())) return
  submitting.value = true
  try {
    const payload = buildPayload()
    const saved = isEdit.value
      ? await chatStore.editModel(props.model.id, payload)
      : await chatStore.addModel(payload)

    ElMessage.success(isEdit.value ? '模型已更新' : '模型已添加')
    emit('saved', saved)

    // 顺手做一次连通性探测，把问题当场暴露出来
    if (saved?.id) {
      probeResult.value = { pending: true }
      const result = await chatStore.checkModel(saved.id)
      probeResult.value = result
      if (result?.ok) ElMessage.success('连接测试通过，可以开始提问了')
      else ElMessage.warning(`连接测试未通过：${String(result?.reason || '').slice(0, 80)}`)
    }
  } catch (error) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    submitting.value = false
  }
}

async function testConnection() {
  if (!(await validate())) return
  probing.value = true
  probeResult.value = null
  try {
    // 先保存再探测（探测用的是服务端已存的配置，避免前端持有密钥明文多次传输）
    const payload = buildPayload()
    const saved = isEdit.value
      ? await chatStore.editModel(props.model.id, payload)
      : await chatStore.addModel(payload)
    const result = await chatStore.checkModel(saved.id)
    probeResult.value = result
    if (result?.ok) ElMessage.success('连接测试通过')
    else ElMessage.warning(`连接失败：${String(result?.reason || '').slice(0, 80)}`)
  } catch (error) {
    ElMessage.error(error?.message || '连接测试失败')
  } finally {
    probing.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑模型' : '添加模型'"
    width="560px"
    :close-on-click-modal="false"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <!-- 本地预设：一键填入，省去记端口 -->
      <div v-if="!isEdit && presets.length" class="mb-4">
        <p class="mb-2 text-xs app-muted">本地部署可一键填入：</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="preset in presets"
            :key="preset.id"
            type="button"
            class="rounded-lg border app-border px-3 py-1.5 text-xs transition app-hover"
            :title="preset.hint"
            @click="applyPreset(preset)"
          >
            {{ preset.label }}
          </button>
        </div>
      </div>

      <el-form-item label="显示名称" prop="label">
        <el-input v-model="form.label" placeholder="例如：本地 Qwen / 我的 DeepSeek" maxlength="64" />
      </el-form-item>

      <el-form-item label="部署方式">
        <el-radio-group v-model="form.isLocal">
          <el-radio :value="true">本地部署</el-radio>
          <el-radio :value="false">云端 API</el-radio>
        </el-radio-group>
        <p class="mt-1 text-[11px] app-muted">
          {{
            form.isLocal
              ? '本地服务（Ollama / vLLM / LM Studio）通常不校验密钥，留空会自动填 local'
              : '云端服务需要填写你自己的 API Key，提交后由后端加密保存，不会再回显'
          }}
        </p>
      </el-form-item>

      <el-form-item label="接口地址（Base URL）" prop="baseUrl">
        <el-input v-model="form.baseUrl" placeholder="http://127.0.0.1:11434/v1 或 https://api.deepseek.com/v1" />
      </el-form-item>

      <el-form-item label="模型名" prop="model">
        <el-input v-model="form.model" placeholder="qwen2.5:7b 或 deepseek-chat" />
      </el-form-item>

      <el-form-item label="API Key">
        <el-input
          v-model="form.apiKey"
          type="password"
          show-password
          :placeholder="
            isEdit
              ? '留空表示不修改已保存的密钥'
              : form.isLocal
                ? '本地服务通常不需要，留空会自动填 local'
                : '只填密钥本身，形如 sk-xxxxxxxxxxxxxxxx'
          "
        />
        <p class="mt-1 text-[11px] leading-5 app-muted">
          <template v-if="isEdit && model?.hasApiKey">
            已保存密钥，留空即可沿用。
          </template>
          <template v-else>
            只粘贴服务商给你的那串密钥，<strong>不要</strong>连带说明文字、空格或换行；
            密钥里不该出现中文。
          </template>
        </p>
      </el-form-item>

      <el-form-item label="Temperature（可选）">
        <el-slider v-model="form.temperature" :min="0" :max="2" :step="0.1" show-input size="small" />
      </el-form-item>

      <!-- 连通性测试结果 -->
      <div
        v-if="probeResult"
        class="rounded-lg border px-3 py-2 text-xs leading-5"
        :class="
          probeResult.pending
            ? 'app-border app-muted'
            : probeResult.ok
              ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300'
              : 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300'
        "
      >
        <template v-if="probeResult.pending">正在测试连接…</template>
        <template v-else-if="probeResult.ok">
          连接测试通过（{{ probeResult.url }}）
        </template>
        <template v-else>
          <p class="font-medium">连接测试未通过</p>
          <p class="mt-0.5">{{ probeResult.reason }}</p>
          <p v-if="probeResult.hint" class="mt-0.5">{{ probeResult.hint }}</p>
        </template>
      </div>

      <p class="mt-3 flex items-start gap-1.5 text-[11px] leading-5 app-muted">
        <el-icon class="mt-0.5 shrink-0"><InfoFilled /></el-icon>
        <span>
          密钥仅保存在你自己的后端（加密存储），不会出现在接口响应里，也不会写到日志。
          当前账号看不到其他用户的模型。
        </span>
      </p>
    </el-form>

    <template #footer>
      <div class="flex items-center justify-between">
        <el-button :loading="probing" :disabled="submitting" @click="testConnection">
          <el-icon class="mr-1"><Connection /></el-icon>
          测试连接
        </el-button>
        <span>
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submit">
            {{ isEdit ? '保存修改' : '添加' }}
          </el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</template>
