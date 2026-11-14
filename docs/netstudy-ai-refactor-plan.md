# NetStudy-AI 整改方案（v1 草案）

> 目标：把当前「RAG 知识库问答系统」升级为「AI 学术文献助手平台」。
> 原则：**不重写、先复用**；P0 先跑通；每个任务有验收标准。
> 本文基于 `dec/test-upload @ a816c58` 的实际代码盘点，不是凭空设计。

---

## 0. 结论摘要

| 维度 | 现状 | 目标 | 差距 |
|---|---|---|---|
| 文献来源 | 只能上传本地文件 | 外部数据库检索 + 上传 | **完全缺失**（M1） |
| 文献管理 | 知识库/文档树 | 个人文献库（分类/标签/状态/笔记/引用） | **部分**（有文档管理，无文献语义）（M2） |
| 解析 | 多格式文本 + 页码 | 章节/元数据/表格/图表/参考文献结构化 | **部分**（只有文本+页码）（M3） |
| 单篇分析 | 通用问答 | 10 类结构化分析 + 引用锚点 | **缺失**（M4） |
| 多篇对比 | 无 | 维度矩阵 + 引用 | **完全缺失**（M5） |
| 溯源问答 | 有片段引用+页码+无依据标注 | 引用编号、可跳转、严格模式 | **部分**（M6） |
| 研究辅助 | 无 | 综述/gap/提纲 | **缺失**（M7） |
| 平台化 | 团队/密钥/任务已有 | 配额、监控、审计、共享库 | **部分**（M8） |

**最重要的判断**：现有代码里最值钱的三块资产是 ①团队+权限+密钥体系 ②文档解析/切片/向量化流水线 ③带页码引用的流式 RAG 引擎。整改应当**包住**它们，而不是替换它们。

---

## 1. 现状盘点

### 1.1 技术栈

- 前端：Vue 3 + Vite 8 + Pinia + Element Plus + Tailwind，`client/`
- 后端：FastAPI + SQLAlchemy 2 async + Celery + ChromaDB，`server/`
- 向量：智谱 `embedding-3`（2048 维），未配 Key 时降级为离线 n-gram 哈希（512 维）
- 生成：OpenAI 兼容 `/chat/completions`（DeepSeek / 智谱 / 任意兼容服务）
- 数据库：开发用 SQLite，生产 MySQL（`DATABASE_URL` 切换）

### 1.2 后端现有模块

```
server/app/
├─ api/            auth conversations documents knowledge_bases teams keys chat health
├─ services/       parser chunking pipeline vectorstore embeddings llm keyring access diagnostics
├─ rag/            engine prompts
├─ core/           config database security secrets
├─ db/             seed
├─ models.py       users / knowledge_bases / documents / conversations / messages /
│                  message_sources / teams / team_members / team_join_requests / api_keys
├─ schemas.py      全部 Pydantic 契约（camelCase 输出）
└─ tasks.py        Celery 任务：process_document
```

关键能力（已实现，可复用）：

| 能力 | 位置 | 说明 |
|---|---|---|
| 多格式解析 | `services/parser.py` | pdf/docx/md/pptx/xlsx/html/csv/json，PDF 保留页码 |
| 切片 | `services/chunking.py` | 500/50，中文标点优先，保留 page/source 元数据 |
| 向量化+入库 | `services/pipeline.py`、`vectorstore.py` | 批量 upsert、按 owner/team/kb 过滤、混合检索 |
| 异步任务 | `tasks.py` | Celery eager / Redis 两种模式 |
| 流式 RAG | `rag/engine.py` | 检索→证据门槛→生成→引用快照→降级抽取 |
| 引用快照 | `models.MessageSource` | 页码 + 片段 + 文档名，历史回答可追溯 |
| 权限 | `services/access.py`、`teams.py` | 个人库/团队库，角色 owner/admin/member |
| 密钥 | `services/keyring.py`、`api/keys.py` | 用户/团队级密钥，加密存储，按归属解析 |

