# 团队与 API 密钥

本文说明**团队协作**与**API 密钥**两块功能：数据模型、权限规则、接口清单与验证方式。

- 前端入口：侧边栏 **团队**（`/app/teams`）、账号设置里的 **API 密钥**（`/app/settings`）
- 后端模块：`server/app/api/teams.py`、`server/app/api/keys.py`、`server/app/services/keyring.py`、`server/app/services/access.py`、`server/app/core/secrets.py`
- 界面截图：[docs/screenshots/teams](screenshots/teams)

---

## 一、团队

### 1.1 角色与权限矩阵

一个团队有一个**负责人（owner）**、若干**管理员（admin）**和**成员（member）**。

| 动作 | 负责人 | 管理员 | 成员 |
| --- | :---: | :---: | :---: |
| 查看团队详情 / 成员列表 | ✓ | ✓ | ✓ |
| 查看 / 使用团队知识库、上传文档 | ✓ | ✓ | ✓ |
| 修改团队信息（名称、简介、可见性、加入方式） | ✓ | ✓ | ✗ |
| 审批入队申请 | ✓ | ✓ | ✗ |
| 直接拉人入队（免审批） | ✓ | ✓ | ✗ |
| 查看邀请码 / 重置邀请码 | ✓ | ✓ | ✗ |
| 设置成员角色（提升 / 取消管理员） | ✓ | 仅普通成员 | ✗ |
| 移除成员 | ✓ | 仅普通成员 | ✗ |
| 配置团队 API 密钥 | ✓ | ✓ | ✗ |
| **转让负责人** | ✓ | ✗ | ✗ |
| **解散团队** | ✓ | ✗ | ✗ |
| 退出团队 | 需先转让 | ✓ | ✓ |

补充约束（后端强制，前端仅做展示层优化）：

- 管理员之间**不能互相**改角色或移除，避免内斗；
- 不能修改自己的角色；
- **负责人不能直接退队**，必须先转让（否则团队会没有负责人）；
- 转让后原负责人自动降为**管理员**，便于交接。

### 1.2 入队方式

| 方式 | 入口 | 行为 |
| --- | --- | --- |
| **邀请码** | 团队页「邀请码加入」 | 取决于团队的 `joinPolicy`：`open` 直接加入；`approval` 提交申请待审核；`closed` 拒绝 |
| **搜索申请** | 团队页「发现团队」→ 搜索 → 申请加入 | 提交申请，负责人 / 管理员审批 |
| **管理员直接拉人** | 团队详情 → 成员 → 输入用户名 | 免审批直接入队，同时撤销其待审批申请 |

`visibility`（可见性）与 `joinPolicy`（加入方式）是两个独立维度：

- `visibility=public`：可被搜索到；`private`：只能靠邀请码进入，非成员访问详情返回 404；
- `joinPolicy=open|approval|closed`：见上表。

### 1.3 入队审核（类 QQ 群）

申请人提交后产生一条 `pending` 记录，负责人 / 管理员在「入队审批」页签里**同意**或**拒绝**：

- 同意时可选角色（普通成员 / 管理员）；
- 同一用户对同一团队的**重复申请是幂等的**（不会堆积多条待审）；
- 已被处理过的申请再次审批返回 `409`；
- 管理员直接拉人时，会自动清理该用户的待审批申请；
- 申请人可在「我的申请」里**撤回**自己的待审申请。

### 1.4 团队知识库

团队知识库与个人知识库**共用 `knowledge_bases` 表**，用两个字段区分归属：

| 字段 | 个人库 | 团队库 |
| --- | --- | --- |
| `owner_type` | `user` | `team` |
| `owner_id` | 用户 id | 团队 id |

- **成员都能上传**：团队库对全体成员开放读写（这是团队协作的核心诉求）；
- **检索按归属隔离**：Chroma 切片带 `owner_id`（上传者）与 `team_id`；
  提问者只要**是该团队成员**就能召回该团队的切片，非成员一条也召回不到；
- 非成员访问团队库 / 上传文档一律返回 **404**（不暴露资源是否存在）。

