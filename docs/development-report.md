# 开发报告

**项目**：传智杯 Web 方向参赛项目
**仓库**：https://github.com/m-tx25/chuangzhibei
**开发分支**：`dec/test-upload`
**报告日期**：2026-10-09
**当前阶段**：项目初始化与骨架搭建完成，待接入业务需求

> 说明：本报告记录**实际已完成并经验证**的工作。标注 ⏳ 的条目为尚未完成，标注 ⚠️ 的为已知问题，均未计入已完成成果。

---

## 1. 项目概述

本项目为传智杯 Web 方向参赛作品，采用前后端分离架构：

- 前端负责页面渲染与交互
- 后端提供 REST API
- 两者通过 `/api` 前缀通信，开发环境由 Vite 代理转发，避免跨域配置负担

当前仓库已完成工程骨架搭建，具备可并行开发的目录结构与开发环境，业务功能待赛题要求明确后接入。

---

## 2. 本期完成的工作

### 2.1 仓库初始化与协作基建

| 事项 | 状态 |
| --- | --- |
| Git 仓库初始化，默认分支 `main` | ✅ 完成 |
| 建立开发分支 `dec/test-upload`，作为团队共用开发分支 | ✅ 完成 |
| `main` 分支保护规则集（禁止删除、禁止强推、要求 PR） | ✅ 已启用并验证 |
| `.gitignore`（依赖、构建产物、环境变量、密钥、缓存） | ✅ 完成 |
| 协作流程文档 `docs/collaboration.md` | ✅ 完成 |
| 协作者接入（多人分支协作、合并） | ✅ 完成 |

### 2.2 工程骨架搭建

前端（`client/`）：

- Vue 3 + Vite 工程配置
- 路由（`vue-router`，页面级懒加载）
- 全局状态（`pinia`）示例 store
- 基础布局组件 `App.vue` + 两个示例页面
- 开发代理：`/api` → `http://localhost:3000`
- 路径别名：`@` → `client/src`

后端（`server/`）：

- Express 服务入口
- 健康检查接口 `GET /api/health`
- 全局 404 处理与统一错误处理中间件
- 中间件：`cors`、`express.json()`、`dotenv`
- 环境变量模板 `.env.example`

### 2.3 依赖安装

| 位置 | 包数量 | 说明 |
| --- | --- | --- |
| `server/` | 97 个包 | 已安装并实际运行验证 |
| `client/` | 78 个包 | 已安装，编译级验证 |

锁文件（`package-lock.json`）已提交，保证团队成员安装到一致的依赖版本。

---

## 3. 技术选型

| 层次 | 选型 | 版本 | 选型理由 |
| --- | --- | --- | --- |
| 前端框架 | Vue 3 | 3.5.43 | 组合式 API 上手快，模板语法直观，适合短期赛程 |
| 构建工具 | Vite | 8.3.4 | 冷启动快、热更新及时，开发反馈周期短 |
| 路由 | vue-router | 4.6.4 | Vue 官方路由，页面懒加载开箱可用 |
| 状态管理 | pinia | 3.0.4 | Vue 官方推荐，API 简洁，无需 mutation 样板代码 |
| UI 组件 | Element Plus | 2.14.7 | 组件齐全，表格/表单/弹窗开箱可用 |
| 样式 | TailwindCSS | 3.4.19 | 原子化样式，配合 Element Plus 覆盖主题色 |
| **后端框架** | **FastAPI** | 0.143.0 | 原生异步、自动生成 OpenAPI 文档、Pydantic 校验 |
| **ASGI 服务器** | **uvicorn** | 0.54.0 | FastAPI 官方推荐，热重载方便 |
| **ORM** | **SQLAlchemy（异步）** | 2.1.4 | 2.x 异步引擎配合 aiomysql，模型与迁移路径清晰 |
| **关系型数据库** | **MySQL** | 8.0+ | 业务数据（用户/知识库/文档/会话/消息） |
| **MySQL 驱动** | **aiomysql** | 0.3.2 | 纯 Python 实现，无需编译，新版 Python 也能直接装 |
| **向量库** | **ChromaDB** | 1.5.9 | 纯 Python 持久化向量库，无需额外服务，与 rag 模块一致 |
| **向量模型** | **智谱 embedding-3** | 2048 维 | 与 rag 模块统一；DeepSeek 无 /embeddings 接口，不可用于向量化 |
| **RAG 编排** | **LangChain** | 1.6.9 | 递归字符切片、Document 元数据链路、社区集成 |
| **异步任务队列** | **Celery + Redis** | 5.6.3 / 6.4.0 | 文档解析与向量化耗时较长，需与 Web 进程解耦 |
| **JWT 鉴权** | **python-jose** | 3.5.0 | 无状态令牌签发与校验 |
| **密码哈希** | **bcrypt** | 5.0.0 | 直接调用 bcrypt，不经 passlib（后者版本探测有缺陷） |
| **文档解析** | python-docx / pypdf / openpyxl / python-pptx | — | Word、PDF、Excel、PPT；Markdown 用内置按标题切节 |