**没有的**：外部检索、DOI/作者检索、文献库语义、章节识别、元数据抽取、参考文献、图表、结构化分析、多篇对比、引用导出、限流、外部缓存。

### 1.3 前端现有页面

```
views/  HomeView  LoginView  RegisterView  ChatView  KnowledgeView  TeamsView  SettingsView  AboutView  NotFoundView
stores/ app  chat  knowledge  team  user
```

没有检索页、文献库页、论文详情页、对比页。

### 1.4 现有 RAG 数据流

```
上传 → documents(status=processing) → Celery → parser 解析成 LangChain Document(page)
     → chunking 切片 → Chroma upsert(owner_id/team_id/kb_id/document_id/page_label)
     → documents.status=ready

提问 → engine.stream_answer → vectorstore.search(owner/team/kb 过滤, 混合打分)
     → 证据门槛(RAG_MIN_LEXICAL_SCORE=3 或 向量≥0.85) → 有依据则严格 RAG / 无依据则模型兜底
     → SSE(meta/sources/delta/done) → message + message_sources 落库
```

这条链路是 M4/M5/M6 的地基，**改造点是在 chunk 元数据里加 `section` 与 `paper_id`，而不是重写引擎**。

---

## 2. 八个模块与依赖

### 2.1 模块清单

| 编号 | 模块 | 优先级 | 现状 |
|---|---|---|---|
| M1 | 学术文献检索（外部数据源） | P0 | 缺失 |
| M2 | 个人文献管理系统 | P0 | 部分（文档管理） |
| M3 | 论文智能解析 | P0 | 部分（纯文本） |
| M4 | 单篇论文智能分析 | P0 | 缺失 |
| M5 | 多篇论文对比 | **P0+（核心竞争力）** | 缺失 |
| M6 | 学术问答与引用溯源 | P0+（核心竞争力） | 部分 |
| M7 | 研究辅助（综述/gap/提纲） | P1 | 缺失 |
| M8 | 平台化（团队共享/配额/监控） | P1 | 部分 |

### 2.2 依赖关系

```
M1 检索 ──► M2 文献库 ──► M3 解析 ──► M4 单篇分析 ──► M5 多篇对比
                    │                        │
                    └──────────► M6 溯源问答 ◄┘
                                     │
                                     ▼
                              M7 研究辅助
M8 平台化：横切所有模块（鉴权/配额/任务/缓存/审计）
```

**避免重复开发的三条硬约束**：

1. 外部论文与上传 PDF 共用同一套 `papers` 元数据模型，禁止两套结构。
2. 解析产物（章节/切片）只存一份，M4/M5/M6 都从它取数，不做各自的“再解析”。
3. 引用只用 `message_sources` / `analysis_citations` 一套结构（document_id + page + chunk_id + snippet），前端只写一个 `CitationChip` 组件。

---

## 3. 逐模块设计

## M1 学术文献检索系统（P0）

### 现状与差距

- 现有 `vectorstore.search` 只检索**自己库里的切片**，不是互联网学术检索。
- 无任何外部 API 客户端、无统一结构、无限流、无缓存。

### 目标结构

```
server/app/literature/
├─ dto.py          PaperDTO / AuthorDTO / SearchQuery / SearchPage（统一结构）
├─ base.py         PaperSource 协议：search / get / get_by_doi / related
├─ sources/
│   ├─ openalex.py        主力（覆盖广、免费、支持过滤与引用数）
│   ├─ crossref.py        DOI 精确查询 + 元数据补全
│   ├─ arxiv.py           预印本 + PDF 直链
│   └─ semantic_scholar.py（可选，需 API Key，引用/相关推荐强）
├─ aggregator.py   并行 fan-out、去重、排序、分页、部分失败降级
├─ cache.py        Redis TTL 缓存（无 Redis 时进程内 LRU）
├─ ratelimit.py    按数据源令牌桶
└─ normalize.py    标题归一化、DOI 归一化、作者解析
```

### 统一 DTO（前后端唯一契约）

