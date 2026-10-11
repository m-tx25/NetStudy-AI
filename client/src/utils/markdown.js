/**
 * Markdown 渲染：markdown-it + highlight.js。
 * 关闭原始 HTML（html: false）以避免 XSS；代码块自动附带「复制」按钮。
 */
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/common'
import 'highlight.js/styles/github-dark.css'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: false,
})

const defaultLinkOpen =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

// 外链新窗口打开
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const targetIndex = tokens[idx].attrIndex('target')
  const attrs = { target: '_blank', rel: 'noopener noreferrer' }
  for (const [key, value] of Object.entries(attrs)) {
    const index = tokens[idx].attrIndex(key)
    if (index < 0) tokens[idx].attrPush([key, value])
    else tokens[idx].attrs[index][1] = value
  }
  return defaultLinkOpen(tokens, idx, options, env, self)
}

// 代码块：语言标签 + 复制按钮 + 高亮
md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const lang = (token.info || '').trim().split(/\s+/)[0] || 'text'
  const code = token.content
  let highlighted

  if (lang && lang !== 'text' && hljs.getLanguage(lang)) {
    try {
      highlighted = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
    } catch {
      highlighted = md.utils.escapeHtml(code)
    }
  } else {
    highlighted = md.utils.escapeHtml(code)
  }

  return [
    '<div class="code-block">',
    '<div class="code-block__bar">',
    `<span>${md.utils.escapeHtml(lang)}</span>`,
    `<button type="button" class="code-block__copy" data-copy-code="${encodeURIComponent(code)}">复制</button>`,
    '</div>',
    `<pre class="hljs"><code class="language-${md.utils.escapeHtml(lang)}">${highlighted}</code></pre>`,
    '</div>',
  ].join('')
}

/**
 * 流式输出时，未闭合的 ``` 会让 markdown-it 把后续内容当成代码块，
 * 这里临时补一个闭合围栏，让渲染结果稳定。
 */
function closeOpenFences(text) {
  const fences = text.match(/^\s{0,3}```/gm)
  if (fences && fences.length % 2 === 1) return `${text}\n\`\`\``
  return text
}

export function renderMarkdown(text) {
  if (!text) return ''
  try {
    return md.render(closeOpenFences(String(text)))
  } catch (error) {
    // eslint-disable-next-line no-console
    console.warn('[markdown] 渲染失败，降级为纯文本：', error)
    return `<p>${md.utils.escapeHtml(String(text))}</p>`
  }
}

export function escapeHtml(text) {
  return md.utils.escapeHtml(String(text ?? ''))
}

export { md }
