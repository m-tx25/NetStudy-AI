"""Celery 应用。

队列用于文档解析 + 切片 + 向量化：这三步是 CPU/IO 密集的，
若放在请求线程里同步执行，上传大文件时会把事件循环阻塞住，前端一直转圈。

本地没有 Redis 时可以：
  1. 把 .env 里 CELERY_TASK_ALWAYS_EAGER 设为 true —— 任务在当前进程内同步执行；
  2. 或保持 false 并在另一终端运行 `celery -A app.tasks.celery_app worker -l info`。

`dispatch_process_document` 负责决定「投递到队列」还是「就地执行」，
业务代码只需调用它，不必关心部署形态。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

# 持有 eager-async 模式下创建的后台任务引用，防止被垃圾回收提前取消
_background_tasks: set[asyncio.Task] = set()

# 并发闸门：2 核 4GB 的服务器同时解析多个 PDF 会把内存与 CPU 打满，
# 解析默认串行；对比/研究这类 LLM 任务也单独限流，避免同时打满模型配额。
_parse_gate = asyncio.Semaphore(max(1, settings.MAX_CONCURRENT_PARSE_TASKS))
_llm_gate = asyncio.Semaphore(max(1, settings.MAX_CONCURRENT_LLM_TASKS))

# Celery worker 里跑的是同步函数（process_document_sync），用线程信号量限制。
# 不加这个的话，`MAX_CONCURRENT_PARSE_TASKS` 只在本地 eager-async 分支生效，
# 真上了 Redis + worker 就退化成"由 --concurrency 决定"，与配置不符。
_parse_gate_sync = threading.BoundedSemaphore(max(1, settings.MAX_CONCURRENT_PARSE_TASKS))


async def _limited(coro, gate: asyncio.Semaphore):
    """在信号量内执行协程：超过并发上限的任务排队等待而不是被拒绝。"""
    async with gate:
        return await coro

celery_app = Celery(
    "chuangzhibei",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # 大文件解析可能较久，放宽软/硬超时
    task_soft_time_limit=60 * 30,
    task_time_limit=60 * 60,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
    broker_connection_retry_on_startup=True,
)


def run_async(coro: Any) -> Any:
    """在同步的 Celery worker 里跑协程。

    Celery 的 prefork worker 没有运行中的事件循环，直接 asyncio.run 即可；
    但 eager 模式是在 FastAPI 的请求线程里执行的，那里可能已有事件循环，
    因此需要检测并另起一个循环，避免 "asyncio.run() cannot be called from a
    running event loop"。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # 已有事件循环（eager 模式）：在新线程里跑，避免嵌套
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def dispatch_process_document(document_id: str, *, reindex: bool = False) -> dict[str, Any]:
    """把「处理文档」投递到队列；队列不可用时报告原因，由调用方决定如何提示。"""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        if settings.CELERY_EAGER_ASYNC:
            # 后台异步执行：立即返回，让接口先把 status=processing 交给前端，
            # 解析在事件循环里继续跑。这样本地无 Redis 也能得到与
            # 「Redis + Celery worker」一致的异步语义（前端需要轮询）。
            from app.services.pipeline import process_document_async

            task = asyncio.create_task(
                _limited(
                    process_document_async(document_id, reindex=reindex),
                    _parse_gate,
                )
            )
            # 持有引用，避免任务被垃圾回收提前取消（asyncio 的已知陷阱）
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
            return {"queued": True, "mode": "eager-async"}

        # 同步执行，异常直接抛给调用方
        process_document.run(document_id, reindex)
        return {"queued": False, "mode": "eager"}

    try:
        async_result = process_document.delay(document_id, reindex)
        return {"queued": True, "mode": "celery", "taskId": async_result.id}
    except Exception as exc:  # broker 连不上（如未启动 Redis）
        logger.warning("投递 Celery 任务失败：%s", exc)
        return {"queued": False, "mode": "failed", "error": str(exc)}


def check_queue_health() -> dict[str, Any]:
    """探测 broker 是否可用，供 /api/health 展示。"""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        if settings.CELERY_EAGER_ASYNC:
            return {
                "mode": "eager-async",
                "available": True,
                "detail": "无需 Redis：任务在后台协程中异步执行，接口立即返回 processing",
            }
        return {
            "mode": "eager",
            "available": True,
            "detail": "任务在进程内同步执行（接口会等待解析完成后才返回）",
        }

    try:
        with celery_app.connection_or_acquire() as connection:
            connection.ensure_connection(max_retries=1, timeout=2)
        return {"mode": "celery", "available": True, "broker": settings.broker_url}
    except Exception as exc:
        return {
            "mode": "celery",
            "available": False,
            "broker": settings.broker_url,
            "error": str(exc),
            "hint": "Redis 未启动：可运行 redis-server，或把 CELERY_TASK_ALWAYS_EAGER 设为 true",
        }


