# 评审演示模式（预置论文 + 缓存解析结果）

> 目标：现场演示时**打开就能检索**，不用等解析；同时不删除任何原始文件。

## 一、怎么预置

1. 把演示用的论文（PDF / Word / Markdown）放进 `server/data/demo_papers/`
2. 执行：

```powershell
cd server
.\.venv\Scripts\python.exe demo_seed.py
```

脚本会：

| 步骤 | 说明 |
| --- | --- |
| 建库 | 建（或复用）「评审演示论文」知识库，归属 `demo` 账号 |
| 复制 | 文件复制到上传目录，**原文件保留，不会自动删除** |
| 去重 | 按内容 SHA-256 去重，重复执行不会产生重复文档 |
| 解析 | **立即完成**章节 / 切片 / 向量，演示时直接可检索 |

参数：

```powershell
demo_seed.py --dir D:\papers        # 换成别的目录
demo_seed.py --username demo        # 导入到别的账号
demo_seed.py --force                # 已存在也重新解析（文件内容变了时用）
```

## 二、为什么能「缓存」解析结果

解析产物分三层存放，互不干扰：

| 层 | 存放位置 | 说明 |
| --- | --- | --- |
| 原始文件 | `server/data/uploads/{docId}.pdf` | 只在用户主动删除时才删 |
| 解析文本 | MySQL：`paper_sections` / `document_metadata` | 按章节存正文与元数据 |
| 向量 | Chroma `knowledge_chunks_zhipu2048` | 检索用 |

重新演示时，只要向量还在，就**不需要重新调用 embedding 接口**（省钱、也快）。

> ⚠️ 当前 Chroma 版本不会把 HNSW 索引持久化到磁盘：
> **重启 Chroma 后必须重新索引**。详见 [vectorstore.md](vectorstore.md)。

## 三、上传限制（2 核 4GB / 50GB 磁盘）

| 项 | 默认值 | 配置项 |
| --- | --- | --- |
| 单文件大小 | 100MB | `MAX_UPLOAD_SIZE_MB` |
| 总存储配额 | 40GB | `STORAGE_TOTAL_QUOTA_GB` |
| 单用户配额 | 5GB | `STORAGE_PER_USER_QUOTA_GB` |
| 最少保留空闲 | 5GB | `STORAGE_MIN_FREE_GB` |
| 流式分块 | 1MB | `UPLOAD_CHUNK_SIZE_KB` |
| 同时解析任务 | 1 | `MAX_CONCURRENT_PARSE_TASKS` |
| 同时 LLM 任务 | 1 | `MAX_CONCURRENT_LLM_TASKS` |

前端不写死上限：上传弹窗打开时请求 `GET /api/storage/status`，
显示后端真实的单文件上限与磁盘剩余。

## 四、演示前自检

```powershell
# 向量库是否健康（会明确区分「连不上 / 索引损坏 / 空库」）
.\dev.cmd --check

# 存储与配额
curl http://127.0.0.1:3000/api/storage/status
```

返回里的 `quota.usedGb` / `disk.freeGb` 就是当前占用与剩余空间。
