# 应用服务层（后端）

Python + FastAPI，负责业务逻辑，是**前端、大模型与数据库之间的桥梁**。

```
前端 (Vue 3 / 5173)  ──HTTP/SSE──▶  本服务 (FastAPI / 3000)
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              MySQL（业务数据）   ChromaDB（向量）      大模型（生成）
                                        ▲
                                  智谱 embedding-3
                    └────────── Redis ──▶ Celery worker（文档解析与向量化）
```

## 技术亮点

| 能力 | 实现 |
| --- | --- |
| **JWT 鉴权** | `python-jose` 签发无状态令牌；bcrypt 哈希密码；改密码后令牌版本号递增，旧令牌立即失效 |
| **任务队列** | `Celery + Redis` 异步处理文档上传与向量化，避免阻塞 Web 进程；无 Redis 时可切进程内同步执行 |
| **RAG 核心引擎** | LangChain 递归切片、Prompt 拼装、多轮对话记忆、SSE 流式输出、引用溯源 |

## 存储分工（重要）

| 数据 | 存储 | 位置 |
| --- | --- | --- |
| 用户、知识库、文档元信息、会话、消息、引用 | **MySQL** | `chuangzhibei` 库 |
| 切片正文、向量、溯源元数据 | **ChromaDB** | `server/data/chroma_db/` |
| 上传的原始文件 | 文件系统 | `server/data/uploads/` |

**向量不在 MySQL 中。** 两者通过 `knowledge_base_id` / `document_id` 关联，
因此删除文档或知识库时必须同时清理两边 —— 代码里已处理（见
`app/api/documents.py` 与 `app/api/knowledge_bases.py`）。

## 向量方案（与 `rag/` 模块一致）

- **向量模型**：智谱 `embedding-3`，2048 维（`ZhipuAIEmbeddings`）
- **向量库**：ChromaDB 持久化客户端
- **切片**：`RecursiveCharacterTextSplitter`，500 / 50，中文优先分隔符
- **混合检索**：`0.5 × 向量相似度 + 0.5 × 词面命中`（中文 2-gram），
  术语与公式密集的手册类文档下比纯向量更稳
- **NFKC 归一化**：修正 PDF 文本层里的 Unicode 变体字，否则关键词检索会失配

> **DeepSeek 不能用于向量化。** DeepSeek 开放平台只提供文本生成模型，
> 没有 `/embeddings` 接口（请求该端点返回 404）。它的 Key 只能用在生成环节。

未配置 `ZHIPUAI_API_KEY` 时，会退化为 **Chroma 自带的 ONNX 嵌入函数**：
整条链路仍能跑通，但中文检索效果一般。两种模式的向量**不可混用**，
因此集合名带后缀区分（`knowledge_chunks_zhipu2048` / `knowledge_chunks_default`）。

## 支持的文档格式

| 格式 | 解析方式 |
| --- | --- |
| **Word `.docx`** | LangChain `UnstructuredWordDocumentLoader`，失败回退 `python-docx`（含表格） |
| **Markdown `.md` / `.markdown`** | LangChain `UnstructuredMarkdownLoader`，失败回退内置解析（按标题切节） |
| PDF `.pdf` | LangChain `PyPDFLoader`，失败回退 `pypdf`；保留页码 |
| `.txt` `.csv` `.json` `.html` | 内置解析器 |
| `.xlsx` `.xls` `.pptx` | `openpyxl` / `python-pptx`，按工作表与幻灯片分页 |
| `.doc`（旧版） | 纯 Python 无稳定方案，尽力提取并提示另存为 `.docx` |

## 目录结构

```
server/
├── app/
│   ├── main.py                 FastAPI 入口、CORS、统一错误处理
│   ├── models.py               ORM（MySQL）
│   ├── schemas.py              对外契约（camelCase，与前端 mock.js 对齐）
│   ├── tasks.py                Celery 应用与任务
│   ├── api/                    auth / conversations / knowledge_bases / documents / chat / health
│   ├── core/                   配置、MySQL 引擎、JWT 与密码哈希
│   ├── rag/                    RAG 引擎编排与 Prompt 模板
│   ├── services/               解析、切片、向量化、Chroma 检索、大模型、流水线
│   └── db/seed.py              演示数据
├── data/                       ChromaDB、上传文件（运行时生成，不入版本库）
├── verify_capabilities.py      能力自检（无需 MySQL 与 API Key）
├── docker-compose.yml          MySQL + Redis 一键启动
├── requirements.txt
├── start.ps1                   Windows 一键启动
└── .env.example
```

## 快速开始

### 1. 准备 MySQL

库不存在时会自动创建（utf8mb4）。三种方式任选：

```powershell
# 方式一：Docker（推荐，一并起 Redis）
docker compose up -d mysql redis

# 方式二：已装 MySQL 8，直接改 .env 里的 MYSQL_* 即可
# 方式三：官方 Windows 安装包 https://dev.mysql.com/downloads/installer/
```

### 2. 配置并启动

```powershell
cd server
.\start.ps1                      # 自动建 venv、装依赖、生成 .env

# 或手动：
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env      # 然后填写 MYSQL_PASSWORD 与 ZHIPUAI_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

启动后：

- 接口文档（Swagger）：<http://localhost:3000/docs>
- 健康检查：<http://localhost:3000/api/health>
- 演示账号：`demo` / `123456`（首次启动自动创建，数据与前端 mock 一致）

> 本服务**不提供网页**。打开 <http://localhost:3000/> 只会看到 JSON 说明，
> 界面在 <http://localhost:5173/>。

### 3. 自检

```powershell
# 能力自检：Word/Markdown 解析、切片、Chroma 写入检索、MySQL 方言编译
.\.venv\Scripts\python.exe verify_capabilities.py

