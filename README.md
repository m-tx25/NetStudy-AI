# chuangzhibei

传智杯 Web 方向的开发项目，前后端分离。

- **前端**：Vue 3 + Vite + TailwindCSS + Element Plus（单页应用，SSE 流式问答）
- **后端**：Python + FastAPI（JWT 鉴权、Celery + Redis 异步任务、RAG 核心引擎）

## 功能概览

| 模块 | 说明 |
| --- | --- |
| 登录 / 注册 | 表单校验、登录守卫、记住账号、忘记密码、服务协议与隐私政策 |
| 智能问答 | ChatGPT 风格对话界面，SSE 流式返回 + 打字机效果，可随时停止生成 |
| 引用溯源 | 每条回答列出引用的原文片段（文档名、页码、相关度），可点开核对 |
| 知识库管理 | 知识库 CRUD、拖拽多文件上传、解析状态、参与检索开关、重新索引 |
| 账号设置 | 修改昵称 / 用户名 / 邮箱，修改密码（校验当前密码，支持强制重新登录） |
| 其他 | 明暗主题、会话分组与重命名、检索范围与 Top-K 参数、移动端自适应 |

> 前端默认跑在 **Mock 演示模式**（`client/.env.development` 里 `VITE_USE_MOCK=true`），
> 没有后端也能完整体验全部交互。接真实后端时把它改成 `false` 并重启 dev server。
> 后端目前只实现了 `/api/health`，业务接口清单见 [前端接口约定](docs/frontend-api.md)。

## 文档

- [开发报告](docs/development-report.md) — 已完成工作、技术选型、验证记录、已知问题与下一步计划
- [前端接口与 SSE 协议约定](docs/frontend-api.md) — REST 接口、`text/event-stream` 事件格式、数据模型
- [多人协作说明](docs/collaboration.md) — 邀请协作者、保护 `main`、分支/PR 流程、令牌与 SSH 配置
- [前端说明](client/README.md) — 目录结构、功能清单、自检脚本、界面截图

## 项目结构

```
.
├── client/                     前端：Vue 3 + Vite
│   ├── index.html
│   ├── vite.config.js          含 @ 别名、/api 代理、内联 PostCSS(Tailwind)
│   ├── tailwind.config.js
│   ├── .env.development        VITE_USE_MOCK / VITE_API_BASE_URL
│   ├── scripts/                自检脚本（构建产物检查 / 端到端 / 截图）
│   └── src/
│       ├── main.js             入口：Pinia / Router / Element Plus / 主题
│       ├── api/                Axios 封装、SSE 解析、Mock 数据
│       ├── stores/             Pinia：user / chat / knowledge
│       ├── router/             路由表与登录守卫
│       ├── layouts/            AppLayout（侧边栏+主区）、AuthShell（登录注册）
│       ├── components/         chat / knowledge / auth / layout 组件
│       ├── composables/        主题、打字机、侧边栏、协议弹窗
│       ├── utils/              SSE、Markdown、格式化、剪贴板、密码强度
│       └── views/              登录 / 注册 / 问答 / 知识库 / 账号设置 / 404
├── server/                     后端：Python + FastAPI（详见 server/README.md）
│   ├── app/
│   │   ├── main.py             入口、CORS、统一错误处理
│   │   ├── models.py           ORM：用户/知识库/文档/切片/会话/消息/引用
│   │   ├── schemas.py          对外契约（camelCase，与前端 mock.js 对齐）
│   │   ├── tasks.py            Celery 应用与异步任务
│   │   ├── api/                auth / conversations / knowledge_bases / documents / chat / health
│   │   ├── core/               配置、数据库、JWT 与密码哈希
│   │   ├── rag/                RAG 引擎编排与 Prompt 模板
│   │   ├── services/           解析、切片、向量化、检索、大模型、处理流水线
│   │   └── db/seed.py          演示数据（与前端 mock 内容一致）
│   ├── data/                   SQLite 与上传文件（运行时生成，不入版本库）
│   ├── requirements.txt
│   ├── start.ps1               一键启动（自动建 venv、装依赖、生成 .env）
│   └── .env.example            环境变量模板
├── docs/
│   ├── development-report.md
│   ├── frontend-api.md
│   ├── collaboration.md
│   └── screenshots/            界面截图
└── scripts/
    ├── patch-vite-windows.mjs  规避受限环境下 Vite 的 spawn EPERM
    └── verify-connectivity.mjs 前后端连通性自检
```

## 环境要求