> 实现细节：`server/app/services/access.py` 用 `accessible_condition()` 统一生成
> 「我的个人库 + 我所在团队的团队库」SQL 条件，`knowledge_bases` / `documents` / `rag.engine`
> 三处共用，避免各写一份导致权限口径不一致。

### 1.5 接口清单

前缀 `/api`，均需登录（Bearers token）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/teams` | 创建团队（创建者即负责人，自动生成邀请码） |
| GET | `/teams` | 我加入的团队 |
| GET | `/teams/search?q=&limit=` | 搜索可加入的公开团队 |
| GET | `/teams/invite/{code}` | 邀请码预览团队（加入前） |
| GET | `/teams/{id}` | 团队详情（邀请码仅管理员以上可见） |
| PATCH | `/teams/{id}` | 修改团队信息（管理员以上） |
| DELETE | `/teams/{id}` | 解散团队（负责人） |
| POST | `/teams/{id}/invite-code` | 重置邀请码（管理员以上） |
| GET | `/teams/{id}/members` | 成员列表 |
| POST | `/teams/{id}/members` | 直接拉人入队（管理员以上） |
| PATCH | `/teams/{id}/members/{userId}` | 设置成员角色（`admin` / `member`） |
| DELETE | `/teams/{id}/members/{userId}` | 移除成员；移除自己即退队 |
| POST | `/teams/{id}/transfer` | 转让负责人（负责人） |
| POST | `/teams/{id}/join` | 申请入队（搜索入口） |
| POST | `/teams/join-by-code` | 用邀请码加入 |
| GET | `/teams/join-requests/mine` | 我提交的申请 |
| GET | `/teams/{id}/join-requests?status_filter=` | 待审批列表（管理员以上） |
| POST | `/teams/{id}/join-requests/{reqId}` | 审批（`{approve, role}`） |
| DELETE | `/teams/{id}/join-requests/{reqId}` | 撤回自己的申请 |

---

## 二、API 密钥

### 2.1 为什么需要

服务端 `.env` 里的全局 Key 由部署者提供，所有用户共用。团队/个人可以配置**自己的** Key：

- 费用与配额各算各的（团队库花团队的钱）；
- 可以按团队选择不同的模型供应商。

### 2.2 作用域与生效规则

| 场景 | 用谁的密钥 |
| --- | --- |
| 检索 / 索引**个人知识库** | 该用户自己的 Key |
| 检索 / 索引**团队知识库** | 该团队的 Key |
| 生成回答 | 同一次问答所涉及知识库的归属方；无指定知识库时用提问者自己的 Key |
| 以上都没配 | **回落服务端 `.env` 的全局 Key** |

优先级：**团队 Key → 用户 Key → 服务端 Key**。

> 为什么团队优先于用户：查询团队知识库时不应花某个成员自己的钱。
> 因此**永远不会跨团队串用密钥**。

### 2.3 支持的供应商

| id | 供应商 | 能力 | 默认生成模型 | 默认向量模型 |
| --- | --- | --- | --- | --- |
| `zhipu` | 智谱 AI（GLM） | 向量化 + 生成 | `glm-4-flash` | `embedding-3` |
| `deepseek` | DeepSeek | **仅生成** | `deepseek-chat` | —— |
| `openai` | OpenAI 兼容 | 向量化 + 生成 | `gpt-4o-mini` | `text-embedding-3-small` |
| `custom` | Ollama / vLLM / One-API 等 | 向量化 + 生成 | 自定义 | 自定义 |

> ⚠️ **DeepSeek 不能用于向量化**：开放平台没有 `/embeddings` 接口（请求返回 404），
> 它的 Key 只能用在生成环节。

> ⚠️ **向量化只换 Key、不换模型**：Chroma 集合按向量维度区分
> （见 `vectorstore.collection_name()`），同一个 embedding-3 模型下不同 Key 产生的向量
> 属于同一向量空间，可以安全共用集合。**换模型会导致维度/语义不一致**，故当前不支持
> 团队自选向量模型。

### 2.4 安全设计

- 密钥用 **Fernet 对称加密**（AES-128-CBC + HMAC）后落库，密钥由 `SECRET_KEY` 派生
  （见 `server/app/core/secrets.py`）；
- 所有接口**只返回掩码**（如 `sk-abc…f123`），**任何人都无法查看明文**；
- 更新时 `secret` 留空表示「不改密钥，只改其它字段」；
- 团队密钥仅负责人 / 管理员可读写，普通成员请求返回 403；
- `SECRET_KEY` 更换后旧密文无法解密，此时按「未配置」处理并提示重新填写，而不是抛 500。

> 部署提醒：生产环境务必把 `.env` 里的 `SECRET_KEY` 换成随机长字符串
> （`openssl rand -hex 32`）。更换 `SECRET_KEY` 会让已保存的密钥失效。

### 2.5 接口清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/keys/providers` | 供应商清单（含能力声明，无需登录） |
| GET | `/keys` | 个人密钥总览 |
| POST | `/keys` | 新增 / 覆盖个人密钥（同一 provider 只保留一条） |
| PATCH | `/keys/{keyId}` | 更新个人密钥 |
| DELETE | `/keys/{keyId}` | 删除个人密钥 |
| GET | `/keys/models?team_id=` | 可用生成模型（服务端配置的 + 自配密钥） |
| GET | `/teams/{id}/keys` | 团队密钥总览（管理员以上） |
| POST | `/teams/{id}/keys` | 新增 / 覆盖团队密钥 |
| PATCH | `/teams/{id}/keys/{keyId}` | 更新团队密钥 |
| DELETE | `/teams/{id}/keys/{keyId}` | 删除团队密钥 |

