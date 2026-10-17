# -*- coding: utf-8 -*-
"""环境预检：判断「能不能把本项目跑起来」，并给出可操作的修复建议。

用法（在 server/ 目录下）：
    .\\.venv\\Scripts\\python.exe preflight.py

不需要先启动服务，只检查依赖、配置与外部资源。
适用场景：拿到代码后先确认环境；或启动失败时快速定位原因。
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = 'OK', 'WARN', 'FAIL'
results: list[tuple[str, str, str]] = []


def record(name: str, level: str, note: str = '') -> None:
    results.append((name, level, note))
    icon = {OK: '✓', WARN: '!', FAIL: '✗'}[level]
    print(f'  [{icon}] {name:<32} {note}')


def load_env() -> dict[str, str]:
    env_file = ROOT / '.env'
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for line in env_file.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        values[key.strip()] = value.strip()
    return values


def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_python() -> None:
    v = f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'
    record('Python 版本', OK if sys.version_info >= (3, 11) else FAIL,
           v + ('' if sys.version_info >= (3, 11) else '（需要 ≥ 3.11）'))


def check_dependencies() -> None:
    required = [
        ('fastapi', 'FastAPI'), ('uvicorn', 'uvicorn'),
        ('sqlalchemy', 'SQLAlchemy'), ('aiomysql', 'aiomysql'),
        ('chromadb', 'ChromaDB'), ('langchain_text_splitters', 'LangChain 切片'),
        ('jose', 'python-jose(JWT)'), ('bcrypt', 'bcrypt'),
    ]
    missing = []
    for module, label in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(label)
    if missing:
        record('后端依赖', FAIL, f'缺少 {", ".join(missing)} → pip install -r requirements.txt')
    else:
        record('后端依赖', OK, f'{len(required)} 个关键模块已安装')


def check_env_file() -> dict[str, str]:
    env_file = ROOT / '.env'
    if not env_file.exists():
        record('.env 配置', WARN, '不存在 → 运行 start.ps1 会自动从 .env.example 生成')
        return {}
    record('.env 配置', OK, env_file.name)
    return load_env()


def check_mysql(env: dict[str, str]) -> None:
    dsn = env.get('DATABASE_URL') or ''
    if 'sqlite' in dsn:
        record('MySQL 连接', WARN, '已改用 SQLite（仅开发用）')
        return
    host = env.get('MYSQL_HOST') or '127.0.0.1'
    try:
        port = int(env.get('MYSQL_PORT') or 3306)
    except ValueError:
        port = 3306
    if port_open(host, port):
        record('MySQL 连接', OK, f'{host}:{port} 可达')
    else:
        record('MySQL 连接', FAIL,
               f'连不上 {host}:{port} → 启动 MySQL，或 docker compose up -d mysql')


def check_keys(env: dict[str, str]) -> None:
    if (env.get('ZHIPUAI_API_KEY') or '').strip():
        record('向量化（智谱 Key）', OK, '已配置 embedding-3')
    else:
        record('向量化（智谱 Key）', WARN,
               '未配置 → 使用内置离线向量化（零下载可跑通，语义效果有限）')
    if (env.get('LLM_API_KEY') or '').strip():
        record('大模型（生成）', OK, env.get('LLM_MODEL') or '已配置')
    else:
        record('大模型（生成）', WARN,
               '未配置 → 问答退化为「原文摘录」模式（有引用，非生成式）')


def check_queue(env: dict[str, str]) -> None:
    if (env.get('CELERY_TASK_ALWAYS_EAGER') or '').lower() == 'true':
        record('文档处理队列', OK, '进程内执行（无需 Redis）')
        return
    host, port = '127.0.0.1', 6379
    url = env.get('REDIS_URL') or ''
    if '://' in url:
        try:
            rest = url.split('://', 1)[1].split('/')[0]
            if ':' in rest:
                host, port_text = rest.rsplit(':', 1)
                port = int(port_text)
        except Exception:
            pass
    if port_open(host, port):
        record('文档处理队列', OK, f'Celery + Redis（{host}:{port}）')
    else:
        record('文档处理队列', FAIL,
               'CELERY_TASK_ALWAYS_EAGER=false 但 Redis 不可达 → '
               '上传的文档会直接失败；改为 true 或启动 Redis')


def check_dirs() -> None:
    problems = []
    for name in ('uploads', 'chroma_db'):
        directory = ROOT / 'data' / name
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / '.write_probe'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink(missing_ok=True)
        except OSError as exc:
            problems.append(f'{name}: {exc}')
    record('数据目录可写', FAIL if problems else OK,
           '; '.join(problems) if problems else 'data/uploads、data/chroma_db')


def check_chroma_cache() -> None:
    cache = Path(os.path.expanduser('~')) / '.cache' / 'chroma'
    try:
        cache.mkdir(parents=True, exist_ok=True)
        probe = cache / '.write_probe'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        record('Chroma 缓存目录', OK, str(cache))
    except OSError:
        record('Chroma 缓存目录', FAIL,
               f'{cache} 不可写 → 向量库初始化会失败（unable to open database file）')


def check_frontend() -> None:
    client = ROOT.parent / 'client'
    if (client / 'node_modules').is_dir():
        record('前端依赖', OK, 'client/node_modules 已存在')
    else:
        record('前端依赖', WARN, '未安装 → 在 client 目录执行 npm install')
    env_dev = client / '.env.development'
    if env_dev.exists():
        text = env_dev.read_text(encoding='utf-8-sig', errors='replace')
        mock = 'VITE_USE_MOCK=true' in text
        record('前端模式', OK, 'Mock（无需后端）' if mock else '连接真实后端')


def main() -> int:
    print('=' * 66)
    print('  RAG 知识问答系统 · 环境预检')
    print('=' * 66)

    check_python()
    check_dependencies()
    env = check_env_file()
    check_mysql(env)
    check_keys(env)
    check_queue(env)
    check_dirs()
    check_chroma_cache()
    check_frontend()

    fails = [r for r in results if r[1] == FAIL]
    warns = [r for r in results if r[1] == WARN]

    print('-' * 66)
    if fails:
        print(f'✗ {len(fails)} 项必须修复，否则无法正常使用：')
        for name, _, note in fails:
            print(f'   - {name}: {note}')
    else:
        print('✓ 必须项全部通过，可以启动服务。')
    if warns:
        print(f'! {len(warns)} 项非阻塞提醒（能跑通，但体验受限）：')
        for name, _, note in warns:
            print(f'   - {name}: {note}')
    print('=' * 66)
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
