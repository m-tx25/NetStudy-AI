<script setup>
import { reactive, ref, watch } from 'vue'

import TeamKeysPanel from '@/components/team/TeamKeysPanel.vue'

/**
 * 团队设置：基本信息 + 团队 API 密钥 + 危险操作（解散）。
 * 仅 owner/admin 能看到该面板（由父组件控制渲染）。
 */
const props = defineProps({
  team: { type: Object, required: true },
})
const emit = defineEmits(['save', 'dissolve'])

const form = reactive({
  name: '',
  description: '',
  visibility: 'public',
  joinPolicy: 'approval',
})
const saving = ref(false)

function syncFromTeam(team) {
  if (!team) return
  form.name = team.name || ''
  form.description = team.description || ''
  form.visibility = team.visibility || 'public'
  form.joinPolicy = team.joinPolicy || 'approval'
}

watch(() => props.team, syncFromTeam, { immediate: true, deep: true })

async function onSave() {
  if (!form.name.trim()) return
  saving.value = true
  try {
    emit('save', { ...form })
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- 基本信息 -->
    <section>
      <h3 class="mb-3 text-sm font-medium app-text">基本信息</h3>
      <el-form label-width="88px">
        <el-form-item label="团队名称">
          <el-input v-model="form.name" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="团队简介">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="可见性">
          <el-radio-group v-model="form.visibility">
            <el-radio value="public">公开（可被搜索）</el-radio>
            <el-radio value="private">私有（仅邀请码）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="加入方式">
          <el-radio-group v-model="form.joinPolicy">
            <el-radio value="approval">需审核</el-radio>
            <el-radio value="open">邀请码直接加入</el-radio>
            <el-radio value="closed">禁止加入</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSave">保存修改</el-button>
        </el-form-item>
      </el-form>
    </section>

    <!-- 团队 API 密钥 -->
    <section class="border-t app-border pt-5">
      <TeamKeysPanel :team-id="team.id" />
    </section>

    <!-- 危险操作 -->
    <section class="border-t app-border pt-5">
      <h3 class="mb-2 text-sm font-medium text-red-500">危险操作</h3>
      <p class="mb-3 text-xs app-muted">
        解散团队会删除团队知识库、其下所有文档与成员关系，且<strong>无法恢复</strong>。仅负责人可执行。
      </p>
      <el-button type="danger" plain @click="emit('dissolve')">解散团队</el-button>
    </section>
  </div>
</template>
