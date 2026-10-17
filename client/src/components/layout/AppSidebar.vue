<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatDotRound,
  Close,
  Delete,
  Edit,
  Loading,
  Moon,
  More,
  Plus,
  RefreshLeft,
  Search,
  Setting,
  Sunny,
  SwitchButton,
  UserFilled,
  User,
} from '@element-plus/icons-vue'

import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useUserStore } from '@/stores/user'
import { useTheme } from '@/composables/useTheme'
import { groupByDate } from '@/utils/format'
import { APP_TITLE, isMockMode } from '@/config'
import { resetMockDb } from '@/api/mock'

const emit = defineEmits(['navigate'])

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const knowledgeStore = useKnowledgeStore()
const userStore = useUserStore()
const { isDark, toggleTheme } = useTheme()

const keyword = ref('')

const filteredConversations = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return chatStore.conversations
  return chatStore.conversations.filter((item) => (item.title || '').toLowerCase().includes(key))
})

const groups = computed(() => groupByDate(filteredConversations.value))

const activeId = computed(() => route.params.id || null)

const knowledgeCount = computed(() => knowledgeStore.bases.length)

function go(path) {
  emit('navigate')
  if (route.path !== path) router.push(path)
}

function openConversation(id) {
  emit('navigate')
  if (activeId.value === id) return
  router.push({ name: 'chat', params: { id } })
}

function handleNewChat() {
  emit('navigate')
  // 路由跳转由 store 统一处理（/chat -> /chat-new）
  chatStore.startNewConversation()
}

async function handleRename(conversation) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名会话', {
      inputValue: conversation.title,
      inputPlaceholder: '会话名称',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValidator: (text) => (text && text.trim() ? true : '名称不能为空'),
    })
    await chatStore.renameConversation(conversation.id, value.trim())
  } catch {
    /* 用户取消 */
  }
}

async function handleDelete(conversation) {
  try {
    await ElMessageBox.confirm(`确定删除会话「${conversation.title}」吗？删除后不可恢复。`, '删除会话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger',
    })
  } catch {
    return
  }
  await chatStore.removeConversation(conversation.id)
  ElMessage.success('已删除')
}

