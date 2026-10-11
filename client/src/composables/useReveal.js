import { onBeforeUnmount, onMounted } from 'vue'

/**
 * 首页滚动进入动画：给容器内所有 .reveal 元素加上/移除 is-visible。
 * 用 IntersectionObserver 实现，离开视口后会自动移除，来回滚动都能重播。
 * @param {import('vue').Ref<HTMLElement|null>} rootRef 容器
 */
export function useReveal(rootRef) {
  let observer = null

  onMounted(() => {
    const root = rootRef.value
    if (!root) return

    const targets = root.querySelectorAll('.reveal')

    if (typeof IntersectionObserver === 'undefined') {
      targets.forEach((el) => el.classList.add('is-visible'))
      return
    }

    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          entry.target.classList.toggle('is-visible', entry.isIntersecting)
        })
      },
      { rootMargin: '-8% 0px -12% 0px', threshold: 0.12 },
    )

    targets.forEach((el) => observer.observe(el))
  })

  onBeforeUnmount(() => {
    if (observer) observer.disconnect()
  })
}
