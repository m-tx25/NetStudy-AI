/**
 * 通用格式化工具。
 */

export function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 9)}`
}

export function formatBytes(bytes) {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  const size = value / 1024 ** index
  return `${size >= 10 || index === 0 ? Math.round(size) : size.toFixed(1)} ${units[index]}`
}

const pad = (n) => String(n).padStart(2, '0')

export function formatDateTime(input) {
  const date = toDate(input)
  if (!date) return '-'
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 会话列表用的相对时间：刚刚 / 12:30 / 昨天 / 3月5日 / 2024-03-05 */
export function formatRelativeTime(input) {
  const date = toDate(input)
  if (!date) return ''
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  if (diff < 60 * 1000) return '刚刚'
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / 60000)} 分钟前`

  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const time = date.getTime()
  if (time >= startOfToday) return `${pad(date.getHours())}:${pad(date.getMinutes())}`
  if (time >= startOfToday - 86400000) return '昨天'
  if (time >= startOfToday - 86400000 * 6) return `${date.getMonth() + 1}月${date.getDate()}日`
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 会话列表分组：今天 / 最近 7 天 / 更早 */
export function groupByDate(items, getTime = (item) => item.updatedAt ?? item.createdAt) {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const buckets = [
    { label: '今天', items: [] },
    { label: '最近 7 天', items: [] },
    { label: '更早', items: [] },
  ]
  for (const item of items) {
    const date = toDate(getTime(item))
    const time = date ? date.getTime() : 0
    if (time >= startOfToday) buckets[0].items.push(item)
    else if (time >= startOfToday - 86400000 * 6) buckets[1].items.push(item)
    else buckets[2].items.push(item)
  }
  return buckets.filter((bucket) => bucket.items.length > 0)
}

export function truncate(text, max = 30) {
  const value = String(text ?? '').replace(/\s+/g, ' ').trim()
  return value.length > max ? `${value.slice(0, max)}…` : value
}

/** 从提问内容生成会话标题 */
export function titleFromQuestion(question) {
  const value = String(question ?? '')
    .replace(/[#*`>\-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return value ? truncate(value, 24) : '新的对话'
}

export function toDate(input) {
  if (!input) return null
  if (input instanceof Date) return Number.isNaN(input.getTime()) ? null : input
  const normalized = typeof input === 'string' ? input.replace(' ', 'T') : input
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

/** 把后端可能返回的 0~1 相似度统一成百分比文本 */
export function formatScore(score) {
  const value = Number(score)
  if (!Number.isFinite(value)) return ''
  const percent = value <= 1 ? value * 100 : value
  return `${percent.toFixed(1)}%`
}
