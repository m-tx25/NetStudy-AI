<script setup>
import { CircleCheck, Document, DocumentChecked, Lock, OfficeBuilding } from '@element-plus/icons-vue'

import { APP_TITLE, isMockMode } from '@/config'

const capabilities = [
  {
    icon: Document,
    title: '全格式文档接入',
    desc: 'PDF / Word / Markdown / Excel 一键解析、自动分块与向量化',
  },
  {
    icon: DocumentChecked,
    title: '答案引用可溯源',
    desc: '每条结论都附带原文出处、页码与相关度，可点开逐条核对',
  },
  {
    icon: Lock,
    title: '数据不出内网',
    desc: '支持私有化部署，文档与向量库均落在你指定的环境中',
  },
  {
    icon: OfficeBuilding,
    title: '面向团队的协作',
    desc: '知识库分级管理、会话留痕、检索范围与召回参数随问随调',
  },
]

const trustItems = ['TLS 传输加密', '权限分级', '操作审计', '私有化部署']
</script>

<template>
  <div
    class="relative hidden overflow-hidden bg-[#070d1b] px-12 py-12 text-white lg:flex lg:w-[54%] lg:flex-col xl:px-16"
  >
    <!-- 背景：网格 + 光斑 + 渐层 -->
    <div
      class="pointer-events-none absolute inset-0 opacity-[0.16]"
      style="
        background-image:
          linear-gradient(to right, rgba(255, 255, 255, 0.5) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(255, 255, 255, 0.5) 1px, transparent 1px);
        background-size: 56px 56px;
        mask-image: radial-gradient(ellipse 80% 60% at 30% 20%, #000 40%, transparent 100%);
        -webkit-mask-image: radial-gradient(ellipse 80% 60% at 30% 20%, #000 40%, transparent 100%);
      "
    />
    <div
      class="pointer-events-none absolute -left-32 -top-40 h-[26rem] w-[26rem] rounded-full bg-brand/25 blur-[100px]"
    />
    <div
      class="pointer-events-none absolute -bottom-48 -right-24 h-[30rem] w-[30rem] rounded-full bg-cyan-400/15 blur-[110px]"
    />
    <div
      class="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#070d1b] to-transparent"
    />

    <!-- 顶部品牌 -->
    <div class="relative flex items-center justify-between">
      <div class="flex items-center gap-3">
        <span
          class="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-brand to-emerald-600 text-base font-bold shadow-lg shadow-brand/30"
        >
          R
        </span>
        <div class="leading-tight">
          <p class="text-[15px] font-semibold tracking-wide">{{ APP_TITLE }}</p>
          <p class="mt-0.5 text-[11px] text-white/45">Enterprise Knowledge Assistant</p>
        </div>
      </div>

      <span
        class="rounded-full border border-brand/40 bg-brand/10 px-2.5 py-1 text-[11px] font-medium text-brand"
      >
        企业版
      </span>
    </div>

    <!-- 主文案 -->
    <div class="relative mt-auto pt-14">
      <p
        class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-[11px] text-white/70"
      >
        <span class="h-1.5 w-1.5 rounded-full bg-brand" />
        检索增强生成 · RAG 架构
      </p>

      <h1 class="mt-6 max-w-xl text-[32px] font-semibold leading-[1.35] tracking-tight xl:text-[38px]">
        让每一个答案，<br />
        都能追溯到<span class="text-brand">原文出处</span>
      </h1>

      <p class="mt-5 max-w-lg text-sm leading-7 text-white/55">
        把团队的文档交给大模型之前，先用向量检索锁定最相关的片段。
        回答有据可依，结论可核可查——这是企业场景使用 AI 的底线。
      </p>
    </div>

    <!-- 能力卡片 -->
    <div class="relative mt-10 grid gap-3 sm:grid-cols-2">
      <div
        v-for="item in capabilities"
        :key="item.title"
        class="rounded-2xl border border-white/[0.08] bg-white/[0.04] p-4 backdrop-blur-sm transition-colors hover:border-brand/40 hover:bg-white/[0.07]"
      >
        <div class="flex items-center gap-2">
          <el-icon class="text-base text-brand"><component :is="item.icon" /></el-icon>
          <p class="text-[13px] font-medium">{{ item.title }}</p>
        </div>
        <p class="mt-2 text-[11px] leading-5 text-white/45">{{ item.desc }}</p>
      </div>
    </div>

    <!-- 信任条 -->
    <div class="relative mt-8 border-t border-white/[0.08] pt-5">
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span
          v-for="item in trustItems"
          :key="item"
          class="inline-flex items-center gap-1.5 text-[11px] text-white/45"
        >
          <el-icon class="text-brand/80"><CircleCheck /></el-icon>
          {{ item }}
        </span>
      </div>
      <p v-if="isMockMode" class="mt-3 text-[11px] text-amber-300/70">
        当前为 Mock 演示模式，未连接真实后端
      </p>
    </div>
  </div>
</template>
