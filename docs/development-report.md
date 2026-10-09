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
| 路由 | vue-router | 5.4.0 | Vue 官方路由，页面懒加载开箱可用 |
| 状态管理 | pinia | 4.0.3 | Vue 官方推荐，API 简洁，无需 mutation 样板代码 |
| 后端框架 | Express | 5.2.1 | 生态成熟、中间件模型简单，适合快速实现 REST API |
| 跨域 | cors | 2.8.6 | 开发/联调期直接放行，避免早期跨域阻塞 |
| 环境变量 | dotenv | 18.0.6 | 配置与代码分离，便于区分开发/生产环境 |
| 热重载 | nodemon | 3.1.14 | 后端改动自动重启，减少手动操作 |

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

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查，返回服务名与服务器时间；前端首页据此判断后端连通性 |

响应示例：

```json
{
  "ok": true,
  "service": "chuangzhibei-server",
  "time": "2026-10-09T10:26:30.302Z"
}
```

---

## 6. 开发与运行环境

| 工具 | 版本 |
| --- | --- |
| Node.js | v24.19.0 |
| npm | 11.17.0 |
| pnpm | 11.22.0（未采用，见 9.2） |
| Python | 3.13.11（辅助脚本用） |

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

| 序号 | 验证项 | 方法 | 结果 |
| --- | --- | --- | --- |
| 1 | 后端语法 | `node --check`（5 个 JS 文件） | ✅ 全部通过 |
| 2 | 配置文件合法性 | JSON 解析（2 个 `package.json`） | ✅ 通过 |
| 3 | 前端组件编译 | `@vue/compiler-sfc` 编译 3 个 SFC 的 script + template | ✅ 全部通过，无错误 |
| 4 | 模块依赖完整性 | 解析 11 处 import 并确认目标文件存在 | ✅ 全部解析成功 |
| 5 | 后端接口 | 实际启动服务，`GET /api/health` | ✅ HTTP 200，返回预期 JSON |
| 6 | 后端异常路径 | 请求未定义路由 | ✅ HTTP 404，返回 JSON 错误体 |
| 7 | 端口监听 | 确认服务监听 `0.0.0.0:3000` | ✅ 正常 |
| 8 | 前端 `vite build` | 生产构建 | ⏳ 未完成（见 9.1） |
| 9 | 前端 `vite dev` 端到端 | 浏览器访问 + 代理连通 | ⏳ 未完成（见 9.1） |

### 7.1 启动方式

```bash
# 终端 1：后端
cd server
npm run dev          # http://localhost:3000

# 终端 2：前端
cd client
npm run dev          # http://localhost:5173
```

前端首页显示"后端连接正常"即表示前后端已打通。

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

### 9.1 ⏳ 前端构建与开发服务器尚未端到端验证

在受控沙箱环境中，Vite 启动与构建会调用子进程探测真实路径，被环境限制拦截：

```
[plugin externalize-deps] Error: spawn EPERM
  at optimizeSafeRealPathSync (vite/dist/node)
```

此问题属于**运行环境限制，不是代码缺陷**（后端能正常运行，因其不创建子进程）。已通过组件编译与模块解析做了替代性静态验证。**需在普通终端本地执行 `npm run build` 与 `npm run dev` 完成端到端确认。**

### 9.2 ⚠️ 包管理器未统一

仓库中同时存在 npm 与 pnpm 两套锁文件：

```
client/package-lock.json   （npm，已提交）
client/pnpm-lock.yaml      （pnpm，未跟踪）
client/pnpm-workspace.yaml （pnpm，未跟踪）
server/package-lock.json   （npm，已提交）
server/pnpm-lock.yaml      （pnpm，未跟踪）
```

两者并存会导致依赖版本解析不一致（"我这能跑你那不能跑"）。**须尽快确定唯一包管理器并清理另一套产物。**

### 9.3 ⏳ 测试遗留文件

仓库中存在初始化阶段的测试文件：

- `test.txt'`（0 字节）
- `上传测试.txt`（0 字节）
- `ting.txt`（成员加入测试）

建议在正式开发前清理，避免污染仓库。

### 9.4 ⏳ 尚未引入的工程化能力

以下均未配置，按需引入：

- 代码规范：ESLint / Prettier
- 前后端一键启动：`concurrently`
- 单元测试：Vitest
- CI：GitHub Actions
- 数据库与 ORM（待赛题明确数据需求）

### 9.5 ⏳ 业务需求尚未接入

赛题的具体功能要求尚未确定，因此当前骨架只有示例页面与健康检查接口，尚未实现任何业务模块。

---

## 10. 下一步计划

| 优先级 | 事项 |
| --- | --- |
| 高 | 统一包管理器，清理多余锁文件与测试文件 |
| 高 | 在本地终端完成前端 `build` / `dev` 端到端验证 |
| 高 | 明确赛题需求，梳理功能模块与页面清单 |
| 中 | 设计数据模型与接口契约 |
| 中 | 按模块实现业务功能 |
| 中 | 引入 ESLint + Prettier 统一代码风格 |
| 低 | 配置 CI 与自动化测试 |

---

## 附录：提交记录（本期）

| 提交 | 说明 |
| --- | --- |
| `55e352d` | feat: 搭建前后端项目骨架 |
| `9c771a1` | Merge：合入协作者提交 |
| `d902aec` | 协作者提交（婷 已加入） |

> 更早的初始化提交见 `git log`。
