# 前端 ↔ 后端 接口约定

本文档是前端（`client/`）已经按此实现、后端需要对齐的契约。
默认所有接口前缀为 `/api`（`VITE_API_BASE_URL`），除登录/注册外都需要
`Authorization: Bearer <token>` 请求头。

---

## 0. 返回体格式

前端同时兼容两种风格，任选其一即可：

**A. 裸返回**

```json
{ "id": "conv_1", "title": "新的对话" }
```

**B. 统一信封**（推荐）

```json
{ "code": 0, "message": "ok", "data": { "id": "conv_1" } }
```

`code` 为 `0` 或 `200` 视为成功；其他值前端会把 `message` 作为错误提示。
HTTP 状态码也会被识别：

| 状态码 | 前端行为 |
| --- | --- |
| 401 | 清除本地 Token，跳转登录页（带 `redirect`） |
| 403 / 404 / 413 / 5xx | 弹出对应的中文错误提示 |
| 无响应 | 提示「无法连接后端服务」 |

---

## 1. 鉴权

### POST `/api/auth/register`

```json
{ "username": "alice", "email": "a@b.com", "password": "123456" }
```

返回：

```json
{ "token": "jwt...", "user": { "id": "u1", "username": "alice", "nickname": "Alice", "email": "a@b.com", "role": "user" } }
```

### POST `/api/auth/login`

```json
{ "username": "alice", "password": "123456" }
```

返回同上（`token` + `user`）。

### GET `/api/auth/me`

返回当前用户对象（不带 `token`）。

### POST `/api/auth/logout`

返回任意内容；前端无论如何都会清空本地登录态。

---

## 2. 会话

### GET `/api/conversations`

```json
[
  {
    "id": "conv_1",
    "title": "RAG 检索流程是怎样的",
    "createdAt": "2025-01-01T10:00:00.000Z",
    "updatedAt": "2025-01-01T10:02:00.000Z",
    "messageCount": 2,
    "knowledgeBaseIds": ["kb_1"]
  }
]
```

### POST `/api/conversations`

```json
{ "title": "新的对话", "knowledgeBaseIds": ["kb_1"] }
```

返回新建的会话对象。

### PATCH `/api/conversations/:id`

```json
{ "title": "重命名后的标题" }
```

### DELETE `/api/conversations/:id`

### GET `/api/conversations/:id/messages`

```json
[
  { "id": "m1", "role": "user", "content": "问题", "createdAt": "..." },
  {
    "id": "m2",
    "role": "assistant",
    "content": "Markdown 回答",
    "sources": [ /* 见 3.2 引用来源结构 */ ],
    "createdAt": "...",
    "status": "done"
  }
]
```

`role` 取值：`user` / `assistant`（`system` 会被前端原样渲染为助手样式，建议不要返回）。

---

## 3. 流式问答（核心）

### POST `/api/chat/stream`

请求头：

```
Content-Type: application/json
Accept: text/event-stream
Authorization: Bearer <token>
```

请求体：

```json
{
  "conversationId": "conv_1",
  "content": "RAG 的检索流程是怎样的？",
  "knowledgeBaseIds": ["kb_1", "kb_2"],
  "topK": 5,
  "scoreThreshold": 0.2
}
```

响应头必须是：

```
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
```

#### 3.1 事件格式

后端每推一段增量就 flush 一次，事件之间用空行分隔。推荐三种事件：

```
event: sources
data: {"sources":[{"id":"c1","documentId":"d1","documentName":"系统架构设计.docx","knowledgeBaseName":"技术文档库","score":0.91,"page":3,"snippet":"……原文片段……"}]}

event: delta
data: {"content":"RAG（Retrieval-Augmented"}

event: delta
data: {"content":" Generation）的核心是"}

event: done
data: {"messageId":"m9","usage":{"promptTokens":812,"completionTokens":356}}

```

说明：

- `delta` 事件只放**本次新增**的文本，前端会拼接；不要把已输出的内容重复发送。
- `sources` 可以在正文之前推一次（推荐），也可以之后补推；前端会覆盖式更新。
- `done` 可选，用于回传落库后的消息 id；也可以直接发送 `data: [DONE]`。
- 以 `:` 开头的行是注释，可用作心跳（前端会忽略），建议 15~30s 一次。
- 出错时推送 `event: error` + `data: {"message":"向量库连接失败"}`，前端会把该条回答标记为失败并允许重新生成。

