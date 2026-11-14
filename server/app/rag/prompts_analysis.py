"""单篇论文分析的提示词模板（M4）。

设计约束：
  - 每个分析维度只给模型「检索到的原文片段」，不给整篇全文（控制成本与漂移）；
  - 强制编号引用 [n]，系统在流结束后把 [n] 映射回页码/片段；
  - 找不到依据时必须写「原文未提及」，禁止编造。
"""

from __future__ import annotations

CITATION_RULES = """
你必须遵守以下规则：
1. 只能依据下方【原文片段】回答，不得引入片段之外的知识或常识补全；
2. 每条事实性结论后面必须标注来源编号，格式如 [1]、[2][3]，编号对应片段序号；
3. 原文没有覆盖的内容，直接写「原文未提及」，不要猜测或编造；
4. 用中文输出 Markdown，结构清晰；不要自行编造参考文献列表；
5. 输出模板示例（每个要点末尾都必须有 [n]，没有引用视为不合格）：
   - 要点一：…… [1]
   - 要点二：…… [2][3]
"""

ANALYSIS_SPECS: dict[str, dict] = {
    "summary": {
        "label": "论文速览",
        "query": "研究问题 方法 主要结果 结论 贡献 research problem method results conclusion",
        "sections": [],
        "instruction": (
            "用 200 字左右概括这篇论文：研究什么问题、采用什么方法、"
            "得到什么主要结果、结论是什么。分成 4 个小点，每点都要有引用。"
        ),
    },
    "background": {
        "label": "研究背景",
        "query": "研究背景 动机 现状 挑战 background motivation challenge",
        "sections": ["introduction", "related", "background"],
        "instruction": (
            "解释作者为什么开展这项研究：领域现状如何、已有工作有什么不足、"
            "本文的动机是什么。200-300 字。"
        ),
    },
    "question": {
        "label": "研究问题",
        "query": "研究问题 目标 假设 research question objective hypothesis",
        "sections": ["abstract", "introduction"],
        "instruction": (
            "明确列出论文试图解决的核心研究问题（1-3 条），"
            "并说明对应的研究目标或假设。"
        ),
    },
    "method": {
        "label": "研究方法",
        "query": "研究方法 模型 算法 框架 method model algorithm framework",
        "sections": ["method"],
        "instruction": (
            "说明论文使用的理论、模型、算法或技术方案，解释关键步骤与输入输出；"
            "如果公式较多，用文字说明其作用即可。300 字以内。"
        ),
    },
    "pipeline": {
        "label": "技术路线",
        "query": "技术路线 流程 步骤 框架 pipeline workflow framework",
        "sections": ["method", "experiment"],
        "instruction": (
            "按步骤梳理整体研究流程（数据准备 → 处理 → 建模 → 训练/推理 → 评估），"
            "用有序列表，每一步注明依据。"
        ),
    },
    "innovation": {
        "label": "创新点",
        "query": "创新 贡献 与已有工作的区别 novelty contribution",
        "sections": ["introduction", "related", "method", "conclusion"],
        "instruction": (
            "对比已有工作，总结 2-4 条创新点；每条都要说明「相对于什么」新在哪里，"
            "不要泛泛说“提出了新方法”。"
        ),
    },
    "results": {
        "label": "实验结果",
        "query": "实验结果 数据集 评价指标 性能 对比 results dataset metric baseline",
        "sections": ["experiment", "result"],
        "instruction": (
            "提取实验设置（数据集、指标、对比基线）与主要结果数字；"
            "有提升时说明提升幅度。原文没有具体数字就如实说明。"
        ),
    },
    "limitations": {
        "label": "局限性",
        "query": "局限 不足 未来工作 限制 limitation drawback future work",
        "sections": ["discussion", "conclusion"],
        "instruction": (
            "分析论文的局限：数据规模、方法假设、实验覆盖、可复现性等。"
            "明确区分「作者承认的局限」与「从原文推断的局限」。"
        ),
    },
    "glossary": {
        "label": "关键术语",
        "query": "术语 定义 概念 缩写 definition terminology",
        "sections": [],
        "instruction": (
            "挑出 4-8 个理解本文必须掌握的关键术语/概念，"
            "按「术语：在本文语境下的含义」逐条解释，不要写通用词典定义。"
        ),
    },
}


def build_analysis_messages(
    kind: str, *, title: str, evidence_text: str
) -> list[dict[str, str]]:
    spec = ANALYSIS_SPECS[kind]
    system = "你是一名严谨的学术论文分析助手。" + CITATION_RULES
    user = (
        f"论文标题：{title}\n\n"
        f"【原文片段】\n{evidence_text}\n\n"
        f"任务：{spec['instruction']}\n"
        f"输出语言：中文。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_ask_messages(
    question: str, *, title: str, evidence_text: str, section_label: str = ""
) -> list[dict[str, str]]:
    system = "你是一名严谨的论文阅读助手。" + CITATION_RULES
    scope = f"（限定章节：{section_label}）" if section_label else ""
    user = (
        f"论文标题：{title}\n\n"
        f"【原文片段】{scope}\n{evidence_text}\n\n"
        f"问题：{question}\n"
        "要求：先直接回答，再列出依据编号；没有依据就说「原文未提及」。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
