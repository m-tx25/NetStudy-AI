"""主键生成：带前缀的短 ID，与前端 mock 数据形态保持一致（kb_xxx / doc_xxx）。"""

import secrets

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def new_id(prefix: str, length: int = 12) -> str:
    body = "".join(secrets.choice(_ALPHABET) for _ in range(length))
    return f"{prefix}_{body}"