---

## 4. 代码结构

```
.
├── client/                    前端：Vue 3 + Vite
│   ├── index.html             页面模板
│   ├── vite.config.js         代理与别名配置
│   ├── package.json
│   └── src/
│       ├── main.js            应用入口，挂载 Router 与 Pinia
│       ├── App.vue            根组件（布局 + 导航）
│       ├── assets/main.css    全局样式
│       ├── router/index.js    路由表
│       ├── stores/app.js      状态示例
│       └── views/
│           ├── HomeView.vue   首页（显示前后端连通状态）
│           └── AboutView.vue  关于页
└── server/                    后端：Node.js + Express
    ├── package.json
    ├── .env.example           环境变量模板
    └── src/index.js           服务入口、健康检查、错误处理
```

---

## 5. 接口清单

后端已实现前端 `client/src/api/*` 依赖的**全部接口**（共 27 个），
字段与 `docs/frontend-api.md` 及 `client/src/api/mock.js` 完全对齐。

| 分组 | 接口 | 数量 |
| --- | --- | --- |
| 鉴权 | `POST /api/auth/login`、`POST /api/auth/register`、`GET /api/auth/me`、`POST /api/auth/logout`、`PATCH /api/auth/profile`、`PUT /api/auth/password`、`POST /api/auth/forgot-password` | 7 |
| 会话 | `GET/POST /api/conversations`、`GET/PATCH/DELETE /api/conversations/{id}`、`GET /api/conversations/{id}/messages` | 6 |
| 知识库 | `GET/POST /api/knowledge-bases`、`GET/PATCH/DELETE /api/knowledge-bases/{id}` | 5 |
| 文档 | `GET /api/documents`、`POST /api/documents/upload`、`GET/PATCH/DELETE /api/documents/{id}`、`POST /api/documents/{id}/reindex` | 6 |
| 问答 | `POST /api/chat/stream`（SSE 流式）、`GET /api/chat/config` | 2 |
| 系统 | `GET /api/health` | 1 |

除 `/api/health` 外均需 `Authorization: Bearer <token>`。

`GET /api/health` 响应示例（在原有字段基础上扩展了自检信息）：

```json
{
  "ok": true,
  "service": "chuangzhibei-server",
  "time": "2026-10-11T08:14:50.462Z",
  "llmConfigured": false,
  "llmModel": null,
  "embeddingMode": "hash-fallback",
  "queue": { "mode": "eager", "available": true, "detail": "任务在进程内同步执行" }
}
```

`llmConfigured` / `embeddingMode` / `queue` 三项是本地跑不通时最常见的原因，
直接暴露可省去翻日志。原字段 `ok` / `service` / `time` 保持不变，前端首页无需改动。

### 5.1 SSE 事件协议

`POST /api/chat/stream` 返回 `text/event-stream`，事件顺序固定：

```
event: meta      data: {"type":"meta","conversationId":"...","model":"...","retrieved":3}
event: sources   data: {"type":"sources","sources":[...]}     ← 先给引用，正文随后
event: delta     data: {"type":"delta","content":"增"}         ← 多次增量
event: done      data: {"type":"done","messageId":"...","usage":{}}
```

