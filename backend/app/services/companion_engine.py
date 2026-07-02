"""
陪伴引擎（Companion_Engine）

负责生成回答开头的暖场白（Companion_Message）：注入统一人格"小光"与全局
合规约束，根据情绪状态选择基调，无论何种情绪都先共情；证据含负面结论时先
共情再如实陈述并给可执行出口；high/prohibited 风险时强制包含就医引导；生成
后统一经 ``compliance_guard`` 清洗。LLM 调用失败时回退到按情绪预置的安全模板，
保证不阻塞主流程、不抛异常。

设计要点（对应需求）：
- R1.1/R1.3：注入 Persona 人格，保持语气一致（通过 with_persona 提示词前缀）。
- R1.4：人格表达与证据冲突时不弱化负面结论（提示词约束 + 不掩盖坏消息）。
- R3.1/R3.2：回答开头生成暖场白，按情绪选择基调。
- R3.3/R3.4：无论何种情绪都先共情；证据含负面结论时先共情→照实陈述→给出口，
  不用乐观语气掩盖坏消息（判断交给 LLM 提示词承担，代码侧靠 compliance_guard
  + 安全模板兜底）。
- R3.5/R13.1：暖场白不含诊断结论/处方/个体化治疗指令；生成后经 compliance_guard。
- R3.6：可陈述证据呈现的模式，但不作确诊结论（提示词约束）。
- R3.7/R13.5：risk_level in {high, prohibited} 时暖场白必含就医引导。
- R4.3：history 非空时作为上下文参考拼入提示词（让小光"记得"之前问过什么）。

本模块对 ``agents.prompts.persona`` 不可导入时提供安全兜底，保证后端可独立运行。
"""

import asyncio
from typing import Optional, Union

from ..models.schemas import EmotionState

try:
    from agents.prompts.persona import with_persona, compliance_guard
except Exception:  # pragma: no cover - 仅在 agents 包不可导入时的极端兜底
    def with_persona(task_prompt: str, include_compliance: bool = True) -> str:
        return task_prompt

    def compliance_guard(text: str):
        return text, []


# 风险等级达到此集合时，暖场白必须包含就医引导（R3.7/R13.5）。
_ESCALATED_RISK_LEVELS = {"high", "prohibited"}

# 就医引导兜底句：模板回退路径在 high/prohibited 时拼接（R3.7/R13.5）。
_SEEK_CARE_LINE = (
    "这件事建议尽快当面咨询你的主治医生，或前往正规医疗机构由专业医生评估，"
    "他们能结合你的具体情况给出最稳妥的判断。"
)


# ─── 预置安全模板（LLM 失败回退） ────────────────────────────────────────────
# 每个 EmotionState 一段中性共情话术；措辞温暖但不虚假、不含诊断/处方。
# high/prohibited 时由 _fallback_message 额外拼接就医引导。

_FALLBACK_TEMPLATES: dict[EmotionState, str] = {
    EmotionState.PANIC: (
        "我能感觉到你现在很害怕，这种慌乱的心情是很正常的。别急，我们一步一步来，"
        "我会把找到的信息尽量说清楚，陪你一起看。"
    ),
    EmotionState.ANXIETY: (
        "我理解你心里一直悬着、放不下，这份担心说明你很在意自己的健康。"
        "我们慢慢梳理，把能弄清楚的先弄清楚。"
    ),
    EmotionState.DESPAIR: (
        "听得出你现在很难熬，甚至有些撑不住的感觉，我很想陪在你身边。"
        "你愿意来了解，已经很不容易了，我们一点一点来看。"
    ),
    EmotionState.URGENT: (
        "我很担心你现在的状况，你的安全是最重要的。"
    ),
    EmotionState.CALM: (
        "谢谢你愿意把问题交给我，我们一起把这件事看明白。"
        "我会尽量把找到的信息讲得清楚一些。"
    ),
}

# 兜底默认模板（emotion 无法识别时使用）。
_DEFAULT_FALLBACK = _FALLBACK_TEMPLATES[EmotionState.CALM]


