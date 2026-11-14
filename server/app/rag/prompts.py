"""Prompt 模板：两种作答模式的系统提示与上下文拼装。

设计要点（对应需求：知识库没检索到时，让模型自己生成并明确标注）：

  模式一「知识库依据」——检索命中资料时
      强约束只依据资料、标注引用编号 [1][2]、资料不足就说明，抑制幻觉。

  模式二「模型自身知识」——检索未命中且允许回退时
      放开约束让模型正常作答，但必须在正文前插入醒目标注，
      说明该回答**不是**来自知识库，并引导用户上传相关文档。
      这样既解决了「查不到就答不了」的体验问题，又不会让用户误以为
      答案是文档里写的内容。

两种模式共用同一套历史多轮记忆。
"""

from __future__ import annotations

from app.services.vectorstore import RetrievedChunk

# --------------------------------------------------------------------------
# 模式一：有知识库依据
# --------------------------------------------------------------------------
GROUNDED_SYSTEM_PROMPT = """你是一个严谨的企业知识库问答助手。请遵守以下规则：

1. **只依据「参考资料」回答**，不要使用你自身的记忆补充事实。
2. 资料中没有依据时，明确说明「知识库中未找到相关依据」，不要编造内容，也不要猜测。
3. 引用资料时在句末标注对应编号，例如 [1]、[2]，编号必须与参考资料一致。
4. 使用 Markdown 组织答案：结论先行，需要分点时用有序或无序列表，
   涉及步骤、参数、对比时使用表格，涉及代码时使用围栏代码块。
5. 保持简洁准确，不要重复问题本身，不要输出与问题无关的内容。
6. 涉及多篇论文时，先分别说明各篇怎么说，再给综合结论；
   不要只依据其中一篇就代替全部，也不要把某篇没提到的内容说成它支持。
"""

# --------------------------------------------------------------------------
# 模式二：无知识库依据，改用模型自身知识
# --------------------------------------------------------------------------
FALLBACK_SYSTEM_PROMPT = """你是一个乐于助人的 AI 助手。用户的问题在企业知识库中没有检索到相关资料，
因此本次允许你使用**自身的通用知识**来回答。

请遵守以下规则：

1. 正常、完整地回答问题 —— 不要因为缺少资料就拒绝作答或只说"我不知道"。
2. 回答要具体、有条理，可使用 Markdown 列表、表格与代码块。
3. **不要编造**具体的企业内部信息（如内部编号、内部流程、人名、金额），
   这类内容必须来自知识库，缺失时应明确说明需要查阅内部资料。
4. 不要输出"根据参考资料""引用来源"之类的话 —— 本次回答没有知识库依据。
5. 保持简洁准确，不要重复问题本身。
"""

# 无依据回退时，插在正文开头的标注（服务端直接下发，不依赖模型自觉）
FALLBACK_BANNER = (
    "> ⚠️ **知识库中未检索到相关依据**，以下回答由模型基于通用知识生成，"
    "**并非来自你上传的文档**，请自行核实准确性。\n"
    "> 如需基于内部资料的准确回答，请在下方「知识库管理」中上传相关文档后重新提问。\n\n"
)

# 「检索到了片段，但都不够相关」时的标注。
# 不与上面那条混用：用户看到「未检索到」会以为向量库坏了/没索引，
# 而实际是**召回了但被相关性门槛过滤**。这两件事的排查动作完全不同，必须说清。
FALLBACK_BANNER_WEAK = (
    "> ⚠️ **知识库中检索到 {retrieved} 条片段，但相关度都不足**"
    "（最高相似度 {top_score:.2f}；判定门槛：词面命中 ≥ {lex} 或相似度 ≥ {strong}）。\n"
    "> 以下回答由模型基于通用知识生成，**并非来自你上传的文档**，请自行核实准确性。\n"
    "> 若确认文档里确有这部分内容，可换更具体的问法（带上原文里的术语），"
    "或到「知识库管理」确认这些文档状态为「已就绪」且「参与检索」已打开。\n\n"
)

# 关闭回退（RAG_FALLBACK_TO_MODEL=false）时的纯提示文案
NO_CONTEXT_ANSWER = (
    "知识库中没有检索到与该问题相关的依据。\n\n"
    "建议：\n"
    "- 确认已在输入框上方勾选包含相关文档的知识库；\n"
    "- 若文档尚未上传，请先到「知识库管理」上传并等待解析完成（状态为「已就绪」）；\n"
    "- 也可以换一种更具体的问法，或调大检索数量 Top-K 后重试。"
)

