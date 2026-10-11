import { ref } from 'vue'

/** 移动端侧边栏抽屉状态（模块级单例，跨组件共享） */
const mobileSidebarOpen = ref(false)

export function useSidebar() {
  return {
    mobileSidebarOpen,
    openMobileSidebar: () => {
      mobileSidebarOpen.value = true
    },
    closeMobileSidebar: () => {
      mobileSidebarOpen.value = false
    },
    toggleMobileSidebar: () => {
      mobileSidebarOpen.value = !mobileSidebarOpen.value
    },
  }
}