```python
class PaperDTO(BaseModel):
    id: str                  # "openalex:W123" / "crossref:10.xxx"
    source: str
    source_id: str
    doi: str | None
    title: str
    abstract: str | None     # OpenAlex inverted index 还原
    authors: list[AuthorDTO] # name / affiliation / orcid
    venue: str | None        # 期刊或会议
    year: int | None
    cited_by: int | None
    fields: list[str]        # 研究领域
    open_access: OaInfo      # is_oa / pdf_url / landing_url
    url: str | None
    type: str                # article / preprint / review
```

### 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/literature/search` | `q`、`author`、`doi`、`yearFrom/To`、`venue`、`field`、`source`、`sort`、`page/pageSize` |
| GET | `/api/literature/papers/{source}/{sourceId}` | 单篇详情（多源补全） |
| GET | `/api/literature/papers/{source}/{sourceId}/related` | 相关论文 |
| GET | `/api/literature/sources` | 数据源列表与健康状态 |

### 数据表

> 以下为字段级示意，实际类型以 SQLAlchemy 映射为准；检索走 `LIKE`/`lower(title)`，
> 不依赖 MySQL FULLTEXT（SQLite 开发环境不支持），大规模再上 FTS。

```sql
papers(id PK, source, source_id, doi, title, abstract, authors_json, venue, year,
       cited_by, fields_json, oa_status, pdf_url, landing_url, type, created_at,
       UNIQUE(source, source_id), INDEX(doi), INDEX(year), INDEX(title))
search_logs(id, user_id, query_json, sources, result_count, latency_ms, created_at)
external_cache(cache_key PK, source, payload, expires_at)   -- 无 Redis 时兜底
```

### 任务拆解

| 任务 | 文件 | 验收标准 |
|---|---|---|
| T1.1 DTO + 协议 + 注册表 | `literature/dto.py`、`base.py` | 单测：DTO 序列化 camelCase；注册表可按名取源 |
| T1.2 OpenAlex 适配器 | `sources/openalex.py` | 关键词检索返回 ≥20 条；inverted index 正确还原摘要 |
| T1.3 Crossref 适配器 | `sources/crossref.py` | DOI 精确查询命中率 100%（10 个样例 DOI） |
| T1.4 arXiv 适配器 | `sources/arxiv.py` | Atom 解析出标题/作者/摘要/PDF 链接 |
| T1.5 聚合器 | `aggregator.py` | 3 源并行；单源 3s 超时不拖垮整体；DOI 去重 |
| T1.6 缓存 + 限流 | `cache.py`、`ratelimit.py` | 同查询 10min 内二次请求 <200ms；超限返回 429 并带重试秒数 |
| T1.7 检索 API | `api/literature.py` | `curl` 可检索；分页正确；错误结构化 |
| T1.8 前端检索页 | `views/SearchView.vue`、`components/search/*` | 输入关键词出结果卡片；筛选生效；加载/空/错误态完整 |
| T1.9 单测 | `tests/test_literature.py` | respx 模拟三源响应，覆盖去重/超时/降级 |

**性能要求**：无缓存 P95 < 2s；缓存命中 < 200ms；最多并发 3 个源。

---

## M2 学术文献管理系统（P0）

### 现状与差距

已有：知识库 CRUD、文档上传（去重、批量删除、重索引、状态机）、个人/团队归属、上传者记录。
缺：文献语义（作者/年份/DOI/期刊）、分类、标签、阅读状态、阅读进度、笔记、引用导出、外部论文收藏入口。

### 设计原则

**不新建平行体系**：`papers` 管元数据，`documents` 管实体文件与 RAG 切片，`library_items` 把两者绑到用户身上。

```
papers 1 ── 0..1 documents（有 PDF 才有）
   └──────── n library_items（每个用户一条，可重复收藏不同人的库）
```

### 数据表

