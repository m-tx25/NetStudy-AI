<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  Bell,
  Check,
  Close,
  CopyDocument,
  Link,
  Plus,
  Refresh,
  Search,
  Setting,
  UserFilled,
} from '@element-plus/icons-vue'

import AddMemberForm from '@/components/team/AddMemberForm.vue'
import TeamSettingsPanel from '@/components/team/TeamSettingsPanel.vue'
import { useTeamStore } from '@/stores/team'
import { useUserStore } from '@/stores/user'
import { formatDateTime } from '@/utils/format'
import { notifyError, notifySuccess } from '@/utils/notify'

const teamStore = useTeamStore()
const userStore = useUserStore()

const activeTab = ref('mine')
const keyword = ref('')
const createVisible = ref(false)
const inviteVisible = ref(false)
const detailVisible = ref(false)
const detailTab = ref('members')

const createFormRef = ref(null)
const createForm = reactive({
  name: '',
  description: '',
  visibility: 'public',
  joinPolicy: 'approval',
})
const createRules = {
  name: [
    { required: true, message: '请输入团队名称', trigger: 'blur' },
    { min: 1, max: 64, message: '名称长度为 1~64 个字符', trigger: 'blur' },
  ],
}

const inviteForm = reactive({ code: '', message: '' })

const myUserId = computed(() => userStore.profile?.id || userStore.profile?.userId || '')
const activeTeam = computed(() => teamStore.activeTeam)
const members = computed(() => teamStore.members)
const joinRequests = computed(() => teamStore.joinRequests)

const roleLabels = { owner: '负责人', admin: '管理员', member: '成员' }
const roleTagTypes = { owner: 'warning', admin: 'primary', member: 'info' }
const visibilityLabels = { public: '公开', private: '私有' }
const policyLabels = { open: '邀请码直接加入', approval: '需管理员审核', closed: '禁止加入' }

function myRoleIn(team) {
  return team?.myRole || null
}

function canManage(team) {
  return ['owner', 'admin'].includes(myRoleIn(team))
}

async function copyText(text, tip = '已复制') {
  try {
    await navigator.clipboard.writeText(text)
    notifySuccess(tip)
  } catch {
    notifyError(null, '复制失败，请手动选中复制')
  }
}

/* ------------------------------ 创建 ------------------------------ */
function openCreate() {
  Object.assign(createForm, {
    name: '',
    description: '',
    visibility: 'public',
    joinPolicy: 'approval',
  })
  createVisible.value = true
}

async function submitCreate() {
  const form = createFormRef.value
  if (form) {
    const ok = await form.validate().catch(() => false)
    if (!ok) return
  }
  const team = await teamStore.create({ ...createForm })
  if (team) {
    createVisible.value = false
    activeTab.value = 'mine'
    await openDetail(team)
  }
}

/* ------------------------------ 详情 ------------------------------ */
async function openDetail(team) {
  detailTab.value = 'members'
  await teamStore.selectTeam(team.id)
  detailVisible.value = true
}

async function refreshDetail() {
  if (!activeTeam.value) return
  await teamStore.selectTeam(activeTeam.value.id)
}

/* ------------------------------ 成员操作 ------------------------------ */
async function onAddMember(username, role) {
  if (!activeTeam.value) return false
  const result = await teamStore.addMember(activeTeam.value.id, { username, role })
  return Boolean(result)
}

async function onToggleAdmin(member) {
  if (!activeTeam.value) return
  const next = member.role === 'admin' ? 'member' : 'admin'
  await teamStore.changeRole(activeTeam.value.id, member.userId, next)
}

