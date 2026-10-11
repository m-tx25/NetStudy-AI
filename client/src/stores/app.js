import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 全局状态示例。业务状态按模块拆到 stores/ 下的独立文件，
 * 不要把所有东西都堆在同一个 store 里。
 */
export const useAppStore = defineStore('app', () => {
  const appName = ref('传智杯 Web 项目')

  function setAppName(name) {
    appName.value = name
  }

  return { appName, setAppName }
})