响应头带 `Cache-Control: no-cache, no-transform` 与 `X-Accel-Buffering: no` 关闭缓冲。
出错时推送 `event: error` + `data: {"message":"..."}`。每条事件同时带 `event:` 名与
`data.type`，以兼容前端 `normalizeStreamEvent` 的两种解析路径。

---

## 6. 开发与运行环境

| 工具 | 版本 |
| --- | --- |
| Node.js | v24.20.0 |
| npm | 11.19.0（前端统一使用的包管理器） |
| Python | 3.14.6（后端运行环境） |
| Redis | 未安装（Celery 队列的 broker；可用 `CELERY_TASK_ALWAYS_EAGER` 替代） |

### 6.1 环境适配问题一：HTTPS 访问 GitHub 失败

**现象**：`git` 访问 GitHub 报错

- `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`
- 或 `SSL certificate OpenSSL verify result: unable to get local issuer certificate (20)`

**原因**：开发机安装的 SteamTools（Watt Toolkit）加速器在本机 443 端口做 TLS 中间人，以自签发的 `SteamTools Certificate` 重新签发 `github.com` 等域名证书，而 git 的默认证书链不包含该自签根证书。

**处理**：为本仓库配置

- `http.sslBackend = openssl`
- `http.sslCAInfo = <仓库>/.git-trust/ca-bundle-plus-steamtools.pem`

该 CA 包由 git 自带根证书包与系统信任库中的 SteamTools 根证书合并而成，属于**本机环境适配文件**，已加入 `.gitignore`，不进入版本库。换机或停用加速器后可用 `git config --unset` 恢复默认。

### 6.2 环境适配问题二：工作目录权限

**现象**：工具链无法在 `E:\传智杯web` 建立写权限，目录操作被拒绝。

**处理**：为该目录补充当前用户的完全控制权限项（变更前的权限已备份，并提供回滚脚本）。此改动只影响本机该目录，不涉及文件内容与所有者。

---

## 7. 验证记录

### 7.1 后端（Python + FastAPI）

| 序号 | 验证项 | 方法 | 结果 |
| --- | --- | --- | --- |
| 1 | 语法与导入 | `python -m compileall app` + `from app.main import app` | ✅ 全部通过，注册 11 条路由 |
| 2 | 服务启动 | `uvicorn app.main:app --port 3000` | ✅ 启动成功，演示数据自动写入 |
| 3 | 接口契约 | `npm run check:server`（`scripts/verify-backend-contract.mjs`） | ✅ **46/46 通过** |
| 4 | 鉴权 | 错误密码、无 token、重复用户名、用户名过短 | ✅ 分别返回 401 / 401 / 409 / 400 |
| 5 | JWT 与密码 | bcrypt 哈希、token 版本号失效机制 | ✅ 登录签发、改密后旧 token 失效 |
| 6 | 文档全链路 | 上传 txt → 解析 → 切片 → 向量化 → 检索命中 | ✅ 上传后 `status=ready`、`chunks>0`，提问能召回该文档 |
| 7 | 向量检索 | 余弦相似度检索 + 阈值策略 | ✅ 能按知识库范围过滤并返回引用片段 |
| 8 | SSE 协议 | 事件顺序、Content-Type、字段结构 | ✅ `meta → sources → delta → done`，头正确 |
| 9 | 错误码 | 不存在的资源 | ✅ 返回 404（前端有专门文案） |
| 10 | 前后端连通 | 经 Vite 代理 `5173/api/health` | ✅ 返回 FastAPI 响应 |
| 11 | 数据一致性 | 知识库 `documentCount` / `chunkCount` 冗余计数 | ✅ 上传、删除后自动重算 |

### 7.2 前端

