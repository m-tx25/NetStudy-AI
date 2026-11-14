import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createComparison,
  deleteComparison,
  downloadReport,
  getComparison,
  listComparisons,
  rerunComparison,
} from '@/api/compare'

/**
 * 多篇论文对比 store。
 *
 * 关键点：对比是后台任务，创建后必须**轮询**到 ready/failed。
 * 轮询放在 store 里而不是页面里，这样切到别的页面再回来时
 * 仍能拿到最新结果，也不会因为组件卸载而丢掉定时器（只在登出时清）。
 */
export const useCompareStore = defineStore('compare', () => {
  const comparisons = ref([])
  const current = ref(null)
  const listLoading = ref(false)
  const busy = ref(false)

  let pollTimer = null

  const isRunning = computed(() => {
    const status = current.value?.status
    return status === 'pending' || status === 'running'
  })

  function stopPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  async function loadList() {
    listLoading.value = true
    try {
      comparisons.value = await listComparisons()
    } finally {
      listLoading.value = false
    }
  }

  /** 轮询单个对比，直到终态（ready / failed） */
  function poll(id, onDone) {
    stopPolling()
    const tick = async () => {
      try {
        const data = await getComparison(id)
        current.value = data
        const index = comparisons.value.findIndex((item) => item.id === id)
        if (index >= 0) comparisons.value[index] = data
        if (data.status === 'ready' || data.status === 'failed') {
          pollTimer = null
          if (typeof onDone === 'function') onDone(data)
          return
        }
      } catch {
        // 网络抖动不该中断轮询：下一轮继续，直到终态
      }
      pollTimer = setTimeout(tick, 3000)
    }
    tick()
  }

  async function start(documentIds, topic) {
    busy.value = true
    try {
      const created = await createComparison({ documentIds, topic })
      current.value = created
      comparisons.value = [created, ...comparisons.value]
      poll(created.id)
      return created
    } finally {
      busy.value = false
    }
  }

  async function open(id) {
    stopPolling()
    current.value = await getComparison(id)
    if (isRunning.value) poll(id)
    return current.value
  }

  async function rerun(id) {
    const data = await rerunComparison(id)
    current.value = data
    poll(id)
    return data
  }

  async function remove(id) {
    await deleteComparison(id)
    comparisons.value = comparisons.value.filter((item) => item.id !== id)
    if (current.value?.id === id) {
      stopPolling()
      current.value = null
    }
  }

  /**
   * 导出 Markdown：后端返回 blob，这里造一个临时链接点一下。
   * 文件名用对比主题，方便用户直接在文件夹里认出来。
   */
  async function exportReport(id, title) {
    const response = await downloadReport(id)
    const blob = new Blob([response.data], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${(title || '论文对比报告').slice(0, 40)}.md`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  function reset() {
    stopPolling()
    comparisons.value = []
    current.value = null
  }

  return {
    comparisons,
    current,
    listLoading,
    busy,
    isRunning,
    loadList,
    start,
    open,
    rerun,
    remove,
    exportReport,
    reset,
    stopPolling,
  }
})
