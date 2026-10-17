// 构建产物自检：确认 Tailwind 工具类确实生成、品牌色覆盖顺序正确
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const dir = join(import.meta.dirname, '..', 'dist', 'assets')
const files = readdirSync(dir).filter((f) => f.endsWith('.css'))
const reports = []

for (const file of files) {
  const css = readFileSync(join(dir, file), 'utf8')
  const at = (needle) => css.indexOf(needle)

  const report = {
    file,
    bytes: css.length,
    checks: {
      'tailwind .bg-brand-light': at('.bg-brand-light') >= 0,
      'tailwind .animate-bounce-dot': at('.animate-bounce-dot') >= 0,
      'tailwind .animate-fade-up': at('.animate-fade-up') >= 0,
      'tailwind .animate-pulse-glow': at('.animate-pulse-glow') >= 0,
      'tailwind .scrollbar-thin': at('.scrollbar-thin') >= 0,
      '深色令牌 --app-canvas': at('--app-canvas') >= 0,
      '首页语义类 .app-muted': at('.app-muted') >= 0,
      '首页语义类 .tech-glass': at('.tech-glass') >= 0,
      '登录态遮罩 --el-mask-color': at('--el-mask-color') >= 0,
      'markdown .markdown-body': at('.markdown-body') >= 0,
      'chat caret .is-streaming': at('.is-streaming') >= 0,
    },
  }

  const epDefault = at('--el-color-primary:#409eff')
  const brand = at('--el-color-primary:#2fd1a6')
  const darkBlock = at('html.dark')
  if (epDefault >= 0 || brand >= 0) {
    report.brandColor = {
      epDefaultAt: epDefault,
      brandAt: brand,
      firstHtmlDarkAt: darkBlock,
      brandAfterEpDefault: brand > epDefault,
      // 品牌色必须出现在 EP 的 html.dark 规则之后，否则深色模式会被 #409eff 覆盖
      brandAfterFirstHtmlDark: brand > darkBlock,
    }
  }

  reports.push(report)
}

console.log(JSON.stringify(reports, null, 2))