| 序号 | 验证项 | 方法 | 结果 |
| --- | --- | --- | --- |
| 12 | 生产构建 | `npm run build` | ✅ 1818 个模块，`✓ built in 946ms` |
| 13 | 构建产物自检 | `npm run check:build` | ✅ 7 项 Tailwind 检查全通过，品牌色覆盖顺序正确 |
| 14 | 开发服务器 | `npm run dev` + 浏览器访问 | ✅ 页面、路由、样式均正常 |

### 7.3 启动方式

```powershell
# 终端 1：后端（Python + FastAPI）
cd server
.\start.ps1                      # 自动建 venv、装依赖、启动，http://localhost:3000

# 终端 2：前端
cd client
npm run dev                      # http://localhost:5173
```

> 后端**不提供网页**：直接打开 <http://localhost:3000/> 只会看到 JSON 说明，
> 接口文档在 <http://localhost:3000/docs>，界面请访问 <http://localhost:5173/>。

前端默认跑 Mock 模式（`client/.env.development` 的 `VITE_USE_MOCK=true`），
要联调真实后端需改为 `false` 并重启 dev server。

---

## 8. 团队协作方式

- **共用开发分支**：`dec/test-upload`，成员直接在该分支开发与推送
- **主干保护**：`main` 已启用规则集，禁止删除、禁止强推、必须经 PR 合入
- **合并节奏**：功能完成后由 `dec/test-upload` 发起 PR 合入 `main`
- **推送前先拉取**：共用分支模式下，推送前必须 `git pull`，避免覆盖他人提交
- **提交信息规范**：采用 Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`）
- **凭据规范**：每人使用自己的账号与令牌，禁止共用账号，禁止将令牌写入仓库

详细操作见 `docs/collaboration.md`。

---

## 9. 已知问题与待确认事项

### 9.1 ✅ 前端端到端验证（已完成）

前端开发服务器已在**普通本地终端**完成端到端验证：`npm run dev` 正常启动，页面可访问，`/api` 代理连通。

> 背景记录：在受控沙箱环境中，Vite 启动与构建会调用子进程探测真实路径并被拦截（`spawn EPERM`），属环境限制而非代码缺陷。因此该项验证改在普通终端完成，结论以上述实测为准。
>
> 生产构建 `npm run build` 已完成：1818 个模块，`✓ built in 946ms`（见 7.2 节）。

### 9.2 ✅ 包管理器已统一为 npm（已解决）

**决定**：**前端**统一使用 **npm**；后端改用 Python 生态（pip / requirements.txt）。

**处理**：已从版本库与磁盘移除 pnpm 产物，仅保留前端 npm 锁文件。

```
client/package-lock.json   （npm，保留）
server/requirements.txt    （Python，取代原 package.json）
```

> 历史问题记录：期间仓库曾同时存在 npm 与 pnpm 两套锁文件（`client/pnpm-lock.yaml`、`client/pnpm-workspace.yaml`、`server/pnpm-lock.yaml`），二者并存会导致依赖版本解析不一致。现已清理完毕。

**团队约定**：前端一律使用 `npm install` / `npm run xxx`，不要运行 `pnpm install` 或 `yarn`，以免重新生成冲突的锁文件；后端依赖统一用 `pip install -r server/requirements.txt` 安装。

### 9.3 ⏳ 测试遗留文件

仓库中存在初始化阶段的测试文件：

- `test.txt'`（0 字节）
- `上传测试.txt`（0 字节）
- `ting.txt`（成员加入测试）

**当前决定：暂不清理**，本次保留现状，待正式开发前统一处理。

### 9.6 说明：一次被放弃的改动

开发过程中曾出现一个"命令面板"页面改动（新增 `client/src/views/CommandPanelView.vue`，并修改 `App.vue` 导航与 `router/index.js` 增加 `/commands` 路由），经验证可正常编译。**该改动已被放弃并从工作区丢弃，未进入版本库**，特此记录以免与后续开发混淆。

### 9.8 ✅ 后端技术栈已切换为 Python + FastAPI（已完成）

**决定**：后端由 Node.js + Express 改为 **Python + FastAPI**，作为「应用服务层」。

**已完成**：

