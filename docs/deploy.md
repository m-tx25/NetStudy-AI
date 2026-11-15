# 部署到服务器（2 核 4GB / 50GB 磁盘）

> 面向评审演示环境。两条路线：**A. Docker Compose（推荐）**、**B. 裸机 systemd + Nginx**。
> 部署完跑一句 `./scripts/verify-deploy.sh https://你的域名` 自检。

## 零、先看这三个坑（都踩过）

| 坑 | 现象 | 处理 |
| --- | --- | --- |
| **Chroma 重启后索引丢失** | 检索报 `Error finding id`，接口 200 但引用为 0 | 重启 Chroma 后必须重新索引，见第 5 节 |
| **Nginx 上传上限比后端小** | 上传 64~100MB 的 PDF 直接 413 | `client_max_body_size` 已改成 `120m`，跟着 `MAX_UPLOAD_SIZE_MB` 走 |
| **TEMP 目录不可写** | Chroma 启动即 `SqliteError code 14 unable to open database file` | 容器内不用管；裸机部署要把 `TEMP` 指到可写目录 |

---

## 一、准备（两条路线都要）

### 1.1 服务器基础

```bash
# 建议 2C4G 的最低配置
sudo apt update && sudo apt install -y curl git
# 时区
sudo timedatectl set-timezone Asia/Shanghai
```

### 1.2 拉代码

```bash
git clone https://github.com/m-tx25/NetStudy-AI.git
cd NetStudy-AI
git checkout main
```

### 1.3 必须改的三个配置

```bash
cp server/.env.example server/.env
vi server/.env
```

| 变量 | 改成什么 | 不改会怎样 |
| --- | --- | --- |
| `SECRET_KEY` | `openssl rand -hex 32` 的输出 | 用默认值等于 JWT 可被伪造 |
| `ZHIPUAI_API_KEY` | 你的智谱 Key（`xxxx.xxxx` 格式） | 检索退化成 Chroma 默认嵌入，中文效果差 |
| `LLM_API_KEY` / `LLM_MODEL` | 你的对话模型 Key | 问答只会返回「未配置模型」 |
| `MYSQL_PASSWORD` | 见 1.4 | 后端连不上库 |
| `DEBUG` | `false` | 日志里会打 SQL 与堆栈 |
| `CORS_ORIGINS` | `https://你的域名` | 只影响跨域直连调试 |

### 1.4 compose 的变量

```bash
cp .env.example .env
vi .env            # 改 MYSQL_ROOT_PASSWORD（默认值是 change-me-strong-password）
```

> `server/.env` 里的 `MYSQL_PASSWORD` 要和根目录 `.env` 的 `MYSQL_ROOT_PASSWORD` 一致。

---

## 二、路线 A：Docker Compose（推荐）

### 2.1 装 Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
docker compose version    # 确认是 v2
```

### 2.2 起服务

```bash
docker compose up -d --build
docker compose ps          # 六个容器都应是 running / healthy
```

首次构建约 5~10 分钟（要装 node 依赖 + Python 依赖）。

### 2.3 首次索引（必须做）

```bash
# 演示数据：把论文放进 server/data/demo_papers/ 后
docker compose exec backend python demo_seed.py

# 或者：把已有文档全部重新索引（调用 embedding 接口，有费用）
docker compose exec backend python reindex_all.py
```

### 2.4 自检

```bash
./scripts/verify-deploy.sh http://服务器IP
```

---

## 三、路线 B：裸机（systemd + Nginx）

> 适合不想装 Docker 的情况。**MySQL 与 Chroma 需要自己起**。

### 3.1 依赖

```bash
sudo apt install -y python3.12 python3.12-venv python3-pip nginx mysql-server
curl -LsSf https://astral.sh/uv/install.sh | sh   # 可选，用 uv 装 Python 依赖更快
```

### 3.2 Chroma（服务模式）

```bash
sudo mkdir -p /srv/matrix-scholar/{data,chroma,tmp}
sudo useradd -r -s /bin/false matrix || true
sudo chown -R matrix:matrix /srv/matrix-scholar

# 用 pip 装一份 chroma cli（版本尽量与 requirements 里的 chromadb 对齐）
sudo -u matrix /srv/matrix-scholar/venv/bin/pip install 'chromadb==1.5.9'
```

`/etc/systemd/system/chroma.service`：

```ini
[Unit]
Description=Chroma vector DB
After=network.target

[Service]
Type=simple
User=matrix
WorkingDirectory=/srv/matrix-scholar
# TEMP 必须可写，否则 Chroma 建库时报 unable to open database file
Environment=TEMP=/srv/matrix-scholar/tmp
Environment=TMP=/srv/matrix-scholar/tmp
ExecStart=/srv/matrix-scholar/venv/bin/chroma run --path /srv/matrix-scholar/chroma --port 8000
Restart=always
# 给足时间让它把写入落盘，别 SIGKILL（会导致 compactor 卡死）
TimeoutStopSec=60
[Install]
WantedBy=multi-user.target
```

### 3.3 后端

```bash
cd /srv/matrix-scholar/app
python3.12 -m venv .venv
.venv/bin/pip install -r server/requirements.txt
cp server/.env.example server/.env && vi server/.env   # 见 1.3
```

`/etc/systemd/system/matrix-scholar-api.service`：

```ini
[Unit]
Description=Matrix-Scholar API
After=network.target mysql.service chroma.service

