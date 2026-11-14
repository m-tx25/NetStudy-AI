import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createReport,
  deleteReport,
  downloadExport,
  fetchPrintHtml,
  getReport,
  listReports,
  rerunReport,
} from '@/api/reports'

/**
 * 成果导出 store：与对比/研究一致的后台任务 + 轮询。
 */
export const useReportsStore = defineStore('reports', () => {
  const reports = ref([])
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
      reports.value = await listReports()
    } finally {
      listLoading.value = false
    }
  }

  function poll(id, onDone) {
    stopPolling()
    const tick = async () => {
      try {
        const data = await getReport(id)
        current.value = data
        const index = reports.value.findIndex((item) => item.id === id)
        if (index >= 0) reports.value[index] = data
        if (data.status === 'ready' || data.status === 'failed') {
          pollTimer = null
          if (typeof onDone === 'function') onDone(data)
          return
        }
      } catch {
        // 网络抖动不中断轮询
      }
      pollTimer = setTimeout(tick, 3000)
    }
    tick()
  }

  async function start(payload) {
    busy.value = true
    try {
      const created = await createReport(payload)
      current.value = created
      reports.value = [created, ...reports.value]
      poll(created.id)
      return created
    } finally {
      busy.value = false
    }
  }

  async function open(id) {
    stopPolling()
    current.value = await getReport(id)
    if (isRunning.value) poll(id)
    return current.value
  }

  async function rerun(id) {
    const data = await rerunReport(id)
    current.value = data
    poll(id)
    return data
  }

  async function remove(id) {
    await deleteReport(id)
    reports.value = reports.value.filter((item) => item.id !== id)
    if (current.value?.id === id) {
      stopPolling()
      current.value = null
    }
  }

  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  /** 导出 Markdown / Word */
  async function exportFile(id, format, title) {
    const response = await downloadExport(id, format)
    const type =
      format === 'docx'
        ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        : 'text/markdown;charset=utf-8'
    const name = `${(title || '报告').slice(0, 40)}.${format}`
    saveBlob(new Blob([response.data], { type }), name)
  }

  /**
   * 导出 PDF：后端给一份打印专用 HTML，前端打开后调起浏览器打印，
   * 用户选「另存为 PDF」。这样中文排版稳定，也不依赖服务端 PDF 库。
   */
  async function exportPdf(id) {
    const response = await fetchPrintHtml(id)
    const html = typeof response.data === 'string' ? response.data : await response.data.text()
    const win = window.open('', '_blank')
    if (!win) {
      throw new Error('浏览器拦截了弹窗，请允许本页面弹出窗口后重试')
    }
    win.document.open()
    win.document.write(html)
    win.document.close()
    // 等样式与字体就绪再调打印
    setTimeout(() => {
      try {
        win.focus()
        win.print()
      } catch (error) {
        console.warn('打印调用失败', error)
      }
    }, 600)
  }

  function reset() {
    stopPolling()
    reports.value = []
    current.value = null
  }

  return {
    reports,
    current,
    listLoading,
    busy,
    isRunning,
    loadList,
    start,
    open,
    rerun,
    remove,
    exportFile,
    exportPdf,
    reset,
    stopPolling,
  }
})