# 接口契约自检（需服务已启动）
cd ..
npm run check:server
```

## 任务队列

默认走 Celery + Redis：

```powershell
# 终端 1：Web 服务
.\start.ps1

# 终端 2：worker
.\.venv\Scripts\python.exe -m celery -A app.tasks.celery_app worker -l info
```

没有 Redis 时（Windows 官方不提供 Redis 二进制，可用 Docker、WSL 或 Memurai）：

```ini
# .env
CELERY_TASK_ALWAYS_EAGER=true
CELERY_EAGER_ASYNC=true    # 默认值，建议保持
```

此时文档处理在 Web 进程内执行，但**仍然是异步语义**：

| 配置 | 接口行为 | 前端表现 |
| --- | --- | --- |
| `EAGER=true` + `EAGER_ASYNC=true`（推荐） | 立即返回 `status=processing`，解析在后台协程继续 | 显示「解析中」→ 轮询自动变为「已就绪」 |
| `EAGER=true` + `EAGER_ASYNC=false` | 接口内同步等待解析完成，返回时已是 `ready` | 直接显示「已就绪」，看不到解析过程 |

两种模式都**仅适合开发环境**。`/api/health` 的 `queue.mode` 会报告当前处于
`eager-async` / `eager` / `celery` 哪一种。

> 前端已实现状态轮询（`client/src/stores/knowledge.js`）：只要列表中还有
> `pending` / `processing` 的文档，就每 3 秒重新拉取一次，直到全部落到
> 终态或超过 5 分钟。因此异步模式下无需手动刷新页面。
> 端到端验证脚本：`client/scripts/e2e-polling.mjs`。

### 演示解析过程

想直观看到「解析中 → 已就绪」的完整过程，可临时设置：

```ini
PIPELINE_ARTIFICIAL_DELAY_SECONDS=12
```

解析前会先等待 12 秒，便于演示。**生产环境不要设置。**

## 检索参数

```ini
CHUNK_SIZE=500        # 切片长度（对齐 rag/build_db.py）
CHUNK_OVERLAP=50      # 相邻块重叠
TOP_K=5               # 召回数量
SCORE_THRESHOLD=0.2   # 相关度阈值
MEMORY_TURNS=6        # 注入 Prompt 的历史轮数
HYBRID_SEARCH=true    # 混合检索开关
```

**关于阈值的特别说明**：当阈值过滤后结果为空、但库中确有切片时，服务会退化为返回 Top-K。
原因是弱向量模型（如 ONNX 降级模式）下相似度整体偏低，严格套用阈值会导致
「明明传了文档却总说未找到依据」。智谱 embedding-3 下分数通常较高，阈值会正常生效。

## 接口一览

除 `/api/health` 外均需 `Authorization: Bearer <token>`。

| 分组 | 接口 |
| --- | --- |
| 鉴权 | `POST /auth/login`、`POST /auth/register`、`GET /auth/me`、`POST /auth/logout`、`PATCH /auth/profile`、`PUT /auth/password`、`POST /auth/forgot-password` |
| 会话 | `GET/POST /conversations`、`GET/PATCH/DELETE /conversations/{id}`、`GET /conversations/{id}/messages` |
| 知识库 | `GET/POST /knowledge-bases`、`GET/PATCH/DELETE /knowledge-bases/{id}` |
| 文档 | `GET /documents`、`POST /documents/upload`、`GET/PATCH/DELETE /documents/{id}`、`POST /documents/{id}/reindex` |
| 问答 | `POST /chat/stream`（SSE）、`GET /chat/config` |

### SSE 事件格式

```
event: meta      data: {"type":"meta","conversationId":"...","model":"...","retrieved":3}
event: sources   data: {"type":"sources","sources":[{...}]}     ← 先给引用，正文随后
event: delta     data: {"type":"delta","content":"增"}           ← 多次增量
event: done      data: {"type":"done","messageId":"...","usage":{}}
```

出错时推送 `event: error` + `data: {"type":"error","message":"..."}`。

## 常见问题

**启动报「无法连接 MySQL」？** 检查 MySQL 服务是否启动、`.env` 的 `MYSQL_*` 是否正确。
若暂时不想装 MySQL，可临时在 `.env` 设置
`DATABASE_URL=sqlite+aiosqlite:///./data/app.db`（仅用于开发）。

**上传文档后一直停在「解析中」？** 多半是 Redis 没启动而 `CELERY_TASK_ALWAYS_EAGER=false`。
此时接口会把文档标记为 `failed` 并在 `error` 字段写明原因，而不是永远等待。

**回答总是「知识库中未找到相关依据」？** 依次检查：
1. 提问时是否勾选了包含相关文档的知识库；
2. 文档状态是否为 `ready`、是否被停用（停用会从向量库移除）；
3. `/api/health` 的 `vectorStore.embedding.mode` 是否为 `zhipu-embedding-3`；
   降级模式下中文召回能力有限。

**修改了向量模型（如换了维度）？** 旧向量与新模型不在同一空间，必须重建：
删除 `server/data/chroma_db/` 后，对每个文档调用 `POST /documents/{id}/reindex`。

**`server/data/` 要不要提交？** 不要，已在 `.gitignore` 中忽略。
删除后重启会自动重建演示数据（MySQL 中的 `users` 表为空时触发）。