| 能力 | 实现方式 |
| --- | --- |
| JWT 鉴权 | `python-jose` 签发无状态令牌；bcrypt 哈希密码；改密码后令牌版本号递增，旧令牌立即失效 |
| 任务队列 | `Celery + Redis` 异步处理文档解析与向量化；无 Redis 时可切进程内同步执行 |
| RAG 核心引擎 | LangChain 递归切片、Prompt 拼装、多轮对话记忆、SSE 流式输出、引用溯源 |
| 数据持久化 | SQLAlchemy 2.x 异步 + SQLite（向量以 float32 存于切片表，内存中算余弦相似度） |

原 Express 的 `server/src/index.js`、`package.json`、`package-lock.json` 已删除；
根目录 `package.json` 中指向它的脚本（`install:all` / `dev:server`）同步移除。

### 9.9 ⏳ 后端已知限制

1. **未配置 Embedding 服务时检索质量有限**。默认降级为本地字符 n-gram 哈希向量，
   它按**字面重合度**而非语义工作，同义不同词的问法召回差（实测同主题问答相似度仅 0.1 左右，
   真实模型通常在 0.5 以上）。整条链路可跑通，但**生产环境必须配置真实 Embedding 服务**。
   `/api/health` 的 `embeddingMode` 字段会明确报告当前模式。

2. **阈值策略做了退化处理**。因上述降级向量得分整体偏低，若严格套用 `SCORE_THRESHOLD=0.2`
   会把结果全部滤空，出现「明明传了文档却总说未找到依据」。现在的策略是：
   阈值过滤后为空但库中确有切片时，退化为返回 Top-K。真实 Embedding 下阈值会正常生效。

3. **本机未安装 Redis**，`.env` 中暂设 `CELERY_TASK_ALWAYS_EAGER=true`，
   文档处理在 Web 进程内同步执行 —— 功能一致但**仅适合开发环境**。
   装好 Redis 后改为 `false`，并按 `server/README.md` 启动 Celery worker。

4. **前端上传后不轮询文档状态**。`client/src/stores/knowledge.js` 拿到响应后直接把文档
   插入列表，不会再去查询解析进度。因此在**异步队列模式**下，上传后文档会一直显示「解析中」，
   直到手动刷新页面；同步（eager）模式下响应返回时已完成解析，不受影响。
   若要支持异步，需要前端补一个轮询或让后端支持 WebSocket/SSE 推送进度。

5. **`/api/auth/forgot-password` 未接真实邮件服务**，当前始终返回成功
   （不暴露账号是否存在），重置令牌的投递逻辑留空待接。

### 9.10 ✅ 后端架构调整：MySQL + ChromaDB + 智谱向量（已完成）

按协作方新提交的 `rag/` 模块（`a1f48dd`）与开发要求，对后端做了三项改造。

**1）向量改用 `rag/` 模块的方案**

| 方面 | 改造前 | 改造后 |
| --- | --- | --- |
| 向量库 | 自实现：向量存 MySQL BLOB，numpy 全量算余弦 | **ChromaDB 持久化客户端** |
| 向量模型 | 本地字符 n-gram 哈希降级 | **智谱 embedding-3（2048 维）**，未配 Key 时降级为 Chroma 内置 ONNX 模型 |
| 检索 | 纯向量 | **混合检索**：0.5×向量相似度 + 0.5×词面命中（中文 2-gram） |
| 切片 | 512 / 64 | **500 / 50**（对齐 `rag/build_db.py`） |
| 文本归一化 | 无 | **NFKC 归一化**，修正 PDF 文本层的 Unicode 变体字 |

在协作者实现基础上做了三点生产化改造：
- 用**单一集合 + 元数据过滤**实现多用户隔离（他的脚本是单文件单集合，无 owner 概念），
  且 `owner_id` 在向量库层面过滤，构成安全边界；
- 集合名带向量空间后缀（`knowledge_chunks_zhipu2048` / `_default`）——
  不同 embedding 模型的向量不可混用，Chroma 在集合创建时即固定维度；
- 文档停用/删除时同步从向量库移除，避免检索到已失效内容。