- Node.js **≥ 20.19**（推荐 22 / 24 LTS，Vite 8 的最低要求）
- 包管理器：**npm**（前端；请勿使用 pnpm / yarn，以免生成冲突的锁文件）
- Python **≥ 3.11**（后端；推荐 3.12 / 3.14）
- **MySQL 8.0+（后端必需）**：业务数据存储。库不存在时会自动创建
- **智谱 API Key（向量化必需）**：申请 <https://open.bigmodel.cn/>
- Redis（可选）：仅 Celery 异步队列需要；未安装时可让任务在进程内同步执行
- Docker（可选）：可用 `server/docker-compose.yml` 一键起 MySQL + Redis

> 向量库是 **ChromaDB**，纯 Python 实现，无需额外安装服务；
> 数据落在 `server/data/chroma_db/`。

## 安装

```bash
# 前端
cd client
npm install

# 后端（Python，会自动创建 server/.venv 并安装依赖）
cd ../server
.\start.ps1          # Windows；脚本会建虚拟环境、装依赖、生成 .env
```

### 准备 MySQL

```powershell
# 方式一：Docker（推荐，一并起 Redis）
cd server
docker compose up -d mysql redis

# 方式二：官方 Windows 安装包
#   https://dev.mysql.com/downloads/installer/
# 方式三：已有 MySQL 实例，直接改 server/.env 的 MYSQL_* 即可
```

然后把 `server/.env` 里的 `MYSQL_PASSWORD` 与 `ZHIPUAI_API_KEY` 填好。

后端也可手动安装：

```bash
cd server
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
```

根目录的 `package.json` 是**前端便捷入口**（用 `npm --prefix` 转发）：

```bash
npm run install:client   # 安装前端依赖
```

> 后端的依赖与启动统一由 `server/` 目录管理（Python 生态），
> 详细说明见 [server/README.md](server/README.md)。

## 启动开发环境（需要两个终端）

```bash
# 终端 1：后端，http://localhost:3000
cd server
.\start.ps1                       # 自动建 venv / 装依赖 / 启动（含热重载）

# 终端 2：前端，http://localhost:5173
cd client
npm run dev
```

打开 <http://localhost:5173>，Mock 模式下登录页已预填 `demo / 123456`，直接点「登录」
或「一键体验演示账号」即可看到完整问答流程。

### 接入真实后端

前端默认跑在 Mock 模式，不会请求后端。要联调真实接口，编辑 `client/.env.development`：

```ini
VITE_USE_MOCK=false
```

改完**重启前端 dev server** 生效。演示账号 `demo / 123456` 在后端首次启动时自动创建，
数据与 Mock 内容一致，因此切换后界面看到的仍是同一套知识库与文档。

> 想真正生成回答还需在 `server/.env` 填入 `LLM_API_KEY`；
> 未填写时检索与引用溯源正常工作，生成阶段会返回可读的错误提示。

## 常用命令

| 位置 | 命令 | 说明 |
| --- | --- | --- |
| 根目录 | `npm run install:client` | 安装前端依赖 |
| 根目录 | `npm run dev:client` | 只启动前端 |
| 根目录 | `npm run build` | 构建前端到 `client/dist` |
| 根目录 | `npm run check:server` | 后端接口契约自检（需后端已启动） |
| `client/` | `npm run dev` | 启动前端开发服务器 |
| `client/` | `npm run build` | 构建生产包到 `client/dist` |
| `client/` | `npm run preview` | 预览构建结果 |
| `client/` | `npm run check:build` | 检查构建产物（Tailwind 工具类、主题色覆盖） |
| `client/` | `npm run check:e2e` | 无头浏览器端到端自检（需先启动 `npm run dev`） |
| `client/` | `npm run screenshots` | 重新生成 `docs/screenshots` 下的截图 |
| `server/` | `.\start.ps1` | 启动后端（自动建 venv、装依赖、热重载） |
| `server/` | `.\.venv\Scripts\python -m celery -A app.tasks.celery_app worker -l info` | 启动异步 worker（需 Redis） |
| `server/` | `.\start.ps1 -Port 8000` | 指定端口启动 |

## 开发约定

- **接口统一走 `/api/**` 相对路径**，不要写死 `http://localhost:3000`。
  开发期由 Vite 代理转发（见 `client/vite.config.js`），既免跨域，上线换域名也不用改代码。
- 后端端口在 `server/.env` 里改（`PORT=4000`）。
  改了后端端口，记得同步改 `client/vite.config.js` 里的 `proxy.target`。
- `@` 已别名到 `client/src`，import 可以写 `@/components/xxx.vue`。
- 后端新增接口请拆到 `server/app/api/` 下再注册（见 `server/app/main.py` 的路由注册段），
  不要都堆在单文件里；对外字段一律用 camelCase，与前端契约保持一致。