```sql
library_items(id, user_id, paper_id NULL, document_id NULL, collection_id NULL,
              status ENUM(unread, reading, read), progress INT, last_read_at,
              note TEXT, added_at, UNIQUE(user_id, paper_id), INDEX(user_id, status))

collections(id, user_id, name, parent_id NULL, sort, created_at)
tags(id, user_id, name, color, UNIQUE(user_id, name))
paper_tags(library_item_id, tag_id, PRIMARY KEY(library_item_id, tag_id))
notes(id, library_item_id, page, content, created_at)
```

### 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/library/items` | 收藏外部论文（body=PaperDTO），已存在返回已有项 |
| POST | `/api/library/items/upload` | 上传 PDF 并建库（复用现有 upload 管线） |
| GET | `/api/library/items` | 过滤：status/tag/collection/q |
| PATCH | `/api/library/items/{id}` | 状态、进度、分类、标签、笔记 |
| DELETE | `/api/library/items/{id}` | 解绑（可选同时删文档） |
| GET/POST/PATCH/DELETE | `/api/library/collections` | 分类树 |
| GET/POST/DELETE | `/api/library/tags` | 标签 |
| GET | `/api/library/items/{id}/citation?format=bibtex\|ris\|apa\|gbt7714` | 引用导出 |

### 任务拆解

| 任务 | 文件 | 验收 |
|---|---|---|
| T2.1 建表 + 迁移 | `models.py`、`database.py` | 启动自动建表；SQLite/MySQL 均可 |
| T2.2 收藏导入 | `api/library.py`、`services/library.py` | 从检索页一键收藏；重复 DOI 返回已有项 |
| T2.3 上传绑定 | 复用 `api/documents.py` | 上传后 library_item 自动关联 document |
| T2.4 分类/标签 | `api/library.py` | 增删改查；树形分类不超过 3 层 |
| T2.5 阅读状态/笔记 | 同上 | 状态流转正确；笔记带页码 |
| T2.6 库内搜索 | `services/library.py` | 标题/作者/摘要/标签模糊搜索；P95<300ms（1 万条） |
| T2.7 去重 | `normalize.py` | DOI 优先，其次标题归一化+年份；重复率抽检 100% |
| T2.8 引用导出 | `services/citation.py` | BibTeX 可被 Zotero 导入；4 种格式 |
| T2.9 前端文献库 | `views/LibraryView.vue` | 列表/筛选/分类树/详情抽屉 |

---

## M3 论文智能解析（P0）

### 现状与差距

已有：PDF 文本 + 页码、docx 标题层级与表格、切片、向量化。
缺：章节识别、元数据抽取、参考文献、表格/图片抽取、解析质量校验、章节感知切片。

### 改造点（尽量增量）

```
parser.py（保持）
  └─ sectionizer.py（新）  文本→章节（Abstract/Intro/Related/Method/Experiment/Conclusion/References）
  └─ metadata.py（新）    首页文本 + Crossref 补全 → 标题/作者/DOI/年份/机构
  └─ references.py（新）  References 段→逐条参考文献→DOI 匹配
  └─ assets.py（新，P1）  表格（pdfplumber）、图片（PyMuPDF）→ 文件 + caption
chunking.py（改）          每块带 section / heading / page_start / page_end / paper_id
pipeline.py（改）          解析→结构化→切片→入库→回填统计，全过程记录质量指标
```

### 数据表

```sql
paper_sections(id, document_id, section_type, heading, ordinal, page_start, page_end, text)
paper_assets(id, document_id, kind ENUM(table,figure), page, caption, storage_path, bbox_json)
paper_references(id, document_id, ordinal, raw_text, doi, title, year, matched_paper_id)
document_quality(document_id, char_count, page_count, section_count, garbage_ratio, warnings_json)
```

### 任务拆解

