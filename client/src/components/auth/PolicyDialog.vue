<script setup>
import { computed } from 'vue'

import { usePolicyDialog } from '@/composables/usePolicyDialog'
import { APP_TITLE, COMPANY_NAME, SUPPORT_EMAIL } from '@/config'

const { policyType, visible, titleOf } = usePolicyDialog()

const title = computed(() => titleOf(policyType.value))

const termsSections = [
  {
    heading: '一、服务说明',
    body: `${APP_TITLE} 为团队内部及企业客户提供基于私有知识库的检索增强问答服务。你可以在本平台上传自有文档、构建知识库，并通过对话的方式检索与查阅其中的内容。`,
  },
  {
    heading: '二、账号与安全',
    body: '你应妥善保管账号与密码，不得将账号出借、转让或与他人共享。账号下发生的一切操作均视为你本人的行为。如发现账号被非法使用，请立即修改密码并联系管理员。',
  },
  {
    heading: '三、内容规范',
    body: '你上传的文档应为您合法持有或已获得授权的内容，不得包含违反法律法规、侵犯他人知识产权或商业秘密的材料。平台会对上传内容进行解析与向量化处理，仅用于为你提供检索服务。',
  },
  {
    heading: '四、服务变更与终止',
    body: '平台可能因升级、维护等原因调整服务内容，并会提前通过站内通知或邮件告知。若你违反本协议，我们有权暂停或终止向你提供服务。',
  },
]

const privacySections = [
  {
    heading: '一、我们收集哪些信息',
    body: '为提供账号体系与问答服务，我们会处理你的账号标识（用户名、昵称、邮箱）、你上传的文档内容、以及问答过程中产生的会话记录。',
  },
  {
    heading: '二、信息如何使用',
    body: '上传的文档仅用于构建知识库与检索召回；会话记录用于展示历史对话与改进回答质量。我们不会将你的文档内容用于训练对外公开的模型。',
  },
  {
    heading: '三、信息如何存储',
    body: '数据存储于你所在组织指定的环境中，平台支持私有化部署，文档与向量数据不会离开你的内网环境。传输过程使用 TLS 加密。',
  },
  {
    heading: '四、你的权利',
    body: '你可以随时查看、修改自己的账号资料，删除知识库中的文档，或联系管理员注销账号。注销后相关数据将在约定周期内清除。',
  },
]
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="640px"
    top="6vh"
    class="policy-dialog"
    append-to-body
  >
    <div class="scrollbar-thin max-h-[62vh] overflow-y-auto pr-2">
      <p class="text-xs app-faint">
        最近更新：2025-01-01 · 生效日期：2025-01-01
      </p>

      <div class="mt-5 space-y-5">
        <section v-for="section in (policyType === 'privacy' ? privacySections : termsSections)" :key="section.heading">
          <h3 class="text-sm font-semibold app-text">
            {{ section.heading }}
          </h3>
          <p class="mt-1.5 text-[13px] leading-6 app-text-secondary">
            {{ section.body }}
          </p>
        </section>
      </div>

      <div
        class="mt-6 rounded-xl border app-border app-panel px-4 py-3 text-[13px] leading-6 app-text-secondary"
      >
        <p>
          本文件为演示用模板文本。正式对外提供服务前，请由法务按实际业务主体、数据流向与部署方式重新拟定，
          并替换 {{ COMPANY_NAME }} 的相关信息。
        </p>
        <p class="mt-1.5">
          如有疑问，可联系：
          <a class="app-accent hover:underline" :href="`mailto:${SUPPORT_EMAIL}`">{{ SUPPORT_EMAIL }}</a>
        </p>
      </div>
    </div>

    <template #footer>
      <el-button type="primary" @click="visible = false">我已阅读</el-button>
    </template>
  </el-dialog>
</template>