#### 3.2 前端接受的等价写法

事件类型既可以放在 `event:` 里，也可以放在 JSON 的 `type` 字段里：

```
data: {"type":"delta","content":"增量文本"}
data: {"type":"sources","sources":[...]}
data: {"type":"done","messageId":"m9"}
```

还可以直接兼容 OpenAI 风格：

```
data: {"choices":[{"delta":{"content":"增量文本"}}]}
```

如果响应没有 `text/event-stream` 头，前端会把整个响应体当作一次性回答处理
（`{"content": "..."}` 或纯文本都可以），但这样就**没有打字机效果**。

#### 3.3 引用来源（sources）字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 否 | 片段唯一 id，用于展开态去重 |
| `documentId` | string | 否 | 文档 id |
| `documentName` | string | 是 | 展示在来源标签上的文件名 |
| `knowledgeBaseName` | string | 否 | 所属知识库名 |
| `score` | number | 否 | 相似度，0~1 或 0~100 都可，前端自动识别并显示为百分比 |
| `page` | number | 否 | 页码，有则显示「第 N 页」 |
| `snippet` | string | 是 | 命中的原文片段 |

---

## 4. 知识库

### GET `/api/knowledge-bases`

```json
[
  {
    "id": "kb_1",
    "name": "产品需求文档库",
    "description": "需求规格、路线图、竞品分析",
    "documentCount": 3,
    "chunkCount": 486,
    "embeddingModel": "bge-large-zh-v1.5",
    "createdAt": "...",
    "updatedAt": "..."
  }
]
```

### POST `/api/knowledge-bases`

```json
{ "name": "知识库名", "description": "描述" }
```

### PATCH `/api/knowledge-bases/:id`

```json
{ "name": "新名字", "description": "新描述" }
```

### DELETE `/api/knowledge-bases/:id`

级联删除其中的文档。

---

## 5. 文档

### GET `/api/documents?knowledgeBaseId=kb_1`

```json
[
  {
    "id": "d1",
    "knowledgeBaseId": "kb_1",
    "name": "需求规格说明书_v2.pdf",
    "size": 4512000,
    "chunks": 186,
    "status": "ready",
    "enabled": true,
    "uploadedAt": "2025-01-01T10:00:00.000Z"
  }
]
```

`status` 取值：`pending`（排队中）/ `processing`（解析中）/ `ready`（已就绪）/ `failed`（失败）。
只有 `ready` 且 `enabled !== false` 的文档参与检索。

### POST `/api/documents/upload`

`multipart/form-data`：

| 字段 | 说明 |
| --- | --- |
| `file` | 文件本体 |
| `knowledgeBaseId` | 目标知识库 id |

返回单个文档对象。前端通过 `onUploadProgress` 显示上传进度，拿到响应后进度条置为 100% 并显示「解析中」；
若后端是异步解析，可先用 `processing` 返回，再由前端刷新或轮询得到 `ready`。

### PATCH `/api/documents/:id`

```json
{ "enabled": false }
```

### DELETE `/api/documents/:id`

### POST `/api/documents/:id/reindex`

重新解析与向量化，返回更新后的文档对象（可先返回 `processing`）。

---

## 6. 建议的错误响应

```json
{ "code": 40001, "message": "文件超过 20MB 限制", "data": null }
```

或直接使用 HTTP 状态 + `{ "message": "..." }`。前端会把 `message` 原样展示。

---

## 7. 部署注意

- **关闭缓冲**：SSE 经过 Nginx / 网关时必须关闭响应缓冲，否则会「攒一大段再一次性返回」：
  ```nginx
  location /api/chat/stream {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding off;
    add_header X-Accel-Buffering no;
  }
  ```
  开发期 Vite 代理已在 `vite.config.js` 中处理。
- **CORS**：前后端不同源时需允许 `Authorization` 头，并允许 `text/event-stream` 响应。
- **超时**：流式接口的建议超时 ≥ 120s，前端 Axios 超时也是 120s（流式请求走原生 fetch，不受该值限制）。
