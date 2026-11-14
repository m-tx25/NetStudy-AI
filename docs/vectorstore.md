# 向量库为什么会坏，以及怎么快速恢复

> 这份文档是踩坑记录 + 操作手册。**看完能省下几次白重建的钱**。

## 一、先分清三种「坏了」

三种情况的报错都长得像「连接 Chroma 服务失败」，但处理方式完全不同：

| 现象 | 真实原因 | 处理 | 要不要重建 |
| --- | --- | --- | --- |
| 后端日志有 `502 Bad Gateway` | 系统代理（Clash）劫持了 `127.0.0.1:8000` | 重启后端（代码已自动绕过代理） | ❌ 不用 |
| 报 `Error loading hnsw index` | **索引文件缺失**，sqlite 里还有向量记录 | `dev.cmd --restore` 或 `--rebuild --reindex` | ✅ 要 |
| 集合能打开但 `count()=0` | 只是没索引 | `dev.cmd --reindex` | ❌ 不用 |

一条命令区分：

```powershell
cd server
.\dev.cmd --check
```

输出会直接给结论，例如：

```
服务：[OK] 服务在，但集合 knowledge_chunks_zhipu2048 打不开：InternalError: ... hnsw segment reader
sqlite：1 个集合，2321 条向量记录
索引文件：[!!] segment e5da13f7 缺少 header.bin, data_level0.bin, length.bin, link_lists.bin

诊断：**索引损坏**。sqlite 里有向量记录，但 HNSW 索引文件不见了。
处理：.\dev.cmd --rebuild --reindex
```

## 二、为什么会坏（三个真实原因）

### 1. Chroma 1.x 的写入顺序 + 强行杀进程（主要原因）

Chroma 写一个切片时，先写 sqlite 行，**后**写 HNSW 索引文件
（`header.bin` / `data_level0.bin` / `length.bin` / `link_lists.bin`）。

如果在这中间进程被杀（`taskkill /F`、任务管理器结束、断电），
就会出现：**sqlite 里 2300 多条向量记录，但索引文件目录里只剩 `index_metadata.pickle`**。
此后所有查询都报 `Error loading hnsw index`，而且写新数据也救不回来 —— 必须重建。

官方 issue [chroma-core/chroma#5366](https://github.com/chroma-core/chroma/issues/5366) 仍 open。

本项目实际踩坑记录：
- 重建索引跑到一半，我 `taskkill /F` 杀掉 Chroma → 下一次启动就坏；
- `dev.cmd` 退出时立刻 `taskkill /F`，而此时刚好在刷新索引。

### 2. 两个 Chroma 进程写同一个目录

同一份 `data/chroma_db` 只能被一个进程打开。
既跑 `dev.cmd` 又跑 `start-chroma.cmd`，索引必坏（实测发生过一次）。

现在 `dev.cmd` 启动前会检查 8000 端口，已在监听就跳过启动，不会再起第二个。

### 3. 它「看起来坏了」但其实是被代理劫持

Clash 开着时 `httpx` 默认读系统代理，连 `127.0.0.1:8000` 也走代理，
代理返回 `502` + 空响应，被 chromadb 报成「连接失败」。
这种情况**删库重建纯属白花钱**。代码已自动绕过（`NO_PROXY`）。

## 三、恢复手段：优先用快照

`dev.cmd --reindex` 成功后会自动把整个向量库**复制**一份到
`server/data/chroma_db.snapshot`（约 20~30MB）。

之后索引再坏，不用重新调 embedding 接口，直接：

```powershell
cd server
.\dev.cmd --restore     # 把快照覆盖回来，再启动
```

耗时几秒，**零 API 费用**。

没有快照时才需要：

```powershell
.\dev.cmd --rebuild --reindex    # 备份旧库 → 建新库 → 重新向量化 → 自动留快照
```

## 四、规则（照做就不会再坏）

1. **不要在写索引时强杀 Chroma**
   - 用 `dev.cmd` 启动时：直接 `Ctrl+C` 关后端，脚本会等 8 秒让 Chroma 落盘再停它；
   - 手动启动时：先停后端，再关 Chroma 窗口，别用任务管理器强制结束。
2. **一个目录只跑一个 Chroma**：别再同时开 `dev.cmd` 和 `start-chroma.cmd`。
3. **重建后一定留快照**（`dev.cmd --reindex` 已自动做）。
4. **报错先跑 `dev.cmd --check`**，别急着重启或删库。
5. 磁盘要留余量：SQLite 写入失败会直接坏库（当前 E 盘还有 91GB，正常）。

## 五、相关文件

| 文件 | 作用 |
| --- | --- |
| `server/check_chroma.py` | 体检脚本，区分三种「坏了」 |
| `server/dev.cmd` | 启动 / `--check` / `--reindex` / `--rebuild` / `--restore` / `--snapshot` |
| `server/reindex_all.py` | 全量重建索引 |
| `server/prune_orphan_vectors.py` | 清理「库已删但向量还在」的残留 |
| `docs/compare.md` | 论文对比（不依赖向量库，索引坏了也能用） |

---

## 六、最终结论：这个 Chroma 版本不会持久化 HNSW 索引

> 这一节是实测结论，推翻了本文前半部分「干净退出就能落盘」的假设。

### 验证过程

| 关闭方式 | 结果 |
| --- | --- |
| `taskkill /F`（强杀） | `*.bin` 未落盘 |
| `taskkill`（不带 /F） | 对控制台程序无效，提示只能强制结束 |
| **Ctrl+Break**（`CREATE_NEW_PROCESS_GROUP` + `signal.CTRL_BREAK_EVENT`） | 进程以 `0xC000013A` 退出，`*.bin` **仍未落盘** |

也就是说：**无论怎么关，Chroma 1.4.4/1.5.9 都不会把 HNSW 索引写到磁盘**，
只把向量留在 `chroma.sqlite3` 里。而删除 `index_metadata.pickle` 让 Chroma
从 sqlite 重建索引的做法**不稳定** —— 有时能查到（count/按 id 读都正常），
但向量检索持续报 `Error finding id`，等多久都不会恢复。

### 因此的实际规则

1. **一次机器会话只重建一次**：`dev.cmd --rebuild --reindex`，然后**不要停 Chroma**；
2. 重启电脑 / 重启 Chroma → 索引必然失效 → 再跑一次 `--rebuild --reindex`（约 2 分钟）；
3. `--snapshot` 只能备份 sqlite 数据，**恢复后仍需要重建索引**，
   所以 `--reindex` 成功后**不再自动打快照**（打快照要停 Chroma，正好把索引杀掉）；
4. 判断是否要重建，先跑 `dev.cmd --check`：
   `Error finding id` / `Error loading hnsw index` 都是「要重建」的信号。

### 彻底解决的方向

把 `chromadb` 与它的 rust runtime 版本对齐（当前 python 包 1.5.9、CLI 1.4.4），
或改用 Docker 里的官方镜像（`docker-compose.yml` 已含 chroma 服务，
带 `stop_grace_period`）。这两条都需要联网重装依赖，尚未执行。