async function onRemoveMember(member) {
  if (!activeTeam.value) return
  const isSelf = member.userId === myUserId.value
  const name = member.user?.nickname || member.user?.username || ''
  try {
    await ElMessageBox.confirm(
      isSelf ? '确定退出该团队吗？' : `确定将「${name}」移出团队吗？`,
      isSelf ? '退出团队' : '移除成员',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  if (isSelf) {
    await teamStore.leaveTeam(activeTeam.value.id, member.userId)
    detailVisible.value = false
  } else {
    await teamStore.removeMember(activeTeam.value.id, member.userId)
    await teamStore.loadTeam(activeTeam.value.id)
  }
}

async function onTransfer(member) {
  if (!activeTeam.value) return
  const name = member.user?.nickname || member.user?.username || ''
  try {
    await ElMessageBox.confirm(
      `确定把负责人转让给「${name}」吗？转让后你将变为管理员。`,
      '转让负责人',
      { type: 'warning', confirmButtonText: '确认转让', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  await teamStore.transfer(activeTeam.value.id, member.userId)
}

/* ------------------------------ 审核 ------------------------------ */
async function onApprove(request, role = 'member') {
  if (!activeTeam.value) return
  await teamStore.approveRequest(activeTeam.value.id, request.id, role)
}

async function onReject(request) {
  if (!activeTeam.value) return
  await teamStore.rejectRequest(activeTeam.value.id, request.id)
}

/* ------------------------------ 加入 ------------------------------ */
async function onApply(team) {
  await teamStore.applyJoin(team.id, '')
}

async function onSearch() {
  await teamStore.searchTeamsByKeyword(keyword.value)
}

async function submitInvite() {
  if (!inviteForm.code.trim()) {
    notifyError(null, '请输入邀请码')
    return
  }
  await teamStore.applyByInviteCode(inviteForm.code.trim(), inviteForm.message)
  inviteVisible.value = false
  Object.assign(inviteForm, { code: '', message: '' })
  activeTab.value = 'mine'
}

/* ------------------------------ 解散 ------------------------------ */
async function onDissolve() {
  if (!activeTeam.value) return
  try {
    await ElMessageBox.confirm(
      '解散后团队知识库、文档与成员关系都会被删除，且无法恢复。确定解散吗？',
      '解散团队',
      { type: 'error', confirmButtonText: '确定解散', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const ok = await teamStore.remove(activeTeam.value.id)
  if (ok) {
    detailVisible.value = false
    notifySuccess('团队已解散')
  }
}

onMounted(async () => {
  await Promise.all([teamStore.loadTeams(), teamStore.loadMyRequests()])
  await onSearch()
})
</script>

<template>
  <div class="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
    <!-- 头部 -->
    <header class="mb-5 flex flex-wrap items-center gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="text-xl font-semibold app-text">团队</h1>
        <p class="mt-1 text-sm app-muted">
          团队知识库全员共享，成员都能上传；负责人与管理员可审批入队、拉人、配置团队密钥。
        </p>
      </div>
      <el-button :icon="Link" @click="inviteVisible = true">邀请码加入</el-button>
      <el-button type="primary" :icon="Plus" @click="openCreate">创建团队</el-button>
    </header>

    <el-tabs v-model="activeTab">
      <!-- ============ 我的团队 ============ -->
      <el-tab-pane label="我的团队" name="mine">
        <div v-if="teamStore.teamsLoading" class="py-10 text-center app-muted">加载中…</div>

        <el-empty v-else-if="!teamStore.teams.length" description="还没有加入任何团队">
          <el-button type="primary" @click="activeTab = 'discover'">去发现团队</el-button>
        </el-empty>

        <div v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="team in teamStore.teams"
            :key="team.id"
            class="flex cursor-pointer flex-col rounded-xl border app-border app-card p-4 transition app-hover"
            @click="openDetail(team)"
          >
            <div class="mb-2 flex items-start gap-2">
              <h3 class="min-w-0 flex-1 truncate font-medium app-text">{{ team.name }}</h3>
              <el-tag size="small" :type="roleTagTypes[team.myRole] || 'info'">
                {{ roleLabels[team.myRole] || team.myRole }}
              </el-tag>
            </div>
            <p class="mb-3 line-clamp-2 min-h-[2.5rem] text-xs app-muted">
              {{ team.description || '暂无简介' }}
            </p>
            <div class="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-xs app-muted">
              <span class="flex items-center gap-1">
                <el-icon><UserFilled /></el-icon>{{ team.memberCount }} 人
              </span>
              <span>{{ team.knowledgeBaseCount }} 个知识库</span>
              <span
                v-if="canManage(team) && team.pendingRequestCount"
                class="flex items-center gap-1 text-amber-500"
              >
                <el-icon><Bell /></el-icon>{{ team.pendingRequestCount }} 待审批
              </span>
            </div>
          </article>
        </div>
      </el-tab-pane>

      <!-- ============ 发现团队 ============ -->
      <el-tab-pane label="发现团队" name="discover">
        <div class="mb-4 flex flex-wrap items-center gap-2">
          <el-input
            v-model="keyword"
            placeholder="搜索团队名称或简介"
            clearable
            class="max-w-xs"
            :prefix-icon="Search"
            @keyup.enter="onSearch"
            @clear="onSearch"
          />
          <el-button type="primary" :loading="teamStore.searching" @click="onSearch">搜索</el-button>
        </div>

        <el-empty v-if="!teamStore.searchResults.length" description="没有找到可加入的公开团队" />

        <div v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="team in teamStore.searchResults"
            :key="team.id"
            class="flex flex-col rounded-xl border app-border app-card p-4"
          >
            <div class="mb-2 flex items-start gap-2">
              <h3 class="min-w-0 flex-1 truncate font-medium app-text">{{ team.name }}</h3>
              <el-tag size="small" type="info">{{ visibilityLabels[team.visibility] }}</el-tag>
            </div>
            <p class="mb-2 line-clamp-2 min-h-[2.5rem] text-xs app-muted">
              {{ team.description || '暂无简介' }}
            </p>
            <p class="mb-3 text-[11px] app-muted">
              加入方式：{{ policyLabels[team.joinPolicy] }} · {{ team.memberCount }} 人
            </p>

            <div class="mt-auto">
              <template v-if="myRoleIn(team)">
                <el-button size="small" disabled class="w-full">已在团队中</el-button>
              </template>
              <template v-else-if="team.myRequestStatus === 'pending'">
                <el-button size="small" disabled class="w-full">申请审核中</el-button>
              </template>
              <template v-else>
                <el-button
                  size="small"
                  type="primary"
                  class="w-full"
                  :disabled="team.joinPolicy === 'closed'"
                  @click="onApply(team)"
                >
                  {{ team.joinPolicy === 'open' ? '加入团队' : '申请加入' }}
                </el-button>
              </template>
            </div>
          </article>
        </div>
      </el-tab-pane>

      <!-- ============ 我的申请 ============ -->
      <el-tab-pane label="我的申请" name="requests">
        <el-empty v-if="!teamStore.myRequests.length" description="还没有提交过入队申请" />

        <el-table v-else :data="teamStore.myRequests" class="w-full">
          <el-table-column prop="teamName" label="团队" min-width="140" />
          <el-table-column prop="message" label="留言" min-width="140" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.status === 'approved' ? 'success' : row.status === 'rejected' ? 'danger' : 'warning'"
              >
                {{ row.status === 'approved' ? '已通过' : row.status === 'rejected' ? '已拒绝' : '审核中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="提交时间" width="170">
            <template #default="{ row }">{{ formatDateTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'pending'"
                size="small"
                text
                type="danger"
                @click="teamStore.cancelMyRequest(row.teamId, row.id)"
              >
                撤回
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ============ 创建团队 ============ -->
    <el-dialog v-model="createVisible" title="创建团队" width="520px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="88px">
        <el-form-item label="团队名称" prop="name">
          <el-input v-model="createForm.name" maxlength="64" show-word-limit placeholder="例如：网络工程组" />
        </el-form-item>
        <el-form-item label="团队简介">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="简单说明团队用途，便于他人搜索到"
          />
        </el-form-item>
        <el-form-item label="可见性">
          <el-radio-group v-model="createForm.visibility">
            <el-radio value="public">公开（可被搜索）</el-radio>
            <el-radio value="private">私有（仅邀请码）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="加入方式">
          <el-radio-group v-model="createForm.joinPolicy">
            <el-radio value="approval">需审核</el-radio>
            <el-radio value="open">邀请码直接加入</el-radio>
            <el-radio value="closed">禁止加入</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- ============ 邀请码加入 ============ -->
    <el-dialog v-model="inviteVisible" title="用邀请码加入团队" width="440px">
      <el-form label-width="72px">
        <el-form-item label="邀请码">
          <el-input
            v-model="inviteForm.code"
            placeholder="请输入 8 位邀请码"
            maxlength="16"
            @input="inviteForm.code = inviteForm.code.toUpperCase()"
          />
        </el-form-item>
        <el-form-item label="留言">
          <el-input v-model="inviteForm.message" placeholder="选填，便于管理员识别" maxlength="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inviteVisible = false">取消</el-button>
        <el-button type="primary" @click="submitInvite">提交</el-button>
      </template>
    </el-dialog>

    <!-- ============ 团队详情抽屉 ============ -->
    <el-drawer v-model="detailVisible" :size="620" :with-header="false">
      <div v-if="activeTeam" class="flex h-full flex-col">
        <header class="border-b app-border px-5 py-4">
          <div class="flex items-start gap-3">
            <div class="min-w-0 flex-1">
              <h2 class="flex items-center gap-2 text-lg font-semibold app-text">
                <span class="truncate">{{ activeTeam.name }}</span>
                <el-tag size="small" :type="roleTagTypes[activeTeam.myRole] || 'info'">
                  {{ roleLabels[activeTeam.myRole] || activeTeam.myRole }}
                </el-tag>
              </h2>
              <p class="mt-1 text-xs app-muted">
                {{ visibilityLabels[activeTeam.visibility] }} ·
                {{ policyLabels[activeTeam.joinPolicy] }} ·
                {{ activeTeam.memberCount }} 人 ·
                {{ activeTeam.knowledgeBaseCount }} 个知识库
              </p>
            </div>
            <el-button :icon="Refresh" circle text @click="refreshDetail" />
            <el-button text @click="detailVisible = false">
              <el-icon><Close /></el-icon>
            </el-button>
          </div>

          <div
            v-if="activeTeam.inviteCode"
            class="mt-3 flex items-center gap-2 rounded-lg border app-border px-3 py-2"
          >
            <span class="text-xs app-muted">邀请码</span>
            <code class="font-mono text-sm font-semibold tracking-wider app-text">
              {{ activeTeam.inviteCode }}
            </code>
            <el-button
              size="small"
              text
              :icon="CopyDocument"
              @click="copyText(activeTeam.inviteCode, '邀请码已复制')"
            >
              复制
            </el-button>
            <el-button size="small" text type="warning" @click="teamStore.resetInviteCode(activeTeam.id)">
              重置
            </el-button>
          </div>
        </header>

        <el-tabs v-model="detailTab" class="flex-1 overflow-hidden px-5">
          <!-- 成员 -->
          <el-tab-pane label="成员" name="members">
            <div class="h-full overflow-y-auto pb-6">
              <div v-if="teamStore.isAdmin" class="mb-3">
                <AddMemberForm @submit="onAddMember" />
              </div>

              <div v-if="teamStore.membersLoading" class="py-6 text-center app-muted">加载中…</div>

              <ul v-else class="space-y-2">
                <li
                  v-for="member in members"
                  :key="member.id"
                  class="flex flex-wrap items-center gap-3 rounded-lg border app-border px-3 py-2"
                >
                  <span
                    class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-light to-brand text-xs font-semibold text-white"
                  >
                    {{ (member.user?.nickname || member.user?.username || '?').slice(0, 1) }}
                  </span>
                  <div class="min-w-0 flex-1">
                    <p class="truncate text-sm app-text">
                      {{ member.user?.nickname || member.user?.username }}
                      <span v-if="member.userId === myUserId" class="text-xs app-muted">（我）</span>
                    </p>
                    <p class="truncate text-[11px] app-muted">
                      @{{ member.user?.username }} · 加入于 {{ formatDateTime(member.joinedAt) }}
                    </p>
                  </div>
                  <el-tag size="small" :type="roleTagTypes[member.role] || 'info'">
                    {{ roleLabels[member.role] || member.role }}
                  </el-tag>

                  <template v-if="teamStore.isAdmin && member.role !== 'owner'">
                    <el-button
                      size="small"
                      text
                      :disabled="member.userId === myUserId"
                      @click="onToggleAdmin(member)"
                    >
                      {{ member.role === 'admin' ? '取消管理员' : '设为管理员' }}
                    </el-button>
                    <el-button
                      size="small"
                      text
                      type="danger"
                      :disabled="member.userId === myUserId"
                      @click="onRemoveMember(member)"
                    >
                      移除
                    </el-button>
                  </template>
                  <template v-else-if="member.userId === myUserId">
                    <el-button size="small" text type="danger" @click="onRemoveMember(member)">
                      {{ teamStore.isOwner ? '退出（需先转让）' : '退出' }}
                    </el-button>
                  </template>
                  <template v-else-if="teamStore.isOwner">
                    <el-button size="small" text @click="onTransfer(member)">转让负责人</el-button>
                  </template>
                </li>
              </ul>
            </div>
          </el-tab-pane>

          <!-- 审批（仅管理员以上） -->
          <el-tab-pane v-if="teamStore.isAdmin" name="requests">
            <template #label>
              <span class="flex items-center gap-1">
                入队审批
                <el-badge v-if="teamStore.pendingCount" :value="teamStore.pendingCount" />
              </span>
            </template>

            <div class="h-full overflow-y-auto pb-6">
              <el-empty v-if="!joinRequests.length" description="没有待审批的申请" />
              <ul v-else class="space-y-2">
                <li
                  v-for="request in joinRequests"
                  :key="request.id"
                  class="rounded-lg border app-border px-3 py-2"
                >
                  <div class="flex items-center gap-3">
                    <div class="min-w-0 flex-1">
                      <p class="truncate text-sm app-text">
                        {{ request.user?.nickname || request.user?.username }}
                        <span class="text-xs app-muted">@{{ request.user?.username }}</span>
                      </p>
                      <p class="text-[11px] app-muted">
                        {{ request.source === 'invite_code' ? '邀请码申请' : '搜索申请' }} ·
                        {{ formatDateTime(request.createdAt) }}
                      </p>
                    </div>
                    <el-button size="small" type="primary" :icon="Check" @click="onApprove(request)">
                      同意
                    </el-button>
                    <el-button size="small" :icon="Close" @click="onReject(request)">拒绝</el-button>
                  </div>
                  <p v-if="request.message" class="mt-1 text-xs app-muted">
                    留言：{{ request.message }}
                  </p>
                </li>
              </ul>
            </div>
          </el-tab-pane>

          <!-- 团队设置（仅管理员以上） -->
          <el-tab-pane v-if="teamStore.isAdmin" name="settings">
            <template #label>
              <span class="flex items-center gap-1">
                <el-icon><Setting /></el-icon>团队设置
              </span>
            </template>
            <div class="h-full overflow-y-auto pb-6">
              <TeamSettingsPanel
                :team="activeTeam"
                @save="(payload) => teamStore.update(activeTeam.id, payload)"
                @dissolve="onDissolve"
              />
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>
  </div>
</template>