[Service]
Type=simple
User=matrix
WorkingDirectory=/srv/matrix-scholar/app/server
Environment=PYTHONUNBUFFERED=1
# 单 worker：解析/LLM 的并发闸门是进程内的，多 worker 会各限各的
ExecStart=/srv/matrix-scholar/app/server/.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 3000 --workers 1 --proxy-headers
Restart=always
[Install]
WantedBy=multi-user.target
```

> **不要开多 worker**：`MAX_CONCURRENT_PARSE_TASKS` 用的是进程内信号量，
> 起 4 个 worker 就等于允许 4 个并发解析，2C4G 会 OOM。

### 3.4 前端

```bash
cd client
npm ci            # 或 pnpm i
npm run build     # 产物在 client/dist
sudo rsync -a --delete dist/ /var/www/matrix-scholar/
```

Nginx 站点（`/etc/nginx/sites-available/matrix-scholar`）：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /var/www/matrix-scholar;
    index index.html;

    # 必须 >= 后端 MAX_UPLOAD_SIZE_MB（默认 100MB）
    client_max_body_size 120m;

    location /api/ {
        proxy_pass http://127.0.0.1:3000;   # 末尾不要加斜杠
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection "";
        # SSE：关缓冲、关压缩，否则打字机效果失效
        proxy_buffering off;
        proxy_cache off;
        gzip off;
        proxy_read_timeout 600s;
    }

    location /assets/ { expires 1y; add_header Cache-Control "public, immutable"; }
    location / { try_files $uri $uri/ /index.html; }
    location = /index.html { add_header Cache-Control "no-cache"; }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/matrix-scholar /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 3.5 首次索引

```bash
sudo -u matrix /srv/matrix-scholar/app/server/.venv/bin/python \
  /srv/matrix-scholar/app/server/demo_seed.py
```

---

## 四、开机自启与重启顺序

Docker 路线：容器都是 `restart: unless-stopped`，开机会自动起，**顺序由 `depends_on` 保证**（chroma → backend）。

裸机路线：

```bash
sudo systemctl enable --now mysql chroma matrix-scholar-api nginx
```

---

## 五、⚠️ Chroma 重启后必须重新索引

这个版本的 Chroma 不会把 HNSW 索引持久化到磁盘（实测 `taskkill /F`、
`Ctrl+C`、`Ctrl+Break` 三种关闭方式都不会写 `*.bin`）。所以：

| 场景 | 要做什么 |
| --- | --- |
| 服务器重启 | `docker compose exec backend python reindex_all.py` |
| `docker compose restart chroma` | 同上 |
| `docker compose up -d --build`（只重建 backend） | 不用，Chroma 没重启 |
| 重建 chroma 容器/清空卷 | 同上，且要重新 `demo_seed.py` |

索引耗时取决于文档数（25 篇约 2 分钟），会产生 embedding 费用。

**判断是否需要重建**：

```bash
./dev.cmd --check          # Windows 本地
# 或看日志里是否有：Error finding id / Error loading hnsw index
```

---

## 六、备份与恢复

```bash
# MySQL
docker compose exec mysql mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" chuangzhibei \
  | gzip > backup-$(date +%F).sql.gz

# 上传的原始文件
tar czf uploads-$(date +%F).tar.gz server/data/uploads

# 向量库（可选：重建索引也能恢复，但费钱）
docker run --rm -v rag_chroma-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/chroma-$(date +%F).tar.gz -C /data .
```

恢复顺序：MySQL → uploads → Chroma → **重新索引**。

---

## 七、日常运维

```bash
# 健康
curl -s http://127.0.0.1/api/health | python3 -m json.tool

# 存储与配额
curl -s -H "Authorization: Bearer <token>" http://127.0.0.1/api/storage/status

# 日志（后端最近 200 行）
docker compose logs --tail=200 backend

# 清理无引用的孤儿文件（默认干跑）
docker compose exec backend python cleanup_storage.py
docker compose exec backend python cleanup_storage.py --apply --older-than 24
```

磁盘水位：`df -h`，`/api/storage/status` 的 `disk.freeGb` 低于 `STORAGE_MIN_FREE_GB`（5GB）时上传会被拒绝。

---

## 八、安全清单（上线前逐项勾）

- [ ] `SECRET_KEY` 已换成随机值
- [ ] `MYSQL_ROOT_PASSWORD` 已改，且没写进仓库
- [ ] `DEBUG=false`
- [ ] MySQL / Chroma / 后端端口**不对公网暴露**（compose 里只有前端 80）
- [ ] 演示账号 `demo/123456` 已改密码，或上线前删掉
- [ ] `server/data/uploads` 与 MySQL 数据卷已纳入备份
- [ ] 配了 HTTPS（certbot 一行命令；SSE 需要 `proxy_read_timeout` 足够大）
- [ ] `./scripts/verify-deploy.sh https://域名` 全绿

---

## 九、常见故障对照

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 502 Bad Gateway | 后端没起 / 端口不对 | `docker compose ps`、`logs backend` |
| 上传 413 | Nginx 限制小于后端 | `client_max_body_size` 调到 ≥ 后端上限 + 20MB |
| 回答一次性蹦出来，没有打字效果 | Nginx 缓冲没关 | `proxy_buffering off; gzip off;` |
| 引用为 0，但接口 200 | Chroma 索引丢失 | 重新索引 |
| 启动报 `1071 Specified key was too long` | MySQL 版本/字符集导致索引超长 | 已修（`source_id` 191、title 前缀索引）；自建库确认 utf8mb4 |
| 上传报「文件不完整（缺少 %%EOF）」 | 上传被代理截断 | 检查 Nginx/CLB 的 body 限制与超时 |
| 容器起不来，日志 `unable to open database file` | TEMP 不可写 | 裸机：给 `TEMP` 可写目录；容器：检查卷权限 |
