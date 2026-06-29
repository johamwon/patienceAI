"""
Persona "小光" 与全局合规约束

集中定义患癌知光陪伴助手的人格、全局合规硬性约束，以及生成后兜底的
合规校验函数 `compliance_guard`。所有面向患者的生成环节（陪伴暖场白、
就医准备包、研究希望文案等）都应复用本模块，保证"诚实-希望张力"一致。

本模块无任何副作用、不依赖外部服务，可被后端 services 与 agents 安全独立导入。

关联需求：R1.1, R1.2, R1.4, R13.1, R13.2, R13.3
"""

import re

# ─── Persona 人格定义 ─────────────────────────────────────────────────────────

PERSONA_NAME = "小光"

PERSONA_PROMPT = """\
你是"小光"，患癌知光的陪伴助手。你的人格特征：
- 温柔：用平实、有温度的语言，像一个懂医学的朋友。
- 诚实：只说证据支持的话；不确定就说不确定；坏消息不掩盖、不美化。
- 不端着：不堆砌术语，不居高临下。
你不是医生，不做诊断，不开处方，不替代就医。"""

# ─── 全局合规约束 ─────────────────────────────────────────────────────────────
# 注入所有患者可见的生成提示词；冲突时不确定性优先。

COMPLIANCE_CONSTRAINTS = """\
硬性约束（违反即不合格）：
1. 不得给出诊断结论（如"你患了X""这就是癌症复发"）。
2. 不得给出处方、剂量、用药增减的个体化指令。
3. 不得把群体研究证据表述为对该患者个体的建议。
4. 当温暖表达与证据的不确定性冲突时，优先如实陈述不确定性与风险。
5. 早期/动物实验阶段研究不得表述为已确立的临床获益。"""


def with_persona(task_prompt: str, include_compliance: bool = True) -> str:
    """把人格与合规约束拼接到任务提示词前。

    Args:
        task_prompt: 具体任务的提示词。
        include_compliance: 是否注入全局合规约束，默认 True。
            仅在确实不面向患者的内部生成场景才设为 False。

    Returns:
        以 Persona（可选 + 合规约束）为前缀的完整提示词。
    """
    parts = [PERSONA_PROMPT]
    if include_compliance:
        parts.append(COMPLIANCE_CONSTRAINTS)
    if task_prompt:
        parts.append(task_prompt)
    return "\n\n".join(parts)


# ─── 合规校验（生成后兜底，R13.1/13.2/13.3） ──────────────────────────────────
# 仅针对直接面向"你"的个体化诊断/处方指令；不误伤正常的群体医学陈述
# （如"研究显示该药物可降低死亡风险"）。

#: 中性替换文案，命中违规时用于安全替换，保证替换后文本通顺。
_SAFE_REPLACEMENT = "（此处涉及个体化诊疗，请咨询医生）"

#: 诊断/处方类禁用正则模式列表。
#: 每条只匹配面向个体（"你"）的诊断结论或具体处方/剂量指令。
DIAGNOSIS_PATTERNS = [
    r"你(患|得)了",
    r"确诊为",
    r"建议你服用",
    r"每[日天][^。！？\n]*?(mg|毫克|片|粒|克|g)",
]

# 预编译以提升稳健性与性能。
_COMPILED_PATTERNS = [(p, re.compile(p)) for p in DIAGNOSIS_PATTERNS]

# 句子切分：保留中文/英文常见句末标点作为边界。
_SENTENCE_SPLIT = re.compile(r"([。！？!?\n])")


def _split_sentences(text: str):
    """把文本按句末标点切成 (句子, 末尾标点) 片段列表，保留原始标点与空白。"""
    parts = _SENTENCE_SPLIT.split(text)
    segments = []
    for i in range(0, len(parts), 2):
        body = parts[i]
        delimiter = parts[i + 1] if i + 1 < len(parts) else ""
        if body == "" and delimiter == "":
            continue
        segments.append((body, delimiter))
    return segments


def compliance_guard(text: str) -> tuple[str, list[str]]:
    """生成后合规兜底校验。

    扫描文本中每个句子，若命中诊断/处方类禁用模式，则把整句替换为中性提示，
    并记录命中的模式。对正常的群体医学陈述不做处理（不误伤）。

    Args:
        text: 待校验文本。

    Returns:
        (清洗后文本, 命中的违规模式列表)。未命中时返回原文与空列表。
    """
    if not text:
        return text, []

    violations: list[str] = []
    cleaned_parts: list[str] = []

    for body, delimiter in _split_sentences(text):
        matched_pattern = None
        for pattern_src, compiled in _COMPILED_PATTERNS:
            if compiled.search(body):
                matched_pattern = pattern_src
                break

        if matched_pattern is not None:
            violations.append(matched_pattern)
            # 保留句子的前导空白，让替换后文本与上下文衔接通顺。
            leading_ws = body[: len(body) - len(body.lstrip())]
            cleaned_parts.append(f"{leading_ws}{_SAFE_REPLACEMENT}{delimiter}")
        else:
            cleaned_parts.append(f"{body}{delimiter}")

    return "".join(cleaned_parts), violations
