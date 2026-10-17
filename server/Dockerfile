# ============================================================================
# 后端镜像：Python + FastAPI
#
# 同一镜像同时用于 api 与 celery_worker 两个容器
# （compose 里 celery_worker 复用本镜像，只改启动命令）。
#
# 构建（在项目根目录）：
#   docker build -f server/Dockerfile -t rag-backend:latest server
# ============================================================================

# 注意：用 python:3.12-slim 而不是 3.10。
# 本项目依赖的实际版本要求（pip 元数据）：
#   sqlalchemy 2.1  Requires-Python >=3.11
#   onnxruntime 1.31（chromadb 的传递依赖）  >=3.11
#   numpy 2.x                                >=3.12
# 在 3.10 上 pip 只能解析到更老的版本，无法复现当前已验证的组合，
# 且项目 README 声明要求 Python >=3.11。3.12 是能装齐全部依赖的最低稳妥选择。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    PYTHONPATH=/app

WORKDIR /app

# 运行期系统依赖：
#   curl      —— 健康检查用
#   libmagic1 —— 文档类型探测（部分解析器依赖）
#   tzdata    —— 时区
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libmagic1 tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（改动代码不会让这一层缓存失效）
COPY requirements.txt ./
RUN pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 再拷应用代码。
# 只拷 app/ 与预检脚本：**不拷贝 .env**，避免把密钥烘进镜像层
# （.env 由 docker-compose 的 env_file 在运行时注入）。
COPY app ./app
COPY preflight.py ./

# 数据目录（上传文件 + ChromaDB）。compose 里会用宿主目录挂载覆盖它。
RUN mkdir -p /app/data/uploads /app/data/chroma_db

EXPOSE 8000

# 容器内探活：/api/health 会实际检查 MySQL、向量库与队列
HEALTHCHECK --interval=20s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# 生产环境不开 --reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