def _coerce_emotion(emotion: Union[EmotionState, str, None]) -> EmotionState:
    """把 EmotionState 或字符串统一规整为 EmotionState 枚举。

    无法识别时返回 ``EmotionState.CALM``（与全局默认情绪一致）。
    """
    if isinstance(emotion, EmotionState):
        return emotion
    if isinstance(emotion, str):
        value = emotion.strip().lower()
        for state in EmotionState:
            if state.value == value:
                return state
    return EmotionState.CALM


def _emotion_value(emotion: Union[EmotionState, str, None]) -> str:
    """取情绪的字符串值，兼容枚举/字符串/None。"""
    return _coerce_emotion(emotion).value


def _turn_field(turn, field: str) -> str:
    """从一轮历史记录中取字段，兼容 SessionTurn dataclass 与 dict。"""
    if isinstance(turn, dict):
        value = turn.get(field)
    else:
        value = getattr(turn, field, None)
    return str(value) if value is not None else ""


def _format_history(history) -> str:
    """把历史上下文格式化为提示词片段；空/无效时返回空字符串（R4.3）。"""
    if not history:
        return ""
    lines = []
    for turn in history:
        query = _turn_field(turn, "query").strip()
        if not query:
            continue
        emotion = _turn_field(turn, "emotion").strip()
        if emotion:
            lines.append(f"- 之前问过：{query}（当时情绪：{emotion}）")
        else:
            lines.append(f"- 之前问过：{query}")
    return "\n".join(lines)


def _summarize_evidences(evidences: Optional[list[dict]]) -> str:
    """把证据摘要为提示词片段，供 LLM 判断是否含负面/不利结论。"""
    if not evidences:
        return "（本次未检索到相关证据。）"
    parts = []
    for i, ev in enumerate(evidences[:5], 1):
        if not isinstance(ev, dict):
            continue
        title = str(ev.get("title", "") or "").strip()
        abstract = str(ev.get("abstract", "") or "").strip()
        snippet = abstract[:200]
        parts.append(f"[证据{i}] {title}\n{snippet}".strip())
    return "\n\n".join(parts) if parts else "（本次未检索到相关证据。）"


def _build_prompt(
    query: str,
    emotion: EmotionState,
    evidences: Optional[list[dict]],
    risk_level: str,
    risk_message: Optional[str],
    history,
) -> str:
    """构造暖场白生成的任务提示词（再经 with_persona 注入人格+合规约束）。"""
    escalated = (risk_level or "").lower() in _ESCALATED_RISK_LEVELS

    history_block = _format_history(history)
    history_section = (
        f"\n这位患者在本次会话中之前问过的内容（请自然地体现你记得，不要生硬复述）：\n{history_block}\n"
        if history_block
        else ""
    )

    evidence_section = _summarize_evidences(evidences)

    risk_section = ""
    if escalated:
        risk_section = (
            "\n【重要】本次查询风险等级较高，你必须在暖场白中明确引导患者尽快咨询主治医生"
            "或前往正规医疗机构就医，这一点不可省略、不可被安抚话语替代。"
        )
        if risk_message:
            risk_section += f"\n（风险提示参考：{risk_message}）"

    task_prompt = f"""\
请你以"小光"的身份，为下面这位患者的提问写一段简短的暖场白（开头的陪伴话语），用于回答正文之前。

患者的提问：{query}
我识别到患者当前的情绪状态是：{emotion.value}
{history_section}
检索到的证据摘要：
{evidence_section}
{risk_section}

写作要求：
1. 无论患者是什么情绪，都先表达共情、让对方感到被理解，再进入信息。
2. 根据上面的情绪状态选择合适的基调（恐慌→稳住安抚；焦虑→安定陪伴；绝望→温柔托住；急症→关切并强调安全；平静→平和同行）。
3. 如果证据中包含负面或不利的结论（如治疗无效、病情进展等），不要回避、不要用乐观语气掩盖；先共情，再如实、平实地点到这一点，并给出一个可执行的下一步出口（例如建议和医生沟通哪个方向）。
4. 绝对不要给出诊断结论、处方、剂量或个体化治疗指令；可以陈述证据呈现的模式，但不要说成是对这位患者的确诊。
5. 语言温柔、平实、不堆术语，控制在 2-4 句话以内。

只输出暖场白本身，不要输出任何解释、标题或引号。"""

    return with_persona(task_prompt)


