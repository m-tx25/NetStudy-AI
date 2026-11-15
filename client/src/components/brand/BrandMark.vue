<script setup>
/**
 * 品牌标记：3×3 矩阵格 + 中心圆点。
 *
 * 和 PWA 图标（public/icon-*.png、favicon.svg）用同一套几何参数，
 * 保证「桌面图标 / 浏览器标签 / 站内 logo」是同一个图形，
 * 而不是站内一个字母方块、图标又是一个东西。
 */
import { computed } from 'vue'

const props = defineProps({
  size: { type: Number, default: 28 },
  /** 圆角比例，和图标保持 0.225 一致 */
  radius: { type: Number, default: 7.2 },
})

const UNIT = 5.4
const GAP = 2.1
const TOTAL = UNIT * 3 + GAP * 2
const LEFT = (32 - TOTAL) / 2

const cells = computed(() => {
  const list = []
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 3; col += 1) {
      list.push({
        key: `${row}-${col}`,
        x: LEFT + col * (UNIT + GAP),
        y: LEFT + row * (UNIT + GAP),
        center: row === 1 && col === 1,
        opacity: (row + col) % 2 === 0 ? 1 : 0.68,
      })
    }
  }
  return list
})
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 32 32"
    role="img"
    aria-label="苍穹矩阵"
    class="shrink-0"
  >
    <defs>
      <linearGradient id="brand-mark-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#3ecf9a" />
        <stop offset="1" stop-color="#128464" />
      </linearGradient>
    </defs>
    <rect width="32" height="32" :rx="radius" fill="url(#brand-mark-grad)" />
    <template v-for="cell in cells" :key="cell.key">
      <circle
        v-if="cell.center"
        :cx="cell.x + UNIT / 2"
        :cy="cell.y + UNIT / 2"
        :r="UNIT / 2 - 0.25"
        fill="#fff"
      />
      <rect
        v-else
        :x="cell.x"
        :y="cell.y"
        :width="UNIT"
        :height="UNIT"
        :rx="UNIT * 0.3"
        fill="#fff"
        :fill-opacity="cell.opacity"
      />
    </template>
  </svg>
</template>
