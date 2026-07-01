"""
情绪感知层（Emotion_Detector）

识别患者查询中的情绪信号，采用"规则匹配 + LLM 判定"混合策略，输出统一的
``EmotionState`` 枚举值（复用 ``backend/app/models/schemas.py`` 中的定义）。

混合策略（detect_emotion）：
1. 高危情绪（URGENT、DESPAIR）规则先行命中，保证不漏（R2.4 急症联动靠 URGENT）。
2. 其余情况若 ``llm_client`` 可用，调用 LLM 精判（with_persona 注入、temperature=0，
   要求仅输出五个枚举值之一），稳健解析后映射到 ``EmotionState``。
3. LLM 不可用或调用/解析失败 → 回退规则匹配结果（R2.3）。
4. 全不命中 → 返回 ``EmotionState.CALM``（R2.6）。

本函数为同步函数：``llm_client.chat`` 是同步接口；如需在 async 上下文中使用，
由调用方自行处理（例如 ``run_in_executor``）。

关联需求：R2.1, R2.2, R2.3, R2.6
"""

from typing import Optional

from ..models.schemas import EmotionState

try:
    from agents.prompts.persona import with_persona
except Exception:  # pragma: no cover - 仅在 agents 包不可导入时的极端兜底
    def with_persona(task_prompt: str, include_compliance: bool = True) -> str:
        return task_prompt


# ─── 规则词表（粗筛） ─────────────────────────────────────────────────────────
# 与 design.md 第 2 节保持一致。匹配时对 query.lower() 做包含判断。

EMOTION_KEYWORDS: dict[EmotionState, list[str]] = {
    EmotionState.URGENT: ["快死了", "喘不过气", "大出血", "晕倒", "救命", "急"],
    EmotionState.PANIC: ["好怕", "吓死", "怎么办啊", "崩溃", "扛不住"],
    EmotionState.DESPAIR: ["没救了", "不想活", "放弃", "绝望", "等死"],
    EmotionState.ANXIETY: ["担心", "焦虑", "睡不着", "是不是很严重", "会不会"],
}

# 高危情绪：规则先行命中，保证不漏（R2.4 急症联动靠 URGENT）。
# 顺序即优先级：URGENT 优先于 DESPAIR。
_HIGH_RISK_EMOTIONS: list[EmotionState] = [EmotionState.URGENT, EmotionState.DESPAIR]

# 规则匹配的整体检查顺序（高危优先，其余次之）。
_RULE_CHECK_ORDER: list[EmotionState] = [
    EmotionState.URGENT,
    EmotionState.DESPAIR,
    EmotionState.PANIC,
    EmotionState.ANXIETY,
]

# LLM 提示词：要求仅输出五个枚举值之一。
_EMOTION_TASK_PROMPT = """\
请判断下面这条患者查询所流露的情绪状态，并从以下五个英文枚举值中**仅输出一个**，
不要输出任何解释、标点或其他文字：
- panic（恐慌：极度害怕、不知所措）
- anxiety（焦虑：担忧、紧张、反复纠结）
- despair（绝望：放弃、觉得没救了、不想活）
- urgent（急症倾向：身体出现危急症状，可能需要立即就医）
- calm（平静求知：情绪平稳，只是想了解信息）

患者查询：{query}

只输出 panic / anxiety / despair / urgent / calm 之一："""


def _match_by_rules(query_lower: str) -> Optional[EmotionState]:
    """按高危优先的顺序做规则匹配，命中返回对应情绪，全不命中返回 None。"""
    for emotion in _RULE_CHECK_ORDER:
        keywords = EMOTION_KEYWORDS.get(emotion, [])
        if any(kw in query_lower for kw in keywords):
            return emotion
    return None


def _parse_llm_emotion(text: Optional[str]) -> Optional[EmotionState]:
    """稳健解析 LLM 返回文本，映射到 EmotionState；无法识别返回 None。

    LLM 输出可能含多余内容，这里在文本中查找五个枚举 value 关键词；
    若出现多个，按高危优先（urgent > despair > panic > anxiety > calm）取其一。
    """
    if not text or not isinstance(text, str):
        return None

    lowered = text.lower()

    # 解析优先级：高危情绪优先，避免被次要词覆盖。
    parse_order = [
        EmotionState.URGENT,
        EmotionState.DESPAIR,
        EmotionState.PANIC,
        EmotionState.ANXIETY,
        EmotionState.CALM,
    ]
    for emotion in parse_order:
        if emotion.value in lowered:
            return emotion
    return None


def detect_emotion(query: str, llm_client=None) -> EmotionState:
    """检测查询的情绪状态。

    Args:
        query: 患者自然语言查询。空/None 输入安全返回 ``EmotionState.CALM``。
        llm_client: 可选的 LLM 客户端（需提供同步 ``chat(messages, ...)`` 接口）。
            为 ``None`` 时走纯规则路径，便于单元测试与降级（R2.3）。

    Returns:
        识别到的 ``EmotionState``；全不命中且无 LLM 结果时为 ``EmotionState.CALM``（R2.6）。
    """
    # 空/None 输入安全返回 CALM，不抛异常。
    if not query or not isinstance(query, str):
        return EmotionState.CALM

    query_lower = query.lower()
    rule_result = _match_by_rules(query_lower)

    # 1. 高危情绪（URGENT、DESPAIR）规则先行命中，保证不漏（R2.4）。
    if rule_result in _HIGH_RISK_EMOTIONS:
        return rule_result

    # 2. 其余情况若 llm_client 可用，调用 LLM 精判。
    if llm_client is not None:
        try:
            prompt = with_persona(_EMOTION_TASK_PROMPT.format(query=query))
            messages = [{"role": "user", "content": prompt}]
            raw = llm_client.chat(messages, temperature=0.0, max_tokens=16)
            llm_result = _parse_llm_emotion(raw)
            if llm_result is not None:
                return llm_result
            # LLM 返回无法识别 → 回退规则结果（R2.3）。
        except Exception:
            # 3. LLM 调用失败 → 回退规则结果（R2.3）。
            pass

    # 3/4. 回退规则结果；全不命中 → CALM（R2.6）。
    if rule_result is not None:
        return rule_result
    return EmotionState.CALM
