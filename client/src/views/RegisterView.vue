<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, Message, User } from '@element-plus/icons-vue'

import AuthShell from '@/layouts/AuthShell.vue'
import PasswordStrength from '@/components/auth/PasswordStrength.vue'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'
import { usePolicyDialog } from '@/composables/usePolicyDialog'
import { APP_TITLE } from '@/config'
import { notifyError } from '@/utils/notify'

const router = useRouter()
const userStore = useUserStore()
const chatStore = useChatStore()
const { openPolicy } = usePolicyDialog()

const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  agreed: true,
})

const submitLabel = computed(() => (loading.value ? '正在创建…' : '创建账号'))

function validateConfirm(_rule, value, callback) {
  if (!value) callback(new Error('请再次输入密码'))
  else if (value !== form.password) callback(new Error('两次输入的密码不一致'))
  else callback()
}

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 32, message: '用户名长度为 2~32 个字符', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_\u4e00-\u9fa5-]+$/,
      message: '只能包含字母、数字、下划线、连字符或中文',
      trigger: 'blur',
    },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度为 6~64 位', trigger: 'blur' },
  ],
  confirmPassword: [{ required: true, validator: validateConfirm, trigger: 'blur' }],
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  if (!form.agreed) {
    ElMessage.warning('请先阅读并同意《服务协议》与《隐私政策》')
    return
  }

  loading.value = true
  try {
    await userStore.register({
      username: form.username.trim(),
      email: form.email.trim(),
      password: form.password,
    })
    chatStore.reset()
    ElMessage.success('注册成功，已自动登录')
    router.replace({ name: 'chat-new' })
  } catch (error) {
    notifyError(error, '注册失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthShell mode="register">
    <h2 class="text-[22px] font-semibold tracking-tight app-text">
      创建账号
    </h2>
    <p class="mt-1.5 text-[13px] app-muted">
      注册后即可创建知识库、上传文档并开始智能问答
    </p>

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
          placeholder="2~32 个字符，支持中文"
          :prefix-icon="User"
          autocomplete="username"
        />
      </el-form-item>

      <el-form-item label="邮箱" prop="email">
        <el-input
          v-model="form.email"
          size="large"
          placeholder="you@example.com"
          :prefix-icon="Message"
          autocomplete="email"
        />
      </el-form-item>

      <el-form-item label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          size="large"
          placeholder="至少 6 位，建议 8 位以上"
          :prefix-icon="Lock"
          show-password
          autocomplete="new-password"
        />
        <PasswordStrength
          v-if="form.password"
          :password="form.password"
          :username="form.username"
          class="mt-2"
        />
      </el-form-item>

      <el-form-item label="确认密码" prop="confirmPassword">
        <el-input
          v-model="form.confirmPassword"
          type="password"
          size="large"
          placeholder="再次输入密码"
          :prefix-icon="Lock"
          show-password
          autocomplete="new-password"
          @keyup.enter="handleSubmit"
        />
      </el-form-item>

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

    <template #below>
      <p class="px-1 text-center text-[11px] leading-5 app-faint">
        {{ APP_TITLE }} 支持私有化部署，你的文档不会被用于训练对外公开的模型
      </p>
    </template>
  </AuthShell>
</template>