@celery_app.task(name="app.tasks.process_document", bind=True, max_retries=2)
def process_document(self, document_id: str, reindex: bool = False) -> dict[str, Any]:
    """解析文档 → 切片 → 向量化 → 入库。"""
    from app.services.pipeline import process_document_sync

    # 线程信号量：Worker 进程内同时最多解析 MAX_CONCURRENT_PARSE_TASKS 个文档
    acquired = _parse_gate_sync.acquire(blocking=False)
    if not acquired:
        # 拿不到就排队等，而不是失败 —— 与 eager 模式"排队等待"的语义一致
        _parse_gate_sync.acquire()
        acquired = True
    try:
        return process_document_sync(document_id, reindex=reindex)
    except Exception as exc:  # 交给 Celery 重试，同时把失败原因写回文档状态
        logger.exception("处理文档失败 id=%s", document_id)
        try:
            from app.services.pipeline import mark_failed_sync

            mark_failed_sync(document_id, str(exc))
        except Exception:  # pragma: no cover
            logger.exception("写入失败状态时又出错 id=%s", document_id)

        if self.request.retries < (self.max_retries or 0):
            raise self.retry(exc=exc, countdown=5)
        return {"ok": False, "documentId": document_id, "error": str(exc)}
    finally:
        if acquired:
            _parse_gate_sync.release()

def dispatch_comparison(comparison_id: str) -> dict[str, Any]:
    """把「多篇论文对比」投递到后台。

    与文档解析同一套语义：eager-async 模式下用 asyncio.create_task 在后台跑，
    接口立刻返回 pending，前端轮询进度；装了 Redis 则走 Celery。
    """
    if settings.CELERY_TASK_ALWAYS_EAGER:
        if settings.CELERY_EAGER_ASYNC:
            from app.services.compare import run_comparison

            task = asyncio.create_task(_limited(run_comparison(comparison_id), _llm_gate))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
            return {"queued": True, "mode": "eager-async"}
        run_async(_run_comparison_sync(comparison_id))
        return {"queued": False, "mode": "eager"}

    try:
        run_comparison_task.delay(comparison_id)
        return {"queued": True, "mode": "celery"}
    except Exception as exc:  # broker 不可用
        logger.warning("对比任务投递失败：%s", exc)
        return {"queued": False, "mode": "failed", "error": str(exc)}


async def _run_comparison_sync(comparison_id: str) -> None:
    from app.services.compare import run_comparison

    await run_comparison(comparison_id)


@celery_app.task(name="app.tasks.run_comparison", bind=True, max_retries=1)
def run_comparison_task(self, comparison_id: str) -> dict[str, Any]:
    from app.services.compare import run_comparison

    return run_async(run_comparison(comparison_id))

def dispatch_research(brief_id: str) -> dict[str, Any]:
    """把「研究辅助」投递到后台（与文档解析同一套语义）。"""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        if settings.CELERY_EAGER_ASYNC:
            from app.services.research import run_brief

            task = asyncio.create_task(_limited(run_brief(brief_id), _llm_gate))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
            return {"queued": True, "mode": "eager-async"}
        run_async(_run_research_sync(brief_id))
        return {"queued": False, "mode": "eager"}

    try:
        run_research_task.delay(brief_id)
        return {"queued": True, "mode": "celery"}
    except Exception as exc:
        logger.warning("研究辅助任务投递失败：%s", exc)
        return {"queued": False, "mode": "failed", "error": str(exc)}


async def _run_research_sync(brief_id: str) -> None:
    from app.services.research import run_brief

    await run_brief(brief_id)


@celery_app.task(name="app.tasks.run_research", bind=True, max_retries=1)
def run_research_task(self, brief_id: str) -> dict[str, Any]:
    from app.services.research import run_brief

    return run_async(run_brief(brief_id))

def dispatch_report(report_id: str) -> dict[str, Any]:
    """把「生成报告」投递到后台（与文档解析同一套语义）。"""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        if settings.CELERY_EAGER_ASYNC:
            from app.services.reports import run_report

            task = asyncio.create_task(run_report(report_id))
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
            return {"queued": True, "mode": "eager-async"}
        run_async(_run_report_sync(report_id))
        return {"queued": False, "mode": "eager"}

    try:
        run_report_task.delay(report_id)
        return {"queued": True, "mode": "celery"}
    except Exception as exc:
        logger.warning("报告任务投递失败：%s", exc)
        return {"queued": False, "mode": "failed", "error": str(exc)}


async def _run_report_sync(report_id: str) -> None:
    from app.services.reports import run_report

    await run_report(report_id)


@celery_app.task(name="app.tasks.run_report", bind=True, max_retries=1)
def run_report_task(self, report_id: str) -> dict[str, Any]:
    from app.services.reports import run_report

    return run_async(run_report(report_id))