| 任务 | 文件 | 验收 |
|---|---|---|
| T3.1 章节识别 | `services/sectionizer.py` | 3 篇样例（中/英）识别出 ≥5 个标准章节，准确率抽检 ≥85% |
| T3.2 元数据抽取 | `services/metadata.py` | 标题/作者/年份/DOI 四项，抽样 10 篇命中 ≥8 |
| T3.3 参考文献解析 | `services/references.py` | 逐条切分；DOI 可回查 Crossref |
| T3.4 章节感知切片 | `chunking.py`、`vectorstore.py` | chunk metadata 含 section/page_start/page_end；检索可按 section 过滤 |
| T3.5 解析校验 | `services/quality.py` | 失败/缺章节/乱码给出可读原因，前端可见 |
| T3.6 异步任务与进度 | `tasks.py`、`api/documents.py` | 解析进度可轮询；超时可重试 |
| T3.7 解析结果页 | `views/PaperView.vue`（解析 tab） | 章节树可点击跳页；表格/图片列表（P1） |

---

## M4 单篇论文智能分析（P0）

### 现状与差距

已有：流式问答、引用片段、页码。
缺：10 类结构化分析、章节级检索、分析结果缓存与版本、引用强约束。

### 设计

```
POST /api/papers/{documentId}/analysis/{kind}/stream   SSE
kind ∈ summary | background | question | method | pipeline |
       innovation | results | limitations | glossary
另：POST /api/papers/{documentId}/chat/stream           论文范围问答
```

Prompt 约束（关键）：

1. 只允许使用 `paper_sections` 中检索到的原文，逐条给 `[cite:chunk_id]`；
2. 找不到证据的断言必须写「原文未提及」，禁止外推；
3. 输出结构固定（Markdown + 引用数组），便于前端渲染与校验。

### 数据表

```sql
analyses(id, document_id, kind, model, status, content_md, citations_json,
         prompt_tokens, completion_tokens, created_at, updated_at,
         UNIQUE(document_id, kind, model))
```

### 任务拆解

| 任务 | 文件 | 验收 |
|---|---|---|
| T4.1 分析服务 + 9 类模板 | `services/analysis.py`、`rag/prompts_analysis.py` | 每类输出结构正确，含 ≥3 条引用 |
| T4.2 章节级检索 | `vectorstore.search` 加 section 过滤 | 指定 chapter 后只召回该章节 |
| T4.3 引用强约束 | `analysis.py` 校验器 | 无引用的“事实句”比例 <10%（抽检 30 条） |
| T4.4 流式 + 缓存 | `api/papers.py` | 二次打开同分析 <200ms（缓存命中） |
| T4.5 前端分析面板 | `components/paper/AnalysisPanel.vue` | 9 个 tab、流式渲染、引用可跳页 |
| T4.6 质量评估 | `tests/verify_analysis.py` | 3 篇论文人工评分表，平均 ≥4/5 |

---

## M5 多篇论文对比（P0+ 核心竞争力）

### 设计

- 选择 2–5 篇（同一 `knowledge_base` 或同一 `collection`）
- 维度固定 + 自定义：研究问题、方法、数据集、评价指标、主要结果、创新点、局限
- 输出：**结构化矩阵 JSON**（前端渲染表格）+ 叙述性总结（带引用）
- 每个单元格必须带 `document_id + page + snippet`，点击跳原文

### 接口

```
POST /api/comparisons               创建（papers[], dimensions[]）→ id
POST /api/comparisons/{id}/stream   流式生成矩阵与总结
GET  /api/comparisons/{id}          结果（缓存）
GET  /api/comparisons?paperId=      历史对比
```

### 数据表

```sql
comparisons(id, user_id, title, paper_ids_json, dimensions_json, matrix_json,
            summary_md, model, status, created_at)
```

### 任务拆解

| 任务 | 验收 |
|---|---|
| T5.1 对比服务（逐单元格检索+生成） | 3 篇 × 6 维，每格有引用，<60s |
| T5.2 矩阵渲染 | 表格横向滚动、单元格可展开引用、导出 Markdown/CSV |
| T5.3 一致性校验 | 同一维度跨论文用同一评判口径（prompt 固定 schema） |
| T5.4 叙述总结 | 生成对比结论，引用覆盖 ≥80% 单元格 |

---

## M6 学术问答与引用溯源（P0+）

### 现状

已有：`message_sources` 快照（chunk/document/page/snippet）、无依据横幅、严格 RAG 分支。
缺：论文范围问答、引用编号与跳转、引用覆盖率指标、严格模式开关。