- 后端字段名必须与 `client/src/api/mock.js` 对齐 —— 那是当前唯一的接口契约来源，
  也是 `npm run check:server` 的核对基准。

## 环境适配与自检（本机已配置，协作者可选）

本机在受限环境（DSH）下安装依赖与启动开发服务器时，遇到过两个 `EPERM` 问题。
两处适配都已落地，**普通 Windows / macOS / Linux 环境下无需这些步骤即可正常开发**。

### 1. 依赖缓存 `client/.npmrc`

npm 默认缓存目录在用户目录 `C:\Users\<user>\AppData\Local\npm-cache`，受限环境下
该路径不可写，`npm install` 会直接报 `EPERM`。前端包内放了一份 `.npmrc`：

```ini
cache=.npm-cache
```

相对路径会解析到**包目录内部**（如 `client/.npm-cache`），项目因此自包含。
该目录已被根 `.gitignore` 忽略，不会提交。

### 2. Vite 的 `spawn EPERM` —— `scripts/patch-vite-windows.mjs`

Windows 下 Vite 会执行一次 `exec("net use")` 探测网络驱动器映射；该调用使用管道式
stdio，在禁止命名管道的受限环境中必然抛 `spawn EPERM`，并被 rolldown 当作致命错误，
导致 `vite` / `vite build` 失败（报错栈指向 `optimizeSafeRealPathSync`）。

若遇到该报错，执行：

```bash
cd client
node ../scripts/patch-vite-windows.mjs           # 应用补丁
node ../scripts/patch-vite-windows.mjs --dry-run # 只检查、不写入
```

脚本幂等，会自行定位 `client/node_modules` 下的 Vite 产物；对本机本地磁盘而言
与原始行为完全等价（`windowsNetworkMap` 本为空），不改变构建产物。
**注意：`node_modules` 被删除重装后需要重新执行一次。**

> 该补丁没有挂到 `postinstall`：避免在协作者（可能是 macOS/Linux）的机器上因
> 版本差异导致 `npm install` 整体失败。需要时手动执行即可。

### 3. 后端热重载在受限环境下不可用

`server` 的 `npm run dev` 用 nodemon，其依赖 `pstree.remy` 在导入时会 spawn 一个
带管道 stdio 的子进程，在受限环境下启动即崩（`spawn EPERM`）。此时改用：

```bash
cd server
node src/index.js     # 等价于 npm start，无热重载，但服务功能完全正常
```

在普通环境下 `npm run dev` 可正常使用，无需此替代。

### 4. 连通性自检

前后端起来后，可一键验证链路（不依赖浏览器）：

```bash
node scripts/verify-connectivity.mjs
```

它会检查：后端直连、前端首页、**经 5173 代理访问后端**、SFC 编译、后端 404 处理。
全部通过即表示前后端已打通。

## 协作

分支与 PR 流程见 [docs/collaboration.md](docs/collaboration.md)。简单说：**不要直推 `main`**（已受保护），在 `dec/test-upload` 或自己的功能分支上开发。

---

## 本机环境说明（仅 owner 本机适用，协作者请忽略）

本机安装了 SteamTools（Watt Toolkit）加速器，它会在本机 443 端口做 TLS 中间人，
用自签发的 `SteamTools Certificate` 重新签发 github.com 等域名的证书。
因此 git 默认会报错：

- `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`
- 或 `SSL certificate OpenSSL verify result: unable to get local issuer certificate (20)`

本仓库已在 `.git/config` 中做好以下配置，使 git 能正常访问 GitHub：

- `http.sslBackend = openssl`
- `http.sslCAInfo = <本仓库>/.git-trust/ca-bundle-plus-steamtools.pem`

其中 `.git-trust/ca-bundle-plus-steamtools.pem` 是 git 自带的 CA 根证书包，
加上系统信任库中的 SteamTools 根证书合并而成。该文件属于本机环境适配文件，
已在 `.gitignore` 中忽略，不会提交到仓库。

> 换到其它机器或不再使用加速器时，可执行
> `git config --unset http.sslBackend` 与 `git config --unset http.sslCAInfo` 恢复默认。

> npm 侧不受影响：Node 自带独立的 CA 根证书列表，实测 `registry.npmjs.org` 可正常访问。
> 若日后出现 `UNABLE_TO_VERIFY_LEAF_SIGNATURE`，可设
> `NODE_EXTRA_CA_CERTS=<本仓库>/.git-trust/ca-bundle-plus-steamtools.pem`。
