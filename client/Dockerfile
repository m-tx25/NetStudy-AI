# ============================================================================
# 前端镜像：多阶段构建
#   阶段一 node:22-alpine —— 装依赖 + vite build
#   阶段二 nginx:alpine   —— 托管 dist + 反向代理 /api
#
# 构建（在项目根目录）：
#   docker build -f client/Dockerfile -t rag-web:latest client
# ============================================================================

# ---------------------------------------------------------------- 构建阶段
# 注意：用 node:22 而不是 node:18。
# 本项目 package.json 的 engines 是 "^20.19.0 || >=22.12.0"，
# Vite 8 在 Node 18 上会直接报 "Vite requires Node.js version 20.19+ or 22.12+"
# 并中断构建，所以 18 跑不通。
FROM node:22-alpine AS build

WORKDIR /app

# 淘宝镜像源（npmmirror）。可通过 --build-arg 覆盖。
ARG NPM_REGISTRY=https://registry.npmmirror.com

# 先只拷贝依赖清单，让这一层能被缓存：
# 只改业务代码时不会重新 npm install。
COPY package.json package-lock.json .npmrc ./

# npm ci 严格按 package-lock.json 安装，比 npm install 更可复现。
# 若要改用 npm install，把下一行换成：
#   npm config set registry $NPM_REGISTRY && npm install
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm ci --no-audit --no-fund

# 再拷源码（.env.production 会带进 VITE_API_BASE_URL=/api）
COPY . .

RUN npm run build


# ---------------------------------------------------------------- 运行阶段
FROM nginx:1.27-alpine AS runtime

# 用自定义配置替换默认站点
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf

# 构建产物
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
