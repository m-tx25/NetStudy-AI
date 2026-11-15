import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 移动端断点判断（与 Tailwind 的 md 断点对齐：768px）。
 *
 * 为什么不用纯 CSS：Element Plus 的表格列宽是 JS 计算出来的，
 * 用 `hidden` 类只隐藏单元格内容，列宽仍占位，表格照样溢出。
 * 真要在手机上少显示几列，必须用 v-if 把整列去掉。
 */
export function useIsMobile(maxWidth = 767) {
  const query = `(max-width: ${maxWidth}px)`
  const isMobile = ref(false)
  let media = null

  const update = (event) => {
    isMobile.value = event.matches
  }

  onMounted(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    media = window.matchMedia(query)
    isMobile.value = media.matches
    media.addEventListener('change', update)
  })

  onBeforeUnmount(() => {
    if (media) media.removeEventListener('change', update)
  })

  return { isMobile }
}