def _fallback_message(emotion: EmotionState, risk_level: str) -> str:
    """LLM 失败时的安全模板回退（R3.7：high/prohibited 拼接就医引导）。"""
    base = _FALLBACK_TEMPLATES.get(emotion, _DEFAULT_FALLBACK)
    escalated = (risk_level or "").lower() in _ESCALATED_RISK_LEVELS
    # URGENT 情绪本身已偏向急症，但仅在风险升级时才强制拼接显式就医引导，
    # 以保证 R3.7/R13.5；URGENT 模板较短，拼接后语义自然。
    if escalated:
        return f"{base}{_SEEK_CARE_LINE}"
    return base


def _looks_like_prompt_leak(text: str) -> bool:
    """Detect model reasoning/prompt leakage instead of final companion copy."""
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    markers = [
        "用户现在需要",
        "写作要求",
        "只输出",
        "prompt",
        "患者的提问：",
        "检索到的证据摘要：",
        "是否符合",
        "llm_api_key",
        "[模拟响应]",
    ]
    return any(marker in lowered for marker in markers)


async def generate_companion_message(
    query: str,
    emotion: Union[EmotionState, str, None],
    evidences: Optional[list[dict]],
    risk_level: str,
    risk_message: Optional[str],
    history,
    llm_client,
) -> str:
    """生成面向患者的暖场白（Companion_Message）。

    Args:
        query: 患者本次查询文本。
        emotion: 识别到的情绪状态，兼容 ``EmotionState`` 枚举或字符串。
        evidences: 检索到的证据列表（list[dict]），可为空。
        risk_level: 现有四级风险等级字符串（low/medium/high/prohibited）。
        risk_message: 风险提示文案，可为 None。
        history: 最近 N 轮会话上下文，元素兼容 ``SessionTurn`` dataclass 或 dict。
        llm_client: 提供同步 ``chat(messages, ...)`` 接口的 LLM 客户端，可为 None。

    Returns:
        清洗后的暖场白文本。任何异常或 LLM 不可用都会回退到安全模板，
        保证不抛异常、不阻塞主流程。
    """
    normalized_emotion = _coerce_emotion(emotion)
    safe_risk_level = risk_level or "low"

    # LLM 不可用 → 直接走安全模板回退。
    if llm_client is None:
        return _fallback_message(normalized_emotion, safe_risk_level)

    try:
        prompt = _build_prompt(
            query=query or "",
            emotion=normalized_emotion,
            evidences=evidences,
            risk_level=safe_risk_level,
            risk_message=risk_message,
            history=history,
        )
        messages = [{"role": "user", "content": prompt}]
        # 同步 chat 用 asyncio.to_thread 包裹，避免阻塞事件循环
        # （沿用 simplification_loop 的模式）。
        raw = await asyncio.to_thread(
            llm_client.chat, messages, temperature=0.5, max_tokens=400
        )
    except Exception:
        # LLM 调用失败 → 回退安全模板，不抛异常（R3 降级永不阻塞主流程）。
        return _fallback_message(normalized_emotion, safe_risk_level)

    if not raw or not isinstance(raw, str) or not raw.strip():
        return _fallback_message(normalized_emotion, safe_risk_level)

    message = raw.strip()
    if _looks_like_prompt_leak(message):
        return _fallback_message(normalized_emotion, safe_risk_level)

    # 生成后统一经合规闸清洗（R3.5/R13.1）。
    cleaned, _violations = compliance_guard(message)
    cleaned = (cleaned or "").strip()
    if not cleaned:
        return _fallback_message(normalized_emotion, safe_risk_level)

    # R3.7/R13.5 兜底：风险升级但 LLM 未包含就医引导时，强制补上。
    escalated = safe_risk_level.lower() in _ESCALATED_RISK_LEVELS
    if escalated and not _mentions_seek_care(cleaned):
        cleaned = f"{cleaned}{_SEEK_CARE_LINE}"

    return cleaned


def _mentions_seek_care(text: str) -> bool:
    """粗略判断暖场白是否已包含就医/咨询医生引导（R3.7 兜底用）。"""
    keywords = ["就医", "医生", "医院", "医疗机构", "就诊", "门诊", "急诊"]
    return any(kw in text for kw in keywords)
