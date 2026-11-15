"""评审演示模式：预置论文 + 缓存解析结果。

把指定目录下的 PDF / Word / Markdown 论文导入「评审演示论文」知识库，
并立即完成解析（章节、切片、向量），这样演示时打开就能看到结构和检索结果，
不用现场等解析。

用法（在 server 目录）：
    python demo_seed.py                      # 读取 DEMO_PAPERS_DIR（默认 ./data/demo_papers）
    python demo_seed.py --dir D:\\papers
    python demo_seed.py --username demo --force   # 已存在也重新解析

说明：
  - 原始文件复制到上传目录并保留，不会自动删除；
  - 已按内容哈希去重，重复执行不会产生重复文档；
  - 解析是同步执行的（脚本场景），生产 API 仍是后台异步任务。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Document, KnowledgeBase, User, now_utc
from app.services.pipeline import process_document_sync
from app.services.uploads import ALLOWED_EXTENSIONS, uploads_dir
from app.utils.ids import new_id

DEMO_KB_NAME = "评审演示论文"
SUPPORTED = ALLOWED_EXTENSIONS


def _collect_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        item
        for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() in SUPPORTED
    )


async def _ensure_user(db, username: str) -> User:
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None:
        raise SystemExit(f"用户不存在：{username}（请先注册或改用 --username）")
    return user


async def _ensure_kb(db, user: User) -> KnowledgeBase:
    kb = (
        await db.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_type == "user")
            .where(KnowledgeBase.owner_id == user.id)
            .where(KnowledgeBase.name == DEMO_KB_NAME)
        )
    ).scalar_one_or_none()
    if kb is None:
        kb = KnowledgeBase(
            id=new_id("kb"),
            owner_type="user",
            owner_id=user.id,
            name=DEMO_KB_NAME,
            description="评审演示用的预置论文（解析结果已缓存）",
            embedding_model="embedding-3",
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
    return kb


async def seed(folder: Path, username: str, force: bool) -> None:
    files = _collect_files(folder)
    if not files:
        print(f"没有找到可导入的文件：{folder}（支持 {', '.join(sorted(SUPPORTED))}）")
        return

    target_dir = uploads_dir()
    summary: list[dict] = []

    async with SessionLocal() as db:
        user = await _ensure_user(db, username)
        kb = await _ensure_kb(db, user)

        for path in files:
            data = path.read_bytes()
            content_hash = hashlib.sha256(data).hexdigest()
            existing = (
                await db.execute(
                    select(Document)
                    .where(Document.knowledge_base_id == kb.id)
                    .where(Document.content_hash == content_hash)
                )
            ).scalar_one_or_none()

            if existing is not None and not force:
                summary.append(
                    {"file": path.name, "status": "skipped", "documentId": existing.id}
                )
                continue

            document_id = new_id("doc")
            target = target_dir / f"{document_id}{path.suffix.lower()}"
            shutil.copy2(path, target)
            if existing is None:
                document = Document(
                    id=document_id,
                    knowledge_base_id=kb.id,
                    name=path.name[:512],
                    uploaded_by=user.id,
                    stored_path=str(target),
                    content_hash=content_hash,
                    size=len(data),
                    chunks=0,
                    status="processing",
                    enabled=True,
                    uploaded_at=now_utc(),
                )
                db.add(document)
                await db.commit()
            else:
                document = existing
                document.stored_path = str(target)
                document.status = "processing"
                document.updated_at = now_utc()
                await db.commit()

            result = process_document_sync(document.id, reindex=True)
            summary.append(
                {
                    "file": path.name,
                    "status": "parsed" if result.get("ok") else "failed",
                    "documentId": document.id,
                    "chunks": result.get("chunks"),
                    "sections": result.get("sections"),
                    "error": result.get("error"),
                }
            )

    print(json.dumps({"knowledgeBase": DEMO_KB_NAME, "items": summary}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="预置评审演示论文并缓存解析结果")
    parser.add_argument(
        "--dir",
        default=settings.DEMO_PAPERS_DIR,
        help="论文目录（默认取 DEMO_PAPERS_DIR）",
    )
    parser.add_argument("--username", default="demo", help="导入到哪个用户的库")
    parser.add_argument("--force", action="store_true", help="已存在也重新解析")
    args = parser.parse_args()
    asyncio.run(seed(Path(args.dir), args.username, args.force))


if __name__ == "__main__":
    main()
