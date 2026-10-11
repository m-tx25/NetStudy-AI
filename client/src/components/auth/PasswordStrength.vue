<script setup>
import { computed } from 'vue'

import { evaluatePassword } from '@/utils/password'

const props = defineProps({
  password: { type: String, default: '' },
  username: { type: String, default: '' },
  /** 是否展示优化建议 */
  showTips: { type: Boolean, default: true },
})

const result = computed(() => evaluatePassword(props.password, props.username))
</script>

<template>
  <div class="w-full">
    <div class="flex items-center gap-2">
      <div class="flex flex-1 gap-1">
        <span
          v-for="segment in 4"
          :key="segment"
          class="h-1 flex-1 rounded-full transition-colors duration-200"
          :class="segment <= result.score ? result.color : 'bg-[#e9e9e9] dark:bg-[#3a3a3a]'"
        />
      </div>
      <span
        class="w-10 shrink-0 text-right text-[11px] font-medium"
        :class="{
          'text-[#a8a8a8]': result.score === 0,
          'text-red-500': result.level === 'weak',
          'text-amber-500': result.level === 'fair',
          'text-emerald-500': result.level === 'good',
          'text-brand': result.level === 'strong',
        }"
      >
        {{ result.label }}
      </span>
    </div>

    <p v-if="showTips && result.tips.length" class="mt-1.5 text-[11px] leading-4 text-[#9a9a9a]">
      {{ result.tips.join('；') }}
    </p>
  </div>
</template>
