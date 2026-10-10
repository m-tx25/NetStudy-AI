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
      'tailwind .bg-brand': at('.bg-brand') >= 0,
      'tailwind .animate-bounce-dot': at('.animate-bounce-dot') >= 0,
      'tailwind .animate-fade-up': at('.animate-fade-up') >= 0,
      'tailwind .scrollbar-thin': at('.scrollbar-thin') >= 0,
      'dark: arbitrary value #212121': at('#212121') >= 0,
      'markdown .markdown-body': at('.markdown-body') >= 0,
      'chat caret .is-streaming': at('.is-streaming') >= 0,
    },
  }

  const epDefault = at('--el-color-primary:#409eff')
  const brand = at('--el-color-primary:#10a37f')
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