### 改造

1. `stream_answer` 增加 `document_ids` 过滤（复用 `knowledge_base_ids` 同款参数）。
2. SSE `sources` 增加 `index`（[1][2]）与 `anchor`（page + bbox）。
3. 前端 `CitationChip`：点击滚动到 PDF 对应页并高亮段落。
4. 新增指标：`evidence_coverage = 有引用句子 / 总句子`，低于阈值在 UI 提示。

### 任务

| 任务 | 验收 |
|---|---|
| T6.1 论文范围问答 | 指定单篇后只召回该篇；跨篇不串 |
| T6.2 引用编号 + 锚点 | 每条引用可定位页码；断链率 0 |
| T6.3 严格模式 | 无证据时明确回答“原文未提及”，不调用模型自由发挥 |
| T6.4 覆盖率提示 | 回答尾部显示引用覆盖率 |

---

## M7 研究辅助（P1）

- 文献综述生成（基于 collection 内 10–30 篇）
- 研究 gap 分析（对比结论聚类）
- 选题建议（领域热点 + 引用网络）
- 写作提纲 / 相关工作段落草稿

依赖 M5 的矩阵与 M6 的引用；表：`research_outputs(id, user_id, kind, input_json, content_md, citations_json)`。

## M8 平台化（P1）

- 团队共享文献库（`library_items.scope=team`）
- 每用户/团队配额（检索次数、解析页数、分析次数）
- 任务中心（解析/分析/对比的统一 job 表 + 进度）
- 可观测：检索延迟、数据源成功率、解析失败率、LLM 成本
- 审计日志（导出/分享/删除）

---

## 4. 新增数据模型总览

| 表 | 归属模块 | 说明 |
|---|---|---|
| `papers` | M1/M2 | 外部论文元数据（唯一真源） |
| `search_logs` | M1 | 检索行为与延迟 |
| `external_cache` | M1 | 无 Redis 时的兜底缓存 |
| `library_items` | M2 | 用户文献库条目 |
| `collections` / `tags` / `paper_tags` | M2 | 分类与标签 |
| `notes` | M2 | 阅读笔记 |
| `paper_sections` | M3 | 章节结构与页码 |
| `paper_assets` | M3 | 表格/图片 |
| `paper_references` | M3 | 参考文献 |
| `document_quality` | M3 | 解析质量指标 |
| `analyses` | M4 | 结构化分析结果 |
| `comparisons` | M5 | 多篇对比结果 |
| `research_outputs` | M7 | 综述/gap/提纲 |
| `jobs` | M8 | 统一异步任务与进度 |

**兼容策略**：现有 `documents` / `knowledge_bases` 不动；`papers` 通过 `library_items.document_id` 关联，老数据可无损继续用。迁移全部走 `_ensure_columns` 的增量补列 + 新表 `create_all`，不删列不改类型。

---

## 5. 横切设计

### 5.1 缓存

| 层 | 内容 | TTL |
|---|---|---|
| 进程内 LRU | 数据源响应、模型列表 | 5 min |
| Redis（可选） | 检索结果、DOI 元数据 | 10 min / 24h |
| DB | 分析结果、对比结果 | 永久（带版本） |

### 5.2 限流

按数据源令牌桶（OpenAlex 10/s、Crossref 5/s、arXiv 1/3s、S2 1/s），超限返回 `429 + Retry-After`；服务端对内做并发闸门，避免把上游打挂。

### 5.3 异步任务

解析/分析/对比统一走 `jobs` 表 + Celery；前端轮询 `GET /api/jobs/{id}` 或订阅 SSE。eager 模式下同步执行但同样写 job 记录，保证行为一致。

### 5.4 性能预算

| 场景 | 目标 |
|---|---|
| 检索（3 源，无缓存） | P95 < 2s |
| 检索（缓存命中） | < 200ms |
| 单篇解析（20 页 PDF） | < 30s |
| 单篇分析（单维度） | 首 token < 3s，完整 < 40s |
| 三篇对比（6 维） | < 90s |
| 库内搜索（1 万条） | P95 < 300ms |

