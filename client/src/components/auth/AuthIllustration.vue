<script setup>
/**
 * 登录页右栏插画：纯手写 SVG，无外部图片依赖。
 * 画面内容是"知识库 → 检索 → 可溯源答案"的抽象示意：
 * 问答窗口（命中率环图 + 柱状图）、文档卡片、引用卡片、放大镜"找答案"。
 * 尺寸随容器缩放，浅色/深色下都保持同一套明亮配色。
 */
</script>

<template>
  <svg
    viewBox="0 0 660 440"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    role="img"
    aria-label="智能问答与引用溯源示意图"
  >
    <defs>
      <linearGradient id="authIllHead" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#2fd1a6" />
        <stop offset="1" stop-color="#0f9b7a" />
      </linearGradient>
      <linearGradient id="authIllArc" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#7ecfbb" />
        <stop offset="1" stop-color="#0f9b7a" />
      </linearGradient>
      <linearGradient id="authIllCard" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#ffffff" />
        <stop offset="1" stop-color="#f4fbf8" />
      </linearGradient>
      <filter id="authIllShadow" x="-30%" y="-30%" width="170%" height="190%">
        <feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#0b7c62" flood-opacity="0.18" />
      </filter>
    </defs>

    <!-- 底部投影 / 光斑 -->
    <ellipse cx="330" cy="414" rx="238" ry="16" fill="#b7e6d6" opacity="0.35" />

    <!-- 主窗口：智能问答 -->
    <g filter="url(#authIllShadow)">
      <rect x="40" y="168" width="382" height="238" rx="16" fill="url(#authIllCard)" stroke="#d9efe7" />
    </g>
    <path
      d="M40 184a16 16 0 0 1 16-16h350a16 16 0 0 1 16 16v26H40z"
      fill="url(#authIllHead)"
    />
    <text x="66" y="203" fill="#ffffff" font-size="12" font-weight="600">智能问答</text>
    <circle cx="368" cy="194" r="3.4" fill="#ffffff" opacity="0.75" />
    <circle cx="382" cy="194" r="3.4" fill="#ffffff" opacity="0.6" />
    <circle cx="396" cy="194" r="3.4" fill="#ffffff" opacity="0.45" />

    <!-- 环图：引用命中率 -->
    <circle cx="140" cy="300" r="44" stroke="#eaf7f2" stroke-width="14" fill="none" />
    <circle
      cx="140"
      cy="300"
      r="44"
      stroke="url(#authIllArc)"
      stroke-width="14"
      stroke-linecap="round"
      fill="none"
      stroke-dasharray="184 277"
      transform="rotate(-90 140 300)"
    />
    <text x="140" y="299" text-anchor="middle" fill="#12352c" font-size="20" font-weight="700">
      92%
    </text>
    <text x="140" y="317" text-anchor="middle" fill="#8ba59d" font-size="8">引用命中率</text>

    <!-- 柱状图 + 文本行 -->
    <g>
      <rect x="222" y="292" width="16" height="44" rx="5" fill="#e3f6ef" />
      <rect x="248" y="272" width="16" height="64" rx="5" fill="#cdeee3" />
      <rect x="274" y="284" width="16" height="52" rx="5" fill="#e3f6ef" />
      <rect x="300" y="256" width="16" height="80" rx="5" fill="#0f9b7a" />
      <rect x="326" y="268" width="16" height="68" rx="5" fill="#7ecfbb" />
    </g>
    <rect x="222" y="352" width="120" height="7" rx="3.5" fill="#ecf6f2" />
    <rect x="222" y="366" width="88" height="7" rx="3.5" fill="#eff8f4" />

    <!-- 悬浮文档卡片 -->
    <g filter="url(#authIllShadow)">
      <rect x="250" y="48" width="196" height="86" rx="14" fill="#ffffff" stroke="#e2f2ea" />
    </g>
    <rect x="266" y="64" width="42" height="42" rx="11" fill="#e7f6f1" />
    <text x="287" y="90" text-anchor="middle" fill="#0f9b7a" font-size="10" font-weight="700">
      PDF
    </text>
    <rect x="320" y="72" width="108" height="8" rx="4" fill="#e6f0ec" />
    <rect x="320" y="88" width="74" height="8" rx="4" fill="#eff8f4" />
    <rect x="320" y="106" width="56" height="16" rx="8" fill="#e9f8f1" />
    <text x="348" y="118" text-anchor="middle" fill="#16a37b" font-size="8">已引用</text>

    <!-- 右侧引用卡片 -->
    <g filter="url(#authIllShadow)">
      <rect x="474" y="190" width="126" height="204" rx="16" fill="#ffffff" stroke="#e2f2ea" />
    </g>
    <circle cx="537" cy="222" r="20" fill="#e7f6f1" />
    <circle cx="537" cy="216" r="7" fill="#57cfae" />
    <path d="M527 233a10 10 0 0 1 20 0z" fill="#57cfae" />
    <rect x="494" y="254" width="86" height="8" rx="4" fill="#e6f0ec" />
    <rect x="494" y="270" width="64" height="8" rx="4" fill="#eff8f4" />
    <rect x="494" y="286" width="78" height="8" rx="4" fill="#eff8f4" />
    <rect x="494" y="302" width="56" height="8" rx="4" fill="#eff8f4" />
    <circle cx="512" cy="354" r="17" fill="#e9f8f1" />
    <path
      d="M505 354l5 5 9-10"
      stroke="#16a37b"
      stroke-width="2.6"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <circle cx="562" cy="354" r="17" fill="#fdecec" />
    <path
      d="M556 348l12 12M568 348l-12 12"
      stroke="#ef5a5a"
      stroke-width="2.6"
      stroke-linecap="round"
    />

    <!-- 放大镜：找答案 -->
    <path d="M600 172l36 36" stroke="#0f9b7a" stroke-width="14" stroke-linecap="round" />
    <circle cx="560" cy="132" r="54" fill="#ffffff" stroke="#0f9b7a" stroke-width="8" />
    <circle cx="536" cy="106" r="14" fill="#e7f6f1" opacity="0.9" />
    <rect x="526" y="114" width="68" height="36" rx="18" fill="#ffffff" stroke="#d9efe7" />
    <text x="560" y="138" text-anchor="middle" fill="#12463a" font-size="13" font-weight="700">
      找答案
    </text>

    <!-- 装饰 -->
    <path
      d="M150 104v12M144 110h12"
      stroke="#8fdcbf"
      stroke-width="3"
      stroke-linecap="round"
    />
    <path d="M452 132v10M447 137h10" stroke="#c6ecdd" stroke-width="3" stroke-linecap="round" />
    <circle cx="204" cy="150" r="4" fill="#d3f1e6" />
    <circle cx="470" cy="88" r="5" fill="#d9efe7" />
    <circle cx="612" cy="300" r="6" fill="#d9efe7" opacity="0.8" />
  </svg>
</template>
