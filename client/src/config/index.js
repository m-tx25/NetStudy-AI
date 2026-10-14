/**
 * 全局运行时配置。所有环境变量集中在这里读取，
 * 避免在业务代码里散落 import.meta.env。
 */

const raw = import.meta.env

function toBool(value, fallback = false) {
  if (value === undefined || value === null || value === '') return fallback
  return ['true', '1', 'yes', 'on'].includes(String(value).toLowerCase())
}

export const API_BASE_URL = raw.VITE_API_BASE_URL || '/api'

/** 是否启用内置 Mock：无后端也能完整体验整个前端流程 */
export const isMockMode = toBool(raw.VITE_USE_MOCK, false)

export const APP_TITLE = raw.VITE_APP_TITLE || 'RAG 知识问答系统'

/** 页脚展示用的主体信息（上线前按实际主体替换） */
export const COMPANY_NAME = raw.VITE_COMPANY_NAME || 'RAG 知识问答系统项目组'
export const ICP_LICENSE = raw.VITE_ICP_LICENSE || ''
export const SUPPORT_EMAIL = raw.VITE_SUPPORT_EMAIL || 'support@example.com'

/** localStorage 键名统一在这里定义 */
export const STORAGE_KEYS = {
  token: 'rag.access_token',
  user: 'rag.user',
  theme: 'rag.theme',
  activeKnowledgeBases: 'rag.active_kb',
  /** 用户选择的生成模型 id（见 GET /api/chat/models） */
  selectedModel: 'rag.model',
}

/** 知识库文档上传限制（与后端保持一致即可） */
export const UPLOAD_LIMITS = {
  maxSizeMB: 50,
  accept: '.pdf,.doc,.docx,.txt,.md,.markdown,.csv,.xlsx,.xls,.pptx,.html,.json',
}

/** 问答默认检索参数 */
export const RAG_DEFAULTS = {
  topK: 5,
  scoreThreshold: 0.2,
}
