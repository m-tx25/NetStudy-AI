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

const trustItems = ['传输加密', '权限分级', '操作审计', '私有化部署']
</script>

<template>
  <div
    class="relative hidden overflow-hidden border-r app-border px-12 py-14 lg:flex lg:flex-1 lg:flex-col xl:px-16"
  >
    <!-- 背景：科技网格 + 光晕 -->
    <div class="pointer-events-none absolute inset-0 tech-grid tech-grid-fade opacity-80" />
    <div class="tech-glow -left-24 -top-24 h-[24rem] w-[24rem] animate-pulse-glow" />
    <div
      class="tech-glow -bottom-32 right-0 h-[26rem] w-[26rem] animate-pulse-glow"
      style="background: #38bdf8; opacity: 0.09"
    />

    <!-- 顶部品牌 -->
    <div class="relative flex items-center justify-between">
      <div class="flex items-center gap-3">
        <span
          class="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-brand-light to-brand text-base font-bold text-white shadow-lg shadow-brand/30"
        >
          R
        </span>
        <div class="leading-tight">
          <p class="text-[15px] font-semibold tracking-wide app-text">
            {{ APP_TITLE }}
          </p>
          <p class="mt-0.5 font-mono text-[11px] app-faint">Enterprise Knowledge Assistant</p>
        </div>
      </div>

      <span
        class="rounded-full border border-brand-light/40 app-accent-soft px-2.5 py-1 text-[11px] font-medium"
      >
        企业版
      </span>
    </div>

    <!-- 主文案 -->
    <div class="relative mt-auto max-w-xl">
      <p
        class="inline-flex items-center gap-2 rounded-full border app-border px-3 py-1.5 text-[11px] app-muted tech-glass"
      >
        <span class="relative flex h-1.5 w-1.5">
          <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-light opacity-75" />
          <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand-light" />
        </span>
        检索增强生成 · RAG 架构
      </p>

      <h1
        class="mt-6 text-balance text-[32px] font-semibold leading-[1.35] tracking-tight app-text xl:text-[38px]"
      >
        让每一个答案，<br />
        都能追溯到<span class="tech-gradient-text">原文出处</span>
      </h1>

      <p class="mt-5 max-w-lg text-sm leading-7 app-muted">
        把团队的文档交给大模型之前，先用向量检索锁定最相关的片段。
        回答有据可依，结论可核可查——这是企业场景使用 AI 的底线。
      </p>
    </div>

    <!-- 能力卡片 -->
    <div class="relative mt-10 grid gap-3 sm:grid-cols-2">
      <div
        v-for="item in capabilities"
        :key="item.title"
        class="rounded-2xl tech-glass p-4 tech-lift"
      >
        <div class="flex items-center gap-2">
          <el-icon class="text-base app-accent"><component :is="item.icon" /></el-icon>
          <p class="text-[13px] font-medium app-text">{{ item.title }}</p>
        </div>
        <p class="mt-2 text-[11px] leading-5 app-muted">{{ item.desc }}</p>
      </div>
    </div>

    <!-- 信任条 -->
    <div class="relative mt-8 border-t app-border pt-5">
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
        <span
          v-for="item in trustItems"
          :key="item"
          class="inline-flex items-center gap-1.5 text-[11px] app-muted"
        >
          <el-icon class="app-accent"><CircleCheck /></el-icon>
          {{ item }}
        </span>
      </div>
      <p v-if="isMockMode" class="mt-3 text-[11px] app-faint">
        当前为 Mock 演示模式，未连接真实后端
      </p>
    </div>
  </div>
</template>
