# chuangzhibei

传智杯 Web 方向的开发项目，前后端分离。

## 文档

- [开发报告](docs/development-report.md) — 已完成工作、技术选型、验证记录、已知问题与下一步计划
- [多人协作说明](docs/collaboration.md) — 邀请协作者、保护 `main`、分支/PR 流程、令牌与 SSH 配置

## 项目结构

```
.
├── client/                 前端：Vue 3 + Vite
│   ├── index.html
│   ├── vite.config.js      开发时把 /api 代理到后端，避免跨域
│   └── src/
│       ├── main.js         入口
│       ├── App.vue         根组件
│       ├── assets/         样式与静态资源
│       ├── router/         路由
│       ├── stores/         Pinia 状态
│       └── views/          页面
└── server/                 后端：Node.js + Express
    ├── .env.example        环境变量模板
    └── src/index.js        入口，含 /api/health 健康检查
```

## 环境要求

- Node.js ≥ 20（本机实测 v24.19）
- 包管理器：**npm**（请勿使用 pnpm / yarn，以免生成冲突的锁文件）

## 安装

```bash
# 前端
cd client
npm install

# 后端
cd ../server
npm install
```

## 启动开发环境（需要两个终端）

```bash
# 终端 1：后端，http://localhost:3000
cd server
npm run dev

# 终端 2：前端，http://localhost:5173
cd client
npm run dev
```

打开 <http://localhost:5173>，首页会显示"后端连接正常"表示前后端已打通。

## 常用命令

| 位置 | 命令 | 说明 |
| --- | --- | --- |
| `client/` | `npm run dev` | 启动前端开发服务器 |
| `client/` | `npm run build` | 构建生产包到 `client/dist` |
| `client/` | `npm run preview` | 预览构建结果 |
| `server/` | `npm run dev` | 启动后端（nodemon 热重载） |
| `server/` | `npm start` | 启动后端（生产模式） |

## 环境适配与自检（本机已配置，协作者可选）

本机在受限环境（DSH）下安装依赖与启动开发服务器时，遇到过两个 `EPERM` 问题。
两处适配都已落地，**普通 Windows / macOS / Linux 环境下无需这些步骤即可正常开发**。

### 1. 依赖缓存 `client/.npmrc`、`server/.npmrc`

npm 默认缓存目录在用户目录 `C:\Users\<user>\AppData\Local\npm-cache`，受限环境下
该路径不可写，`npm install` 会直接报 `EPERM`。两个包内各放了一份 `.npmrc`：

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