# 供前端展示的「引导补充文档」提示（与 FALLBACK_BANNER 末尾一致）
FALLBACK_HINT = "知识库中未收录该内容，建议上传相关文档以获得有依据的回答。"


# 「无依据」标注的统一前缀。两条 banner 都以它开头，剥除时按前缀识别。
_BANNER_PREFIX = "> ⚠️ **知识库中"


def strip_leading_banner(text: str) -> str:
    """去掉正文开头的「无依据」标注。

    为什么需要：标注是**服务端**加在回答正文里的，会被存进数据库。
    下一轮提问时这段历史会作为对话记忆喂给模型，模型看到上一轮是这么开头的，
    就跟着复读一遍 —— 结果是「同一条回答里出现两次一模一样的标注」。
    实测：连续两次无依据提问后，第二次的正文变成 `标注 + 标注 + 模型回答`。

    只在**开头**剥除（且必须真的以标注前缀开头），不会误删正文中间的引用块。
    """
    if not text:
        return text
    stripped = text.lstrip()
    if not stripped.startswith(_BANNER_PREFIX):
        return text

    lines = stripped.split("\n")
    index = 0
    while index < len(lines) and (lines[index].startswith(">") or not lines[index].strip()):
        index += 1
    return "\n".join(lines[index:]).lstrip("\n")


def build_context(chunks: list[RetrievedChunk], snippet_limit: int = 600) -> str:
    """把检索结果拼成带编号的参考资料块。"""
    if not chunks:
        return ""

    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.content.strip()
        if len(text) > snippet_limit:
            text = f"{text[:snippet_limit]}…"
        # 定位信息尽量具体：页码 + 章节（章节由解析阶段识别，可能为空）
        parts = [f"第 {chunk.page} 页" if chunk.page else f"第 {chunk.ordinal + 1} 段"]
        if chunk.section:
            parts.append(chunk.section)
        location = " · ".join(parts)
        blocks.append(
            f"[{index}]（来源：{chunk.document_name} · {location} · 相关度 {chunk.score:.2f}）\n{text}"
        )
    return "\n\n".join(blocks)


# 多篇论文同时作答时的额外要求。
# 为什么必须显式约束：模型默认会挑「最相关的那一篇」作答，
# 用户选了 5 篇却只拿到 1 篇的内容，还以为其余 4 篇都说了一样的话。
MULTI_PAPER_RULES = """本次问题涉及以下 {count} 篇论文：
{documents}

作答要求（多篇论文场景）：
1. 凡是能从多篇论文得到信息的问题，**先分别说明各篇的说法**，再给出综合结论；
2. 各篇结论不一致时，明确指出差异，并分别标注依据编号；
3. 若某篇论文在参考资料中没有相关内容，直接写「《论文名》未提及」，
   **不要**用其他论文的内容替它作答，也不要假装它支持某个观点；
4. 跨论文的关联（继承、改进、互相矛盾）要明确指出，例如「A 解决了 B 的检索效率问题」。
"""


def build_user_prompt(
    question: str,
    chunks: list[RetrievedChunk],
    document_names: list[str] | None = None,
) -> str:
    context = build_context(chunks)
    names = [name for name in dict.fromkeys(document_names or []) if name]
    multi = ""
    if len(names) >= 2:
        multi = MULTI_PAPER_RULES.format(
            count=len(names),
            documents="\n".join(f"- {name}" for name in names),
        ) + "\n"

    if not context:
        return f"{multi}用户问题：{question}"

    return (
        f"{multi}参考资料：\n{context}\n\n"
        f"用户问题：{question}\n\n"
        "请依据上述参考资料作答，并在引用处标注对应编号。"
    )


def build_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[tuple[str, str]] | None = None,
    *,
    grounded: bool | None = None,
    document_names: list[str] | None = None,
) -> list[dict[str, str]]:
    """组装完整的 messages：system + 历史多轮 + 当前问题。

    grounded: True = 有知识库依据；False = 用模型自身知识；None = 按 chunks 自动判断。
    document_names: 本次问答涉及的论文名（≥2 篇时追加跨论文作答要求）。
    """
    if grounded is None:
        grounded = bool(chunks)

    system_prompt = GROUNDED_SYSTEM_PROMPT if grounded else FALLBACK_SYSTEM_PROMPT
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    for role, content in history or []:
        if role not in ("user", "assistant") or not content:
            continue
        # 历史中的助手回答不重复携带引用资料，避免上下文爆炸
        messages.append({"role": role, "content": content})

    messages.append(
        {"role": "user", "content": build_user_prompt(question, chunks, document_names)}
    )
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