---

## 三、验证

### 3.1 后端自动化测试

后端接口用脚本对**真实运行的服务**发请求（避免 TestClient 的跨事件循环问题）：

```powershell
cd server
.\.venv\Scripts\python.exe tests\verify_teams.py     # 团队与密钥：52 项
.\.venv\Scripts\python.exe tests\verify_team_kb.py   # 团队知识库与检索：23 项
```

覆盖：创建团队、邀请码、搜索、幂等申请、审批通过/拒绝/重复审批、角色提升、
权限边界（成员/管理员各不能做什么）、转让负责人、退队限制、解散清理、
个人与团队密钥 CRUD、掩码不回明文、跨用户隔离、团队库上传与检索。

### 3.2 前端端到端

```powershell
# 前置：后端 3000 + 前端 5173 都在运行
cd client
node scripts/e2e-teams.mjs     # 无头浏览器验证界面：24 项
node scripts/shots-teams.mjs   # 生成 docs/screenshots/teams 下的截图
```

### 3.3 手工验证要点

1. 用 A 账号建团队 → 复制邀请码；
2. 用 B 账号「邀请码加入」→ 提交申请；
3. A 打开团队 → 入队审批 → 同意；
4. A 在团队设置里配置团队智谱 Key；
5. A 或 B 建一个**团队知识库**并上传文档，等状态变「已就绪」；
6. B 提问文档里的内容 → 应能召回并给出带引用的回答；
7. 用**非成员** C 账号提问同一问题 → 不应召回任何团队库切片。

---

## 四、相关文件

| 文件 | 职责 |
| --- | --- |
| `server/app/models.py` | `Team` / `TeamMember` / `TeamJoinRequest` / `ApiKey`；`KnowledgeBase.owner_type/owner_id`；`Document.uploaded_by` |
| `server/app/api/teams.py` | 团队路由与权限校验 |
| `server/app/api/keys.py` | 密钥路由（个人 + 团队） |
| `server/app/services/access.py` | 知识库访问控制（个人 / 团队统一判定） |
| `server/app/services/keyring.py` | 密钥解析（作用域优先级）与供应商清单 |
| `server/app/core/secrets.py` | 密钥加密 / 解密 / 掩码 |
| `client/src/api/teams.js`、`client/src/api/keys.js` | 前端接口封装 |
| `client/src/stores/team.js` | 团队状态与权限 computed |
| `client/src/views/TeamsView.vue` | 团队主页面（列表 / 发现 / 申请 / 详情抽屉） |
| `client/src/components/keys/ApiKeyManager.vue` | 密钥管理组件（个人 / 团队复用） |
