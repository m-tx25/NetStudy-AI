import { ref } from 'vue'

/**
 * 服务协议 / 隐私政策弹窗的共享状态。
 * 登录卡片、注册卡片与页脚都要能唤起同一个弹窗，因此放在模块级单例里。
 */
const policyType = ref('')
const visible = ref(false)

const TITLES = {
  terms: '服务协议',
  privacy: '隐私政策',
}

export function usePolicyDialog() {
  return {
    policyType,
    visible,
    openPolicy(type) {
      policyType.value = type
      visible.value = true
    },
    titleOf(type) {
      return TITLES[type] || '条款'
    },
  }
}