**2）关系型数据库改为 MySQL**

- 驱动选 **aiomysql**（纯 Python，无需编译；`asyncmy` 在新版 Python 上装不上）；
- 库不存在时**自动创建**（utf8mb4），并预先校验所有索引列长度 ≤255
  （utf8mb4 下索引键上限 3072 字节，不存在 "Specified key was too long" 风险）；
- 连接失败时给出可读中文报错与 4 条排查项，而不是裸驱动异常；
- `Chunk` 表已移除（向量不再存关系库），现有 7 张表。

**3）文档解析支持 Word 与 Markdown**

- **Word `.docx`**：LangChain `UnstructuredWordDocumentLoader` → 回退 `python-docx`
  （含段落、标题层级与**表格**）；
- **Markdown `.md` / `.markdown`**：LangChain `UnstructuredMarkdownLoader` → 回退内置
  **按标题切节**；
- 解析层统一返回 LangChain `Document`，页码等元数据沿「加载 → 切片 → 入库」链路保留，
  检索命中后可溯源到具体页。

> **刻意不安装 `unstructured`**：它依赖 `langdetect`，后者只有源码分发包、没有 wheel，
> 在 Python 3.14 上需现场编译并会导致 `pip install` 长时间卡死（实测）。
> 去掉后所有依赖都有预编译 wheel，安装顺利，解析层的回退实现已覆盖需求。

**验证结果**

| 验证项 | 结果 |
| --- | --- |
| 能力自检 `verify_capabilities.py` | ✅ **33/33 通过** |
| Word 解析（段落 + 表格） | ✅ 表格内容未丢失 |
| Markdown 解析（按标题切节） | ✅ 切成 3 节 |
| ChromaDB 写入 → 检索 → 删除 | ✅ Top-1 命中正确片段（相似度 0.7059），含文档名与页码 |
| 跨用户隔离 | ✅ 他人检索结果为 0 条 |
| 知识库范围过滤 | ✅ 范围外命中 0 条 |
| 接口契约 `npm run check:server` | ✅ **46/46 通过** |
| MySQL 方言编译 DDL | ✅ 7 张表，索引列长度安全 |
| MySQL 不可达时的报错 | ✅ 可读中文提示，含排查项 |
| 应用启动 + 演示数据 | ✅ 3 知识库 / 8 文档 / 32 切片写入 ChromaDB |

**未验证项（本机环境限制）**：本机**未安装 MySQL**（服务、3306 端口、安装目录均不存在），
因此 MySQL 的**真实连接与读写未实测**。上述契约验证是在 `DATABASE_URL` 临时指向
SQLite 的前提下完成的（仅验证用途，不改动 `.env` 默认配置）。
装好 MySQL（`docker compose up -d mysql`）后即可用同一套脚本复验。

### 9.11 ✅ 修复：异步解析下前端状态不更新（已完成）

**问题**：后端在异步队列模式下，上传接口只返回 `status=processing`，真正的解析与向量化
由后台完成；而前端拿到响应后**不再查询**，导致列表一直停在「解析中」，
必须手动刷新页面才能看到真实状态。连带影响：「重新索引」按钮在
`row.status === 'processing'` 时被禁用，用户在刷新前无法操作该文档。

**修复（前端）**：在 `client/src/stores/knowledge.js` 增加状态轮询 ——

- 只要列表中还有 `pending` / `processing` 的文档，每 3 秒重新拉取一次；
- 全部落到终态（`ready` / `failed`）后自动停止；超过 5 分钟或连续 3 次请求失败也会停止；
- 切换知识库、重置状态时停止轮询，避免对不可见知识库持续请求；
- 轮询内部使用会抛错的 `fetchDocuments`，对外 `loadDocuments` 保持原有
  「失败只提示、不抛错」语义，不影响既有调用方；
- 上传与重新索引若返回非终态，则自动开启轮询。

