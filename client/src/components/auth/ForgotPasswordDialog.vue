<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Message, User } from '@element-plus/icons-vue'

import { forgotPassword } from '@/api/auth'
import { notifyError } from '@/utils/notify'

const visible = defineModel({ type: Boolean, default: false })

const formRef = ref(null)
const submitting = ref(false)
const sent = ref(false)

const form = reactive({ username: '', email: '' })

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入注册邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

const title = computed(() => (sent.value ? '重置邮件已发送' : '找回密码'))

function close() {
  visible.value = false
}

async function submit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    await forgotPassword({ username: form.username.trim(), email: form.email.trim() })
    sent.value = true
    ElMessage.success('重置邮件已发送，请查收')
  } catch (error) {
    notifyError(error, '发送失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

// 关闭后重置，便于下次打开
function onClosed() {
  sent.value = false
  formRef.value?.resetFields()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="420px"
    append-to-body
    @closed="onClosed"
  >
    <template v-if="!sent">
      <p class="mb-5 text-[13px] leading-6 text-[#7a7a7a] dark:text-[#a0a0a0]">
        输入你的用户名与注册邮箱，我们会向你发送一封密码重置邮件。
      </p>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            size="large"
            placeholder="请输入用户名"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item label="注册邮箱" prop="email">
          <el-input
            v-model="form.email"
            size="large"
            placeholder="you@example.com"
            :prefix-icon="Message"
            @keyup.enter="submit"
          />
        </el-form-item>
      </el-form>

      <p class="text-[11px] leading-5 text-[#9a9a9a]">
        出于安全考虑，无论账号是否存在，我们都会返回相同的结果。
      </p>
    </template>

    <div v-else class="py-2 text-center">
      <div class="mx-auto grid h-12 w-12 place-items-center rounded-full bg-brand/10 text-brand">
        <el-icon :size="24"><Message /></el-icon>
      </div>
      <p class="mt-4 text-sm font-medium text-[#0d0d0d] dark:text-[#ececec]">
        重置链接已发送至 {{ form.email }}
      </p>
      <p class="mt-2 text-[13px] leading-6 text-[#8c8c8c]">
        请在 30 分钟内点击邮件中的链接完成重置。若未收到，请检查垃圾邮件目录，
        或联系管理员协助处理。
      </p>
    </div>

    <template #footer>
      <el-button v-if="!sent" @click="close">取消</el-button>
      <el-button v-if="!sent" type="primary" :loading="submitting" @click="submit">
        发送重置邮件
      </el-button>
      <el-button v-else type="primary" @click="close">知道了</el-button>
    </template>
  </el-dialog>
</template>
