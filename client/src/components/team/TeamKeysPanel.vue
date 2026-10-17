<script setup>
import ApiKeyManager from '@/components/keys/ApiKeyManager.vue'

/**
 * 团队 API 密钥面板（团队设置里的一个区块）。
 * 权限与安全由后端保证：仅 owner/admin 能读写，接口只返回掩码。
 */
defineProps({
  teamId: { type: String, required: true },
})
</script>

<template>
  <ApiKeyManager scope="team" :team-id="teamId" />
</template>