**顺带修复（后端）**：本地无 Redis 时的 `CELERY_TASK_ALWAYS_EAGER=true` 原本在
**请求内同步等待**解析完成，响应返回时已是 `ready` —— 导致本地开发根本复现不出
「解析中」，与生产（Redis + worker）行为不一致，也让轮询逻辑无处生效。
新增配置 `CELERY_EAGER_ASYNC`（默认 `true`）：eager 模式下改为后台协程异步执行，
接口立即返回 `processing`。这样**无需 Redis 也能得到与生产一致的异步语义**。

另新增 `PIPELINE_ARTIFICIAL_DELAY_SECONDS`（默认 0）用于演示与验证解析过程。

**验证**：新增端到端脚本 `client/scripts/e2e-polling.mjs`（基于项目已有的 CDP 无头方案），
**17/17 通过**：

| 断言 | 结果 |
| --- | --- |
| 上传后处于「解析中」 | ✅ |
| **不刷新页面，状态自动变为「已就绪」** | ✅ |
| 轮询确实发出文档列表请求 | ✅ 解析期间 5 次 |
| 「重新索引」按钮恢复可用 | ✅ 解析中 `disabled=true` → 就绪后 `false` |
| 到达终态后停止轮询 | ✅ 就绪后 0 次多余请求 |
| 页面未被刷新（单页状态保持） | ✅ |

同时更新了 `scripts/verify-backend-contract.mjs` 以适配异步语义（上传与重新索引后
轮询等待就绪），接口契约回归 **48/48 通过**。

### 9.4 ⏳ 尚未引入的工程化能力

以下均未配置，按需引入：

- 代码规范：ESLint / Prettier（前端）、Ruff（后端）
- 前后端一键启动：`concurrently` 或根目录脚本
- 单元测试：Vitest（前端）、pytest（后端）
- CI：GitHub Actions
- 数据库迁移：Alembic（当前用 `create_all` 建表，字段变更需手工处理或删库重建）

### 9.5 ✅ 业务需求已接入（后端）

原先「只有示例页面与健康检查接口」的状态已结束：后端已实现前端依赖的全部 27 个接口
（鉴权、会话、知识库、文档、流式问答），并跑通「上传 → 解析 → 切片 → 向量化 → 检索 → 引用」
完整链路，详见 5 节与 7.1 节。

### 9.7 说明：功能分支尚未合并进 `main`

`main` 目前仍停留在初始化提交 `ff1db8a`，`client/`、`server/`、`docs/` 全部位于开发分支 `dec/test-upload`。因此直接打开仓库首页看到的是空壳。

**当前决定：暂不合并**，待开发阶段告一段落后再由 `dec/test-upload` 发起 PR 合入 `main`。

---

## 10. 下一步计划

| 优先级 | 事项 | 状态 |
| --- | --- | --- |
| ~~高~~ | ~~统一包管理器，清理多余锁文件~~ | ✅ 已完成（见 9.2） |
| ~~高~~ | ~~前端端到端验证~~ | ✅ 已完成（见 9.1） |
| 高 | 明确赛题需求，梳理功能模块与页面清单 | ⏳ 待办 |
| 中 | 设计数据模型与接口契约 | ⏳ 待办 |
| 中 | 按模块实现业务功能 | ⏳ 待办 |
| 中 | 引入 ESLint + Prettier 统一代码风格 | ⏳ 待办 |
| 中 | 前端生产构建 `npm run build` 验证 | ⏳ 待办 |
| 低 | 清理测试遗留文件（见 9.3） | ⏳ 待办 |
| 低 | 将 `dec/test-upload` 合入 `main`（见 9.7） | ⏳ 待办 |
| 低 | 配置 CI 与自动化测试 | ⏳ 待办 |

---

## 附录：提交记录（本期）

| 提交 | 说明 |
| --- | --- |
| `55e352d` | feat: 搭建前后端项目骨架 |
| `9c771a1` | Merge：合入协作者提交 |
| `d902aec` | 协作者提交（婷 已加入） |
| `7b3bd75` | docs: 新增开发报告，README 补充文档索引 |
| `1402a8e` | 提交并推送 pnpm 锁文件（后已在本次统一包管理器时移除） |

> 更早的初始化提交见 `git log`。
