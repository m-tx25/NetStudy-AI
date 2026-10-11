"""Prompt 模板：RAG 系统提示与上下文拼装。

设计要点：
  1. 强约束「只依据资料回答」，资料不足时明确说不知道，抑制幻觉；
  2. 要求标注引用编号 [1][2]，与前端「引用来源」面板对齐；
  3. 历史对话只取最近若干轮，避免上下文无限膨胀。
"""

from __future__ import annotations

from app.services.vectorstore import RetrievedChunk

SYSTEM_PROMPT = """你是一个严谨的企业知识库问答助手。请遵守以下规则：

1. **只依据「参考资料」回答**，不要使用你自身的记忆补充事实。
2. 资料中没有依据时，明确回答「知识库中未找到相关依据」，并说明还需要补充哪类文档，
   不要编造内容，也不要猜测。
3. 引用资料时在句末标注对应编号，例如 [1]、[2]，编号必须与参考资料一致。
4. 使用 Markdown 组织答案：结论先行，需要分点时用有序或无序列表，
   涉及步骤、参数、对比时使用表格，涉及代码时使用围栏代码块。
5. 保持简洁准确，不要重复问题本身，不要输出与问题无关的内容。
"""

NO_CONTEXT_ANSWER = (
    "知识库中没有检索到与该问题相关的依据，因此我无法回答。\n\n"
    "建议：\n"
    "- 确认已在输入框上方勾选包含相关文档的知识库；\n"
    "- 若文档尚未上传，请先到「知识库管理」上传并等待解析完成（状态为「已就绪」）；\n"
    "- 也可以换一种更具体的问法，或调大检索数量 Top-K 后重试。"
)


def build_context(chunks: list[RetrievedChunk], snippet_limit: int = 600) -> str:
    """把检索结果拼成带编号的参考资料块。"""
    if not chunks:
        return ""

    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.content.strip()
        if len(text) > snippet_limit:
            text = f"{text[:snippet_limit]}…"
        location = f"第 {chunk.page} 页" if chunk.page else f"第 {chunk.ordinal + 1} 段"
        blocks.append(
            f"[{index}]（来源：{chunk.document_name} · {location} · 相关度 {chunk.score:.2f}）\n{text}"
        )
    return "\n\n".join(blocks)


def build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    context = build_context(chunks)
    if not context:
        return f"参考资料：\n（无）\n\n用户问题：{question}"

    return (
        f"参考资料：\n{context}\n\n"
        f"用户问题：{question}\n\n"
        "请依据上述参考资料作答，并在引用处标注编号。"
    )


def build_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    """组装完整的 messages：system + 历史多轮 + 当前问题（带资料）。

    history 形如 [("user", "..."), ("assistant", "...")]，按时间正序。
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    for role, content in history or []:
        if role not in ("user", "assistant") or not content:
            continue
        # 历史中的助手回答不重复携带引用资料，避免上下文爆炸
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": build_user_prompt(question, chunks)})
    return messages


def title_from_question(question: str, limit: int = 20) -> str:
    """用首句生成会话标题，与前端 utils/format.js 的 titleFromQuestion 行为一致。"""
    text = " ".join((question or "").split())
    if not text:
        return "新的对话"
    for separator in ("？", "?", "。", ".", "！", "!", "\n"):
        index = text.find(separator)
        if 0 < index <= limit:
            return text[:index]
    return text if len(text) <= limit else f"{text[:limit]}…"