### 5.5 安全与合规

- 只存 **开放获取（OA）** 论文全文；非 OA 仅存元数据 + 原文链接，不做全文抓取。
- API Key 继续加密存储；外部数据源 Key（如 S2）支持服务端 `.env` 与用户自带两种。
- 团队库与个人库的检索隔离沿用现有 `owner_id/team_id` 过滤，不能因为新接口破坏。

---

## 6. 实施计划

### Sprint 0 — 地基（2–3 天）

- 新增 `papers` / `library_items` / `collections` / `tags` / `jobs` 表
- `literature/` 目录骨架 + DTO + 协议 + 缓存/限流
- 前端路由骨架（search / library / paper / compare）
- 验收：`pytest` 通过；启动自动建表；空页面可访问

### Sprint 1 — M1 检索（3–4 天）

- OpenAlex + Crossref + arXiv 适配器 + 聚合器
- `/api/literature/*` 全部接口
- `SearchView` + 结果卡片 + 筛选 + 详情抽屉
- 验收：关键词/作者/DOI 三种检索可用；单源故障不影响整体

### Sprint 2 — M2 文献库（3 天）

- 收藏/上传/分类/标签/状态/笔记/库内搜索/引用导出
- `LibraryView` + 详情抽屉
- 验收：从检索页收藏→进库→打标签→导出 BibTeX 全链路

### Sprint 3 — M3 解析（3–4 天）

- 章节识别、元数据、参考文献、章节感知切片、质量校验
- 解析结果页
- 验收：样例论文章节树正确；切片 metadata 含 section

### Sprint 4 — M4 单篇分析（3–4 天）

- 9 类分析 + 引用校验 + 缓存 + 流式
- 分析面板
- 验收：9 类可生成；引用可跳页

### Sprint 5 — M5 对比 + M6 溯源问答（4–5 天）

- 对比矩阵 + 叙述 + 导出
- 引用编号/锚点/严格模式/覆盖率
- 验收：3 篇 6 维对比；问答引用准确率 ≥90%

### Sprint 6 — M7/M8（按需）

- 综述/gap/提纲；团队共享库；配额与监控

---

## 7. 验收标准汇总（Definition of Done）

每个功能必须同时满足：

1. **接口**：OpenAPI 可见、参数校验、错误结构化（`{ok:false,message}`）。
2. **数据**：迁移可重复执行，旧数据不丢；SQLite/MySQL 双跑通。
3. **测试**：新增逻辑有单测（外部 HTTP 用 respx mock）；核心路径有手测脚本。
4. **前端**：加载/空/错误三态齐全；移动端不崩。
5. **性能**：达到 5.4 预算。
6. **文档**：README 增补启动方式与接口说明；`.env.example` 增补新变量。

---

## 8. 风险与不做的事

| 风险 | 应对 |
|---|---|
| 数据源不稳定/限流 | 多源聚合 + 缓存 + 降级返回部分结果 |
| PDF 版权 | 仅 OA 全文；非 OA 只存元数据与链接 |
| SQLite 并发写 | 开发期用 SQLite，生产必须 MySQL；解析任务串行化 |
| Chroma 规模 | 单集合 + 元数据过滤；超过 50 万块再考虑按领域分集合 |
| 老数据兼容 | 全部新增表/列，不删不改；`documents` 保持原语义 |
| 范围膨胀 | 每个 Sprint 结束必须可演示；P1 功能不阻塞 P0 |

**明确不做**：不重写 RAG 引擎、不替换前端框架、不引入新的向量库、不做爬虫抓取非 OA 全文。

---

## 9. 下一步

建议从 **Sprint 0 + Sprint 1（M1）** 开始：先把「统一检索层」打通，它是后续所有模块的数据入口，也是最能立刻演示出“从阅读工具变成检索平台”的模块。

确认本方案后，我会按 Sprint 顺序提交代码，每个 Sprint 结束时给出可运行的演示路径与验收结果。
