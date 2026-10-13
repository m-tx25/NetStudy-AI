"""量化：无依据问题在弱向量模型下的实际得分，用于确定「证据门槛」。

对比两组问题：
  A. 知识库中确实没有的（量子纠缠）—— 期望得分低 / 词面命中 0
  B. 知识库中确实有的（报销流程）  —— 期望得分高 / 词面命中 > 0
"""
import asyncio

from app.core.database import SessionLocal
from app.services import vectorstore


async def main() -> None:
    questions = [
        ("无关-量子纠缠", "请用一句话解释量子纠缠，并给出一个生活化类比。"),
        ("无关-天气预报", "明天北京的天气怎么样？"),
        ("无关-写代码", "用 Python 写一个快速排序"),
        ("有关-报销流程", "报销流程分几步？单张发票超过多少金额需要附加采购申请单编号？"),
        ("有关-RAG流程", "RAG 的检索流程是怎样的？"),
        ("有关-工作时间", "标准工作制每天几小时？核心工作时段是几点到几点？"),
    ]

    async with SessionLocal() as db:
        print(f"{'问题':<14} {'Top1分':>7} {'词面':>5}  {'是否命中':<8} Top1 来源")
        print("-" * 92)
        for label, question in questions:
            hits = vectorstore.search(db, question, owner_id="user_demo", top_k=3, score_threshold=0.0)
            if not hits:
                print(f"{label:<14} {'-':>7} {'-':>5}  {'无':<8}")
                continue
            top = hits[0]
            lexical = vectorstore.lexical_score(question, top.content)
            print(
                f"{label:<14} {top.score:>7.3f} {lexical:>5}  "
                f"{'是' if lexical > 0 else '否':<8} {top.document_name}"
            )


asyncio.run(main())
