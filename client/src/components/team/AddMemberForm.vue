<script setup>
import { reactive, ref } from 'vue'

/**
 * 管理员直接拉人入队（免审批）。
 * 通过 emit 把请求交给父组件处理，父组件返回 true 表示成功后清空输入。
 */
const props = defineProps({
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['submit'])

const form = reactive({ username: '', role: 'member' })
const submitting = ref(false)

async function onSubmit() {
  const username = form.username.trim()
  if (!username) return
  submitting.value = true
  try {
    emit('submit', username, form.role)
    form.username = ''
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <el-input
      v-model="form.username"
      placeholder="输入用户名直接拉人入队"
      size="small"
      class="max-w-[220px]"
      @keyup.enter="onSubmit"
    />
    <el-select v-model="form.role" size="small" class="w-[112px]">
      <el-option label="普通成员" value="member" />
      <el-option label="管理员" value="admin" />
    </el-select>
    <el-button size="small" type="primary" :loading="submitting" @click="onSubmit">
      添加成员
    </el-button>
  </div>
</template>
