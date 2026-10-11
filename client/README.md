# RAG 知识问答系统 · 前端

基于 **Vue 3 + Vite + TailwindCSS + Element Plus** 的单页应用（SPA），
负责登录注册、智能问答对话、知识库与文档管理，通过 Axios 与后端异步通信，
并使用 SSE（Server-Sent Events）实现流式回答与打字机效果。

---

## 一、快速开始

```bash
# 1. 安装依赖（在仓库根目录执行，npm --prefix 转发，一次装好 client 与 server）
npm run install:all

# 2. 启动前端
npm run dev:client          # 等价于 npm run dev:client

# 3. 打开 http://localhost:5173
```

> 默认开启 **Mock 演示模式**（`client/.env.development` 中 `VITE_USE_MOCK=true`），
> 不需要后端即可完整体验：登录、流式问答、知识库与文档上传管理都会有模拟数据。
> 要接入真实后端，把 `VITE_USE_MOCK` 改成 `false` 并重启 dev server；
> 同时先启动后端 `npm run dev:server`（默认 `http://localhost:3000`，由 Vite 代理 `/api`）。

生产构建：

```bash
npm run build        # 产物在 client/dist
npm run preview      # 本地预览构建产物
```

---

## 二、技术栈与职责

| 层次 | 选型 | 说明 |
| --- | --- | --- |
| 框架 | Vue 3（Composition API + `<script setup>`） | 单文件组件 |
| 构建 | Vite | 开发服务器 + 生产打包 |
| 样式 | TailwindCSS | 布局、间距、明暗主题（`darkMode: 'class'`） |
| 组件库 | Element Plus | 表单、表格、弹窗、消息提示、上传等 |
| 路由 | Vue Router | History 模式 + 登录守卫 |
| 状态 | Pinia | `user` / `chat` / `knowledge` 三个 store |
| 请求 | Axios | 统一实例、拦截器、Token 注入、错误提示 |
| 流式 | 原生 `fetch` + `ReadableStream` | 解析 `text/event-stream`，支持 POST 与中断 |
| 渲染 | markdown-it + highlight.js | 回答正文 Markdown 渲染、代码高亮与复制 |

---

## 三、目录结构

```
client/
├── index.html
├── vite.config.js            # 别名 @、/api 代理（含 SSE 不缓冲配置）、内联 PostCSS
├── tailwind.config.js        # 主题色 brand、动画、字体
├── .env.development          # VITE_API_BASE_URL / VITE_USE_MOCK / VITE_APP_TITLE
├── .env.production           # 生产默认关闭 Mock
├── scripts/                  # 无需额外依赖的自检脚本（见第八节）
└── src/
    ├── main.js               # 应用入口：Pinia / Router / Element Plus / 图标 / 主题
    ├── App.vue
    ├── style.css             # Tailwind 指令、设计令牌、Markdown 正文、EP 覆盖
    ├── config/index.js       # 环境变量与常量集中出口
    ├── api/
    │   ├── request.js        # Axios 实例、Token、信封解包、401 处理
    │   ├── auth.js           # 登录 / 注册 / 当前用户 / 登出
    │   ├── chat.js           # 会话 CRUD + SSE 流式问答 + 事件归一化
    │   ├── knowledge.js      # 知识库 / 文档 CRUD + 上传
    │   └── mock.js           # 内置 Mock 数据与模拟流式输出
    ├── router/index.js       # 路由表与登录守卫
    ├── stores/
    │   ├── user.js           # 登录态、用户信息
    │   ├── chat.js           # 会话列表、消息、流式状态、检索参数
    │   └── knowledge.js      # 知识库、文档、上传任务
    ├── composables/
    │   ├── useTheme.js       # 明暗主题（写入 html.dark）
    │   ├── useTypewriter.js  # 打字机缓冲队列
    │   └── useSidebar.js     # 移动端侧边栏抽屉
    ├── utils/
    │   ├── sse.js            # SSE 解析器（fetch + ReadableStream）
    │   ├── markdown.js       # Markdown 渲染 + 代码块复制按钮
    │   ├── format.js         # 时间 / 体积 / 分组 / 分数格式化
    │   ├── clipboard.js      # 复制到剪贴板（含降级）
    │   └── notify.js         # 去重的错误提示
    ├── layouts/AppLayout.vue # 侧边栏 + 主区域
    ├── components/
    │   ├── layout/AppSidebar.vue
    │   ├── chat/{ChatHeader,MessageList,MessageItem,MessageInput,KnowledgeSelector}.vue
    │   ├── knowledge/{DocumentTable,UploadDialog}.vue
    │   └── auth/AuthPanel.vue
    └── views/
        ├── LoginView.vue      # 登录
        ├── RegisterView.vue   # 注册
        ├── ChatView.vue       # 智能问答
        ├── KnowledgeView.vue  # 知识库与文档管理
        └── NotFoundView.vue   # 404
```

---

## 四、界面预览

截图位于 [`docs/screenshots`](../docs/screenshots)，由 `npm run screenshots` 自动生成：

