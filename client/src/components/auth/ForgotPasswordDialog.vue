<script setup>
/**
 * 「忘记密码」说明弹窗
 *
 * 背景：这里原本是一个收集「用户名 + 邮箱」并提交的表单，提交后提示
 * 「重置邮件已发送，请查收」——但后端从未真的发邮件，也不会改密码
 * （`/api/auth/forgot-password` 当时只是返回成功）。
 *
 * 与其假装成功、让用户（尤其演示/评审场景）一直等一封永远不会来的邮件，
 * 不如明确告知「暂未开放」并给出可行的替代路径。
 * 后端该接口现在返回 501 + 同样的文案，直接调 API 也不会再被误导。
 */
import { Lock } from '@element-plus/icons-vue'

const visible = defineModel({ type: Boolean, default: false })

function close() {
  visible.value = false
}
</script>

<template>
  <el-dialog v-model="visible" title="找回密码" width="440px" append-to-body>
    <div class="py-2">
      <div class="mx-auto grid h-12 w-12 place-items-center rounded-full app-accent-soft">
        <el-icon :size="24"><Lock /></el-icon>
      </div>

      <p class="mt-4 text-center text-sm font-medium app-text">
        密码重置功能暂未开放
      </p>

      <p class="mt-3 text-[13px] leading-6 app-text-secondary">
        当前版本还没有接入邮件服务，无法自助重置密码。如需找回账号，请：
      </p>

      <ul class="mt-2 space-y-1.5 pl-5 text-[13px] leading-6 app-text-secondary">
        <li class="list-disc">联系团队负责人或管理员，帮你重置密码；</li>
        <li class="list-disc">或使用其他账号登录，在「设置 → API 密钥」重新配置即可继续使用。</li>
      </ul>

      <p class="mt-3 rounded-lg border app-border px-3 py-2 text-[12px] leading-5 app-muted">
        演示账号：用户名 <code class="app-text">demo</code>，密码
        <code class="app-text">123456</code>（可直接登录体验全部功能）。
      </p>
    </div>

    <template #footer>
      <el-button type="primary" @click="close">知道了</el-button>
    </template>
  </el-dialog>
</template>
