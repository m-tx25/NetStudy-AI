<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'

import AuthShell from '@/layouts/AuthShell.vue'
import ForgotPasswordDialog from '@/components/auth/ForgotPasswordDialog.vue'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'
import { usePolicyDialog } from '@/composables/usePolicyDialog'
import { APP_TITLE, isMockMode } from '@/config'
import { notifyError } from '@/utils/notify'

const REMEMBER_KEY = 'rag.remembered_username'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const chatStore = useChatStore()
const { openPolicy } = usePolicyDialog()

const formRef = ref(null)
const loading = ref(false)
const demoLoading = ref(false)
const forgotVisible = ref(false)

function readRemembered() {
  try {
    return localStorage.getItem(REMEMBER_KEY) || ''
  } catch {
    return ''
  }
}

const remembered = readRemembered()

const form = reactive({
  username: remembered || (isMockMode ? 'demo' : ''),
  password: isMockMode && !remembered ? '123456' : '',
  remember: Boolean(remembered),
  agreed: true,
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 32, message: '用户名长度为 2~32 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

const submitLabel = computed(() => (loading.value ? '正在登录…' : '登 录'))

function rememberUsername(username) {
  try {
    if (form.remember) localStorage.setItem(REMEMBER_KEY, username)
    else localStorage.removeItem(REMEMBER_KEY)
  } catch {
    /* ignore */
  }
}

function redirectAfterLogin() {
  const target = route.query.redirect
  if (typeof target === 'string' && target.startsWith('/')) router.replace(target)
  else router.replace({ name: 'chat-new' })
}

function ensureAgreed() {
  if (form.agreed) return true
  ElMessage.warning('请先阅读并同意《服务协议》与《隐私政策》')
  return false
}

async function doLogin(payload, { loadingRef } = {}) {
  loadingRef.value = true
  try {
    await userStore.login(payload)
    chatStore.reset()
    return true
  } catch (error) {
    notifyError(error, '登录失败，请检查用户名与密码')
    return false
  } finally {
    loadingRef.value = false
  }
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!ensureAgreed()) return

  const username = form.username.trim()
  const ok = await doLogin({ username, password: form.password }, { loadingRef: loading })
  if (!ok) return

  rememberUsername(username)
  ElMessage.success(`欢迎回来，${userStore.displayName}`)
  redirectAfterLogin()
}

/** Mock 模式下的一键体验：用预置演示账号登录，方便评审快速看到完整功能 */
async function handleDemoLogin() {
  if (!ensureAgreed()) return
  form.username = 'demo'
  form.password = '123456'
  const ok = await doLogin({ username: 'demo', password: '123456' }, { loadingRef: demoLoading })
  if (!ok) return
  rememberUsername('demo')
  ElMessage.success('已使用演示账号登录')
  redirectAfterLogin()
}

onMounted(() => {
  if (route.query.registered) ElMessage.success('注册成功，请使用新账号登录')
  if (route.query.passwordChanged) ElMessage.success('密码已更新，请使用新密码登录')
})
</script>

<template>
  <AuthShell mode="login">
    <h2 class="text-[22px] font-semibold tracking-tight app-text">
      登录
    </h2>
    <p class="mt-1.5 text-[13px] app-muted">使用你的 {{ APP_TITLE }} 账号继续</p>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      class="mt-6"
      @submit.prevent="handleSubmit"
    >
      <el-form-item label="用户名" prop="username">
        <el-input
          v-model="form.username"
          size="large"
          placeholder="请输入用户名"
          :prefix-icon="User"
          autocomplete="username"
        />
      </el-form-item>

      <el-form-item label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          size="large"
          placeholder="请输入密码"
          :prefix-icon="Lock"
          show-password
          autocomplete="current-password"
          @keyup.enter="handleSubmit"
        />
      </el-form-item>

      <div class="-mt-1 mb-4 flex items-center justify-between">
        <el-checkbox v-model="form.remember">记住账号</el-checkbox>
        <button
          type="button"
          class="text-[13px] app-accent underline-offset-2 transition hover:underline"
          @click="forgotVisible = true"
        >
          忘记密码？
        </button>
      </div>

      <el-checkbox v-model="form.agreed" class="!mb-4 !h-auto !items-start !whitespace-normal">
        <span class="text-[12px] leading-5 app-muted">
          我已阅读并同意
          <button type="button" class="app-accent hover:underline" @click.stop="openPolicy('terms')">
            《服务协议》
          </button>
          与
          <button type="button" class="app-accent hover:underline" @click.stop="openPolicy('privacy')">
            《隐私政策》
          </button>
        </span>
      </el-checkbox>

      <el-button
        type="primary"
        size="large"
        class="w-full !h-11 !rounded-xl !text-[15px] !font-medium"
        :loading="loading"
        @click="handleSubmit"
      >
        {{ submitLabel }}
      </el-button>
    </el-form>

    <el-divider class="!my-5">
      <span class="text-[11px] font-normal text-[#a8a8a8]">其他方式</span>
    </el-divider>

    <el-button
      v-if="isMockMode"
      size="large"
      class="w-full !h-11 !rounded-xl"
      :loading="demoLoading"
      @click="handleDemoLogin"
    >
      一键体验演示账号
    </el-button>
    <el-button
      v-else
      size="large"
      class="w-full !h-11 !rounded-xl"
      @click="router.push({ name: 'register' })"
    >
      创建新账号
    </el-button>

    <template #below>
      <div
        v-if="isMockMode"
        class="rounded-xl border border-amber-200/70 bg-amber-50/70 px-3.5 py-2.5 text-[11px] leading-5 text-amber-700 dark:border-amber-500/25 dark:bg-amber-500/10 dark:text-amber-300"
      >
        <span class="font-medium">演示模式</span>
        ：已预填 <code>demo / 123456</code>；也可用任意用户名 + 6 位以上密码登录。
      </div>

      <p v-else class="px-1 text-center text-[11px] leading-5 app-faint">
        登录即表示你同意我们按照《隐私政策》处理你的账号信息
      </p>
    </template>
  </AuthShell>

  <ForgotPasswordDialog v-model="forgotVisible" />
</template>
