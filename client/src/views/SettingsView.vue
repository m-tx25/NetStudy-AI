<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Expand, Key, Lock, Message, User, UserFilled } from '@element-plus/icons-vue'

import PasswordStrength from '@/components/auth/PasswordStrength.vue'
import ApiKeyManager from '@/components/keys/ApiKeyManager.vue'
import { useUserStore } from '@/stores/user'
import { useChatStore } from '@/stores/chat'
import { useSidebar } from '@/composables/useSidebar'
import { formatDateTime } from '@/utils/format'
import { notifyError } from '@/utils/notify'

const router = useRouter()
const userStore = useUserStore()
const chatStore = useChatStore()
const { openMobileSidebar } = useSidebar()

/* ------------------------------------------------------------------ *
 * 账号资料
 * ------------------------------------------------------------------ */
const profileFormRef = ref(null)
const passwordFormRef = ref(null)

const profileForm = reactive({
  nickname: '',
  username: '',
  email: '',
})

const originalUsername = ref('')

const passwordForm = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
})

function syncProfileForm() {
  profileForm.nickname = userStore.profile?.nickname || ''
  profileForm.username = userStore.profile?.username || ''
  profileForm.email = userStore.profile?.email || ''
  originalUsername.value = profileForm.username
}

onMounted(() => {
  if (!userStore.profile) userStore.loadProfile().then(syncProfileForm)
  else syncProfileForm()
})

const usernameChanged = computed(
  () => profileForm.username.trim() !== '' && profileForm.username.trim() !== originalUsername.value,
)

const profileDirty = computed(
  () =>
    profileForm.nickname !== (userStore.profile?.nickname || '') ||
    profileForm.username !== (userStore.profile?.username || '') ||
    profileForm.email !== (userStore.profile?.email || ''),
)

const previewName = computed(() => profileForm.nickname.trim() || profileForm.username.trim() || '未命名')
const previewInitial = computed(() => previewName.value.slice(0, 1).toUpperCase())

const profileRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 32, message: '用户名长度为 2~32 个字符', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_\u4e00-\u9fa5-]+$/,
      message: '只能包含字母、数字、下划线、连字符或中文',
      trigger: 'blur',
    },
  ],
  nickname: [{ max: 32, message: '昵称不能超过 32 个字符', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

const accountInfo = computed(() => {
  const profile = userStore.profile || {}
  return [
    { label: '账号 ID', value: profile.id || '-' },
    { label: '角色', value: userStore.roleLabel },
    { label: '注册时间', value: formatDateTime(profile.createdAt) },
    { label: '最近登录', value: formatDateTime(profile.lastLoginAt) },
  ]
})

async function saveProfile() {
  if (!profileFormRef.value) return
  try {
    await profileFormRef.value.validate()
  } catch {
    return
  }

  // 先记下旧用户名，syncProfileForm 会把它覆盖掉
  const previousUsername = originalUsername.value

  try {
    const updated = await userStore.updateProfile({
      nickname: profileForm.nickname.trim(),
      username: profileForm.username.trim(),
      email: profileForm.email.trim(),
    })
    syncProfileForm()
    ElMessage.success(
      updated.username !== previousUsername
        ? `已保存，下次请使用新用户名「${updated.username}」登录`
        : '账号资料已更新',
    )
  } catch (error) {
    notifyError(error, '保存失败，请稍后重试')
  }
}

function resetProfileForm() {
  syncProfileForm()
}

/* ------------------------------------------------------------------ *
 * 修改密码
 * ------------------------------------------------------------------ */
function validateNewPassword(_rule, value, callback) {
  if (!value) callback(new Error('请输入新密码'))
  else if (value.length < 6) callback(new Error('新密码至少 6 位'))
  else if (value === passwordForm.currentPassword) callback(new Error('新密码不能与当前密码相同'))
  else callback()
}

function validateConfirm(_rule, value, callback) {
  if (!value) callback(new Error('请再次输入新密码'))
  else if (value !== passwordForm.newPassword) callback(new Error('两次输入的新密码不一致'))
  else callback()
}

const passwordRules = {
  currentPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [{ required: true, validator: validateNewPassword, trigger: 'blur' }],
  confirmPassword: [{ required: true, validator: validateConfirm, trigger: 'blur' }],
}

async function savePassword() {
  if (!passwordFormRef.value) return
  try {
    await passwordFormRef.value.validate()
  } catch {
    return
  }

  try {
    await userStore.changePassword({
      currentPassword: passwordForm.currentPassword,
      newPassword: passwordForm.newPassword,
    })
  } catch (error) {
    notifyError(error, '修改密码失败')
    return
  }

  passwordFormRef.value.resetFields()
  passwordForm.currentPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''

  try {
    await ElMessageBox.confirm(
      '密码已修改。为保证账号安全，建议立即使用新密码重新登录，其他设备上的登录状态也应失效。',
      '密码修改成功',
      {
        type: 'success',
        confirmButtonText: '立即重新登录',
        cancelButtonText: '稍后再说',
        closeOnClickModal: false,
      },
    )
  } catch {
    ElMessage.success('密码已更新')
    return
  }

  // 重新登录：清掉本地登录态，回到登录页
  try {
    await userStore.logout()
  } catch {
    userStore.forceRelogin()
  }
  chatStore.reset()
  router.replace({ name: 'login', query: { passwordChanged: '1' } })
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col app-canvas">
    <!-- 顶部栏 -->
    <header
      class="flex h-14 shrink-0 items-center gap-2 border-b app-border px-3 md:px-5"
    >
      <button
        class="grid h-9 w-9 shrink-0 place-items-center rounded-lg app-muted transition app-hover hover-app-text md:hidden"
        title="打开侧边栏"
        @click="openMobileSidebar"
      >
        <el-icon><Expand /></el-icon>
      </button>

      <div class="min-w-0 flex-1">
        <h1 class="truncate text-sm font-semibold app-text">账号设置</h1>
        <p class="truncate text-[11px] app-muted">
          管理你的账号资料与登录密码
        </p>
      </div>
    </header>

    <div class="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto w-full max-w-3xl px-4 py-6 md:px-6 md:py-8">
        <!-- 账号概览 -->
        <section
          class="flex flex-wrap items-center gap-4 rounded-2xl border app-border app-panel p-5"
        >
          <span
            class="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand-light to-brand text-xl font-semibold text-white shadow-lg shadow-brand/25"
          >
            {{ previewInitial }}
          </span>
          <div class="min-w-0 flex-1">
            <p class="flex items-center gap-2">
              <span class="truncate text-base font-semibold app-text">
                {{ previewName }}
              </span>
              <span
                class="shrink-0 rounded-full app-accent-soft px-2 py-0.5 text-[11px] font-medium"
              >
                {{ userStore.roleLabel }}
              </span>
            </p>
            <p class="mt-0.5 truncate text-xs app-muted">
              {{ userStore.username }} · {{ userStore.email }}
            </p>
          </div>
          <p class="text-[11px] app-faint">
            侧边栏显示「{{ previewName }}」
          </p>
        </section>

        <!-- 账号资料 -->
        <section class="mt-6 rounded-2xl border app-border p-5 md:p-6">
          <div class="flex items-center gap-2">
            <el-icon class="text-base app-accent"><UserFilled /></el-icon>
            <h2 class="text-[15px] font-semibold app-text">账号资料</h2>
          </div>
          <p class="mt-1 text-xs leading-5 app-muted">
            用户名是你的登录账号，修改后需要用新的用户名登录；昵称只影响界面展示。
          </p>

          <el-form
            ref="profileFormRef"
            :model="profileForm"
            :rules="profileRules"
            label-position="top"
            class="mt-5"
            @submit.prevent="saveProfile"
          >
            <div class="grid gap-x-5 sm:grid-cols-2">
              <el-form-item label="昵称" prop="nickname">
                <el-input
                  v-model="profileForm.nickname"
                  size="large"
                  placeholder="用于界面展示，例如「张工」"
                  :prefix-icon="UserFilled"
                  maxlength="32"
                />
              </el-form-item>

              <el-form-item label="用户名（登录账号）" prop="username">
                <el-input
                  v-model="profileForm.username"
                  size="large"
                  placeholder="2~32 个字符"
                  :prefix-icon="User"
                  autocomplete="username"
                />
              </el-form-item>
            </div>

            <el-form-item label="邮箱" prop="email">
              <el-input
                v-model="profileForm.email"
                size="large"
                placeholder="you@example.com"
                :prefix-icon="Message"
                autocomplete="email"
              />
            </el-form-item>

            <div
              v-if="usernameChanged"
              class="mb-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-[12px] leading-5 text-amber-700 dark:border-amber-500/25 dark:bg-amber-500/10 dark:text-amber-300"
            >
              <el-icon class="mt-0.5 shrink-0"><Key /></el-icon>
              <span>
                登录账号将从 <strong>{{ originalUsername }}</strong> 变更为
                <strong>{{ profileForm.username.trim() }}</strong>，密码保持不变。
                保存后请使用新用户名登录。
              </span>
            </div>

            <div class="flex items-center gap-3">
              <el-button
                type="primary"
                :loading="userStore.savingProfile"
                :disabled="!profileDirty"
                @click="saveProfile"
              >
                保存修改
              </el-button>
              <el-button :disabled="!profileDirty" @click="resetProfileForm">重置</el-button>
            </div>
          </el-form>

          <!-- 只读的账号信息 -->
          <div class="mt-6 grid gap-x-6 gap-y-3 border-t app-border pt-5 sm:grid-cols-2">
            <div v-for="item in accountInfo" :key="item.label" class="flex items-center justify-between gap-3">
              <span class="text-xs app-faint">{{ item.label }}</span>
              <span class="truncate text-xs app-text-secondary">{{ item.value }}</span>
            </div>
          </div>
        </section>

        <!-- API 密钥（个人级） -->
        <section class="mt-6 rounded-2xl border app-border p-5 md:p-6">
          <div class="flex items-center gap-2">
            <el-icon class="text-base app-accent"><Key /></el-icon>
            <h2 class="text-[15px] font-semibold app-text">API 密钥</h2>
          </div>
          <p class="mt-1 mb-4 text-xs leading-5 app-muted">
            配置你自己的大模型 / 向量化密钥，作用于<strong>个人知识库</strong>。
            团队知识库请在「团队 → 团队设置」里配置团队密钥（费用归团队）。
            密钥加密存储，保存后无法查看明文。
          </p>
          <ApiKeyManager scope="user" />
        </section>

        <!-- 修改密码 -->
        <section class="mt-6 rounded-2xl border app-border p-5 md:p-6">
          <div class="flex items-center gap-2">
            <el-icon class="text-base app-accent"><Lock /></el-icon>
            <h2 class="text-[15px] font-semibold app-text">修改密码</h2>
          </div>
          <p class="mt-1 text-xs leading-5 app-muted">
            修改成功后建议重新登录。请勿使用与其他网站相同的密码。
          </p>

          <el-form
            ref="passwordFormRef"
            :model="passwordForm"
            :rules="passwordRules"
            label-position="top"
            class="mt-5 max-w-md"
            @submit.prevent="savePassword"
          >
            <el-form-item label="当前密码" prop="currentPassword">
              <el-input
                v-model="passwordForm.currentPassword"
                type="password"
                size="large"
                placeholder="请输入当前使用的密码"
                :prefix-icon="Lock"
                show-password
                autocomplete="current-password"
              />
            </el-form-item>

            <el-form-item label="新密码" prop="newPassword">
              <el-input
                v-model="passwordForm.newPassword"
                type="password"
                size="large"
                placeholder="至少 6 位，建议 8 位以上"
                :prefix-icon="Key"
                show-password
                autocomplete="new-password"
              />
              <PasswordStrength
                v-if="passwordForm.newPassword"
                :password="passwordForm.newPassword"
                :username="profileForm.username"
                class="mt-2"
              />
            </el-form-item>

            <el-form-item label="确认新密码" prop="confirmPassword">
              <el-input
                v-model="passwordForm.confirmPassword"
                type="password"
                size="large"
                placeholder="再次输入新密码"
                :prefix-icon="Key"
                show-password
                autocomplete="new-password"
                @keyup.enter="savePassword"
              />
            </el-form-item>

            <el-button type="primary" :loading="userStore.changingPassword" @click="savePassword">
              确认修改密码
            </el-button>
          </el-form>
        </section>
      </div>
    </div>
  </div>
</template>
