"""清理上传目录中的「孤儿文件」。

孤儿 = 上传目录里存在、但数据库 documents.stored_path 没有引用的文件
（通常是上传中断、测试残留、早期版本删记录时没删文件）。

安全原则：
  - **有引用的原始 PDF 永不删除**（需求 9：未经用户确认不得自动删除）；
  - 默认干跑，只打印将删除的内容；加 --apply 才真正删除；
  - 只删修改时间早于 --older-than 小时的文件，避免误删正在上传的半成品。

用法（在 server 目录）：
    python cleanup_storage.py                       # 干跑，默认 24 小时
    python cleanup_storage.py --older-than 1        # 干跑，1 小时前的孤儿
    python cleanup_storage.py --apply --older-than 1
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.services.storage import cleanup_orphans_async


def main() -> None:
    parser = argparse.ArgumentParser(description="清理上传目录中的孤儿文件")
    parser.add_argument("--older-than", type=int, default=24, help="只清理 N 小时前的文件")
    parser.add_argument(
        "--apply", action="store_true", help="真正删除（默认只干跑展示）"
    )
    args = parser.parse_args()

    result = asyncio.run(
        cleanup_orphans_async(older_than_hours=args.older_than, dry_run=not args.apply)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.apply:
        print("\n这是干跑结果；确认无误后加 --apply 执行删除。")


if __name__ == "__main__":
    main()
