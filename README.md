# chuangzhibei

传智杯 Web 方向的开发项目。

前端 **Vue 3 + Vite**，后端 **Node.js + Express**，用 pnpm workspace 统一管理。

## 项目结构

```
chuangzhibei/
├── client/                  # 前端：Vue 3 + Vite
│   ├── public/favicon.svg
│   ├── src/
│   │   ├── components/HelloWorld.vue
│   │   ├── App.vue
│   │   ├── main.js
│   │   └── style.css
│   ├── index.html
│   ├── vite.config.js       # 含 /api → http://localhost:3000 代理
│   └── package.json
├── server/                  # 后端：Express
│   ├── src/index.js
│   └── package.json
├── docs/collaboration.md    # 多人协作说明
├── package.json             # 根：统一脚本入口
└── pnpm-workspace.yaml
```

## 环境要求

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| Node.js | **>= 20.19**（推荐 22 / 24 LTS） | Vite 8 的最低要求 |
| pnpm | >= 9 | 仓库用 workspace，`npm` 装不了这种结构 |

> 检查：`node -v`、`pnpm -v`。若提示「不是内部或外部命令」，说明 Node.js 还没装或是没加进 `PATH`。

## 快速开始

```bash
git clone https://github.com/m-tx25/chuangzhibei.git
cd chuangzhibei

# 设置自己的身份（重要！否则提交作者是别人的名字）
git config user.name "你的名字"
git config user.email "你的邮箱"

# 安装前后端依赖（在仓库根目录执行，一次装两边）
pnpm install

# 同时启动前端 + 后端
pnpm dev
```

启动后：

- 前端 <http://localhost:5173>
- 后端 <http://localhost:3000>（健康检查 <http://localhost:3000/api/health>）

首页上的「检测后端」按钮会请求 `/api/health`，用于确认前后端已打通。

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `pnpm dev` | 并行启动前端 (5173) 与后端 (3000) |
| `pnpm dev:client` | 只启动前端 Vite |
| `pnpm dev:server` | 只启动后端 Express（`node --watch`，改完自动重启） |
| `pnpm build` | 构建前端到 `client/dist/` |
| `pnpm preview` | 本地预览生产构建 |

## 开发约定

- **接口统一走 `/api/**` 相对路径**，不要写死 `http://localhost:3000`。
  开发期由 Vite 代理转发（见 `client/vite.config.js`），既免跨域，上线换域名也不用改代码。
- 后端端口用环境变量覆盖：`PORT=4000 pnpm dev:server`（默认 3000）。
  改了后端端口，记得同步改 `vite.config.js` 里的 `proxy.target`。
- `@` 已别名到 `client/src`，import 可以写 `@/components/xxx.vue`。
- 新增后端路由建议拆到 `server/src/routes/` 下再挂载，别都堆在 `index.js`。

## 文档

- [多人协作说明](docs/collaboration.md) — 邀请协作者、保护 `main`、分支/PR 流程、令牌与 SSH 配置

---

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

> npm 侧不受影响：Node 自带独立的 CA 根证书列表，实测 `registry.npmjs.org` 可正常访问。
> 若日后出现 `UNABLE_TO_VERIFY_LEAF_SIGNATURE`，可设
> `NODE_EXTRA_CA_CERTS=<本仓库>/.git-trust/ca-bundle-plus-steamtools.pem`。