async function handleCommand(command) {
  if (command === 'settings') {
    go('/app/settings')
    return
  }
  if (command === 'knowledge') {
    go('/app/knowledge')
    return
  }
  if (command === 'theme') {
    toggleTheme()
    return
  }
  if (command === 'reset-mock') {
    try {
      await ElMessageBox.confirm('将清空所有演示数据（会话、知识库、文档）并恢复初始状态。', '重置演示数据', {
        type: 'warning',
        confirmButtonText: '重置',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
    resetMockDb()
    ElMessage.success('演示数据已重置，即将刷新页面')
    setTimeout(() => window.location.reload(), 600)
    return
  }
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出登录吗？', '退出登录', {
        confirmButtonText: '退出',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
    await userStore.logout()
    chatStore.reset()
    knowledgeStore.reset()
    router.replace({ name: 'login' })
  }
}
</script>

<template>
  <div class="flex h-full flex-col app-sidebar-bg">
    <!-- 品牌区 -->
    <div class="flex items-center gap-2 px-3 pb-1 pt-3">
      <button
        class="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left transition app-hover"
        @click="go('/app/chat')"
      >
        <span
          class="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-light to-brand text-[13px] font-bold text-white"
        >
          R
        </span>
        <span class="truncate text-sm font-semibold app-text">
          {{ APP_TITLE }}
        </span>
        <span
          v-if="isMockMode"
          class="ml-1 shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium leading-none text-amber-700 dark:bg-amber-500/20 dark:text-amber-300"
        >
          MOCK
        </span>
      </button>

      <button
        class="grid h-8 w-8 shrink-0 place-items-center rounded-lg app-muted transition app-hover hover-app-text md:hidden"
        title="收起"
        @click="emit('navigate')"
      >
        <el-icon><Close /></el-icon>
      </button>
    </div>

    <!-- 新建对话 -->
    <div class="px-3 pb-2 pt-1">
      <button
        class="tech-button flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium"
        @click="handleNewChat"
      >
        <el-icon class="text-base"><Plus /></el-icon>
        <span>新建对话</span>
      </button>
    </div>

    <!-- 搜索 -->
    <div class="px-3 pb-1">
      <el-input
        v-model="keyword"
        size="default"
        placeholder="搜索对话"
        clearable
        :prefix-icon="Search"
      />
    </div>

    <!-- 会话列表 -->
    <nav class="scrollbar-thin mt-1 flex-1 overflow-y-auto px-2 pb-3">
      <template v-for="group in groups" :key="group.label">
        <p class="select-none px-2 pb-1 pt-3 text-xs font-medium app-muted">
          {{ group.label }}
        </p>
        <div
          v-for="conversation in group.items"
          :key="conversation.id"
          class="group relative flex items-center rounded-lg transition"
          :class="
            activeId === conversation.id
              ? 'app-active'
              : 'app-hover'
          "
        >
          <button
            class="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm app-text"
            :title="conversation.title"
            @click="openConversation(conversation.id)"
          >
            {{ conversation.title || '新的对话' }}
          </button>

          <div
            class="mr-1 flex shrink-0 items-center opacity-100 transition md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100"
          >
            <button
              class="grid h-7 w-7 place-items-center rounded-md app-muted transition app-hover hover-app-text"
              title="重命名"
              @click.stop="handleRename(conversation)"
            >
              <el-icon :size="14"><Edit /></el-icon>
            </button>
            <button
              class="grid h-7 w-7 place-items-center rounded-md app-muted transition app-hover hover:text-red-500"
              title="删除"
              @click.stop="handleDelete(conversation)"
            >
              <el-icon :size="14"><Delete /></el-icon>
            </button>
          </div>
        </div>
      </template>

      <div
        v-if="chatStore.conversationsLoading"
        class="flex items-center justify-center gap-2 py-6 text-xs app-muted"
      >
        <el-icon class="animate-spin"><Loading /></el-icon>
        加载中…
      </div>

      <p
        v-else-if="!groups.length"
        class="px-3 py-6 text-center text-xs leading-5 app-muted"
      >
        {{ keyword ? '没有匹配的会话' : '还没有对话，点上方「新建对话」开始提问吧' }}
      </p>
    </nav>

    <!-- 底部功能区 -->
    <div class="border-t app-border px-2 py-2">
      <button
        class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm app-text transition app-hover"
        :class="{ 'app-active': route.path.startsWith('/app/knowledge') }"
        @click="go('/app/knowledge')"
      >
        <el-icon class="text-base"><Setting /></el-icon>
        <span class="flex-1 text-left">知识库管理</span>
        <span v-if="knowledgeCount" class="text-xs app-muted">{{ knowledgeCount }}</span>
      </button>

      <button
        class="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm app-text transition app-hover"
        :class="{ 'app-active': route.path.startsWith('/app/teams') }"
        @click="go('/app/teams')"
      >
        <el-icon class="text-base"><User /></el-icon>
        <span class="flex-1 text-left">团队</span>
      </button>

      <el-dropdown trigger="click" placement="top-start" class="mt-1 w-full" @command="handleCommand">
        <button
          class="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition app-hover"
        >
          <span
            class="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-light to-brand text-xs font-semibold text-white"
          >
            {{ userStore.avatarText }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm app-text">
              {{ userStore.displayName }}
            </span>
            <span class="block truncate text-[11px] app-muted">
              {{ userStore.profile?.email || '已登录' }}
            </span>
          </span>
          <el-icon class="app-muted"><More /></el-icon>
        </button>

        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="settings">
              <el-icon><UserFilled /></el-icon>
              账号设置
            </el-dropdown-item>
            <el-dropdown-item command="knowledge">
              <el-icon><ChatDotRound /></el-icon>
              知识库管理
            </el-dropdown-item>
            <el-dropdown-item command="theme">
              <el-icon><Moon v-if="!isDark" /><Sunny v-else /></el-icon>
              {{ isDark ? '切换为浅色' : '切换为深色' }}
            </el-dropdown-item>
            <el-dropdown-item v-if="isMockMode" command="reset-mock" divided>
              <el-icon><RefreshLeft /></el-icon>
              重置演示数据
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon>
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>
