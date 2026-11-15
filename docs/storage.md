# PDF 上传与存储管理（2 核 4GB / 50GB 磁盘）

面向评审演示服务器（2 vCPU、4GB 内存、50GB 磁盘）的默认配置与运维方式。

## 1. 默认限制

| 项 | 默认值 | 配置项 |
|---|---|---|
| 单文件大小 | **100MB** | `MAX_UPLOAD_SIZE_MB` |
| 总存储配额 | 40GB | `STORAGE_TOTAL_QUOTA_GB` |
| 单用户配额 | 5GB | `STORAGE_PER_USER_QUOTA_GB` |
| 最少保留空闲 | 5GB | `STORAGE_MIN_FREE_GB` |
| 流式分块 | 1MB | `UPLOAD_CHUNK_SIZE_KB` |
| 同时解析任务 | 1 | `MAX_CONCURRENT_PARSE_TASKS` |
| 同时 LLM 任务 | 1 | `MAX_CONCURRENT_LLM_TASKS` |

所有限制都在 `server/.env` 里改，**前端不再硬编码**：上传弹窗打开时会请求
`GET /api/storage/status`，显示后端真实的单文件上限与磁盘剩余。

## 2. 上传链路

```
浏览器选择文件
  → POST /api/documents/upload（multipart，流式）
  → 扩展名白名单（pdf/docx/md/…）
  → 声明大小 > 上限 → 413
  → 容量预检（磁盘/总配额/个人配额）
  → 流式落盘（1MB 分块，边写边算 SHA-256，内存占用与文件大小无关）
  → 完整性校验：
       PDF：%PDF- 头 + %%EOF 尾 + pypdf 能读出页面且未加密
       docx/pptx/xlsx：必须是合法 zip
       .doc：OLE 复合文档头
       文本类：不能含 NUL 字节
  → 同知识库内容去重（content_hash）
  → 建 documents 记录（status=processing），立即返回
  → 后台异步解析（章节/切片/向量），前端轮询状态
```

超限、格式错误、文件损坏都会在**落盘后立即删除半成品**，不会留下垃圾文件。

## 3. 存储分层（互不耦合）

| 数据 | 位置 | 说明 |
|---|---|---|
| 原始 PDF | `server/data/uploads/` | 保留原件；文件名用文档 ID，避免重名覆盖 |
| 解析文本 | MySQL `paper_sections` / `paper_references` | 章节、参考文献，可按 document_id 删除 |
| 向量 | ChromaDB（`data/chroma_db`） | 切片与向量，按 document/知识库删除 |
| 临时文件 | 上传目录中未被数据库引用的文件 | 由清理脚本处理 |

删除文档时三者都会清理；**原始文件默认保留，不会被自动删除**（需求 9）。

## 4. 磁盘监控与清理

- 实时状态：`GET /api/storage/status`（登录后），返回磁盘总量/已用/剩余、总配额、个人配额、单文件上限。
- 上传时会自动检查：剩余空间 < 5GB 或超出配额 → 直接拒绝并给出可读原因（507/413）。
- 孤儿文件清理（默认干跑）：

```bash
cd server
python cleanup_storage.py                 # 查看将删除什么
python cleanup_storage.py --apply         # 真正删除（只删无引用且超过 24h 的文件）
```

建议加到计划任务，每天凌晨执行一次：

```powershell
# Windows 任务计划程序，每天 03:00
powershell -NoProfile -Command "cd D:\chuangzhibei\server; .\.venv\Scripts\python.exe cleanup_storage.py --apply --older-than 24" >> D:\chuangzhibei\server\data\cleanup.log 2>&1
```

## 5. 2 核 4GB 的优化点

1. **解析串行**：`MAX_CONCURRENT_PARSE_TASKS=1`，用信号量排队；避免两个 100MB PDF 同时解析把内存打爆。
2. **分块流式**：上传按 1MB 读写，内存占用与文件大小无关。
3. **Chroma 小批次**：`CHROMA_UPSERT_BATCH=8`，降低 compactor 被打断导致向量库损坏的概率。
4. **LLM 任务串行**：对比/研究类任务单独限流，避免同时打满模型配额与内存。
5. **PDF 完整性检查在线程池**：pypdf 解析页面数不阻塞事件循环。
6. **磁盘预留 5GB**：保证 MySQL/Chroma 写入与日志不会因磁盘满而失败。
7. 若使用 Redis + Celery，worker 启动时加 `--concurrency=1`（与 `MAX_CONCURRENT_PARSE_TASKS` 一致）。

## 6. 评审演示模式

准备一个目录放演示论文（PDF/Word/Markdown），执行：

```bash
cd server
python demo_seed.py --dir D:\papers --username demo
```

脚本会：

1. 在 demo 用户下创建/复用「评审演示论文」知识库；
2. 按内容哈希去重导入文件（原文件复制到上传目录，保留）；
3. 立即完成解析，把章节、切片、向量**缓存好**；
4. 打印每个文件的解析结果（chunks / sections / error）。

演示时打开该知识库即可看到已解析的结构，不需要现场等待。重复执行不会产生重复文档；要重新解析加 `--force`。

## 7. 相关配置一览

```ini
MAX_UPLOAD_SIZE_MB=100
UPLOAD_CHUNK_SIZE_KB=1024
STORAGE_TOTAL_QUOTA_GB=40
STORAGE_PER_USER_QUOTA_GB=5
STORAGE_MIN_FREE_GB=5
MAX_CONCURRENT_PARSE_TASKS=1
MAX_CONCURRENT_LLM_TASKS=1
DEMO_MODE=false
DEMO_PAPERS_DIR=./data/demo_papers
```