| 页面 | 文件 |
| --- | --- |
| 登录 | [`01-login.png`](../docs/screenshots/01-login.png) |
| 注册 | [`02-register.png`](../docs/screenshots/02-register.png) |
| 问答欢迎页 | [`03-chat-welcome.png`](../docs/screenshots/03-chat-welcome.png) |
| 流式生成中（打字机） | [`04-chat-streaming.png`](../docs/screenshots/04-chat-streaming.png) |
| 回答完成 + 引用来源 | [`05-chat-answer.png`](../docs/screenshots/05-chat-answer.png) |
| 知识库管理 | [`06-knowledge.png`](../docs/screenshots/06-knowledge.png) |
| 上传弹窗 | [`07-upload-dialog.png`](../docs/screenshots/07-upload-dialog.png) |
| 深色主题 | [`08-chat-dark.png`](../docs/screenshots/08-chat-dark.png) |

---

## 五、功能一览

### 1. 登录 / 注册
- Element Plus 表单校验（用户名长度、邮箱格式、密码强度、二次确认）。
- 登录成功后写入 Token 与用户信息；401 自动清理并跳回登录页（带 `redirect`）。
- 未登录访问受保护路由会被守卫拦截。

### 2. 智能问答（ChatGPT 风格）
- 左侧会话侧边栏：新建对话、搜索、按「今天 / 最近 7 天 / 更早」分组、重命名、删除。
- 主区域：欢迎页（示例问题快捷入口）→ 消息流。
- 用户消息为右侧气泡，助手回答为左侧全宽 Markdown 正文。
- **流式打字机**：SSE 增量先进入缓冲队列，再按固定节奏吐出，积压越多吐得越快，避免一顿一顿。
- 生成过程中可随时「停止」，已生成的内容保留。
- 每条回答下方展示「引用来源」：文档名、所属知识库、页码、相关度分数、原文片段。
- 代码块带语言标签、语法高亮与一键复制。
- 支持重新生成、复制回答、回到底部、明暗主题切换。

### 3. 知识库与文档管理
- 左侧知识库列表（新建 / 编辑 / 删除），右侧文档表格。
- 拖拽或点击上传，支持多文件、单文件体积校验、重复文件提示、逐个进度条。
- 文档状态：排队中 / 解析中 / 已就绪 / 失败；支持「参与检索」开关与重新索引。
- 按文件名搜索、刷新列表、跳转去提问。

### 4. 检索参数
问答头部「知识库」弹层内可选择参与检索的知识库（多选 / 全选 / 清空），
并调整 **Top-K** 与 **相似度阈值**，方便对比不同召回策略下的回答质量。

---

## 六、环境变量

| 变量 | 开发默认 | 生产默认 | 说明 |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | `/api` | 接口前缀，开发期由 Vite 代理到 `http://localhost:3000` |
| `VITE_USE_MOCK` | `true` | `false` | 是否启用内置 Mock 数据 |
| `VITE_APP_TITLE` | `RAG 知识问答系统` | 同左 | 显示在登录页与侧边栏 |

> 想交付一个「纯前端、点开就能演示」的构建包，把 `client/.env.production` 里的
> `VITE_USE_MOCK` 改成 `true` 再 `npm run build` 即可。

---

## 七、与后端的约定

接口清单、SSE 事件格式、数据模型、错误码约定见 [`docs/frontend-api.md`](../docs/frontend-api.md)。

前端对返回体是宽容的：

- 既支持裸返回 `{ id, name }`，也支持统一信封 `{ code: 0, message: 'ok', data: {...} }`；
- SSE 事件既支持命名事件（`event: delta`），也支持把类型放在数据里（`data: {"type":"delta"}`），
  还兼容 OpenAI 的 `choices[0].delta.content` 写法；
- 若后端没有以 `text/event-stream` 返回，会自动降级为「一次性输出整段回答」。

---

## 八、自检脚本

`client/scripts/` 下有三个**零额外依赖**的脚本（只用 Node 内置能力 + 系统自带 Edge/Chrome），
用于在没有人工点测的情况下验证前端是否真的能跑：

```bash
npm run build          # 生产构建
npm run check:build    # 检查构建产物里 Tailwind 工具类、主题色覆盖是否真的生效
npm run check:e2e      # 端到端：路由守卫 → 流式问答 → 引用来源 → 知识库页（需先启动 dev server）
npm run screenshots    # 自动生成 docs/screenshots 下的界面截图
```

`check:e2e` 会启动无头浏览器、注入登录态、点击欢迎页示例问题、等待 SSE 流结束，
再断言「用户气泡 / Markdown 正文 / 引用来源 / 会话落库 / 主题切换 / 无 console 报错」等 22 项。
当前实测结果：**22/22 通过**。

---

## 九、备注

- 上传体积、支持格式等限制在前端 (`UPLOAD_LIMITS`) 与后端各处各校验一次，后端仍需自行兜底。
- 若后端独立域名部署，请在服务端开启 CORS 并允许 `Authorization` 头；
  流式接口需关闭响应缓冲（Nginx：`proxy_buffering off; X-Accel-Buffering: no`）。
- 前端对 SSE 的解析、中断与异常做了兜底：生成过程中可随时停止，切走会话会自动中断当前流。
- 依赖版本：Vue 3.5 / Vite 8（rolldown 内核）/ TailwindCSS 3.4 / Element Plus 2.x / Pinia 3 / Vue Router 4。
  Vite 8 需要 Node `^20.19.0 || >=22.12.0`（仓库根 `package.json` 的 `engines` 已同步）。
