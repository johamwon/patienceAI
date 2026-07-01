"""
就医准备包生成器（Visit Prep Generator）

基于患者查询、检索证据与情绪状态，生成结构化的"医患沟通清单"——
即 VisitPrepPack 四类条目：
  - questions_for_doctor        该问医生的关键问题
  - info_to_tell_doctor         该主动告知医生的信息点
  - tests_to_request            该索取的检查或化验项
  - treatment_options_to_confirm 该确认的治疗方案选项

设计要点（关联需求 R6.1/6.2/6.4, R7.2/7.5/7.6, R13.1）：
- 注入 Persona 人格 + 全局合规约束（`with_persona`）从源头约束模型。
- 有证据：基于证据生成针对性问题（R7.2）。
- 无证据：生成通用就医准备问题（R7.5）。
- 每条文本经 `compliance_guard` 兜底清洗，剥离诊断/剂量（R6.4/R13.1）。
- LLM 调用同步、用 `asyncio.to_thread` 包裹（与 simplification_loop 一致）。
- JSON 解析失败时回退到通用模板；仅当 LLM 调用抛异常或连模板都无法产出时，
  才向上抛异常，供路由层转 5xx（R7.6）。

本模块仅依赖标准库与同包的 prompts.persona，可被独立导入。
emotion 参数按"字符串/枚举值"处理，不依赖尚未实现的 emotion_detector。
"""

import asyncio
import json
import re
from typing import Optional

from ..prompts.persona import with_persona, compliance_guard


# 四类条目的字段名（与 VisitPrepPack 结构对齐）
_PACK_FIELDS = (
    "questions_for_doctor",
    "info_to_tell_doctor",
    "tests_to_request",
    "treatment_options_to_confirm",
)

#: VisitPrepPack 默认定位说明文案（R6.3，作为常量字段，不依赖模型生成）
DEFAULT_POSITIONING_NOTE = "本清单用于辅助你和医生沟通，最终诊疗以医生判断为准。"

#: 单类条目最多保留数量，避免清单过长
_MAX_ITEMS_PER_CATEGORY = 6


def _normalize_emotion(emotion) -> str:
    """把 emotion 归一化为字符串值。

    兼容枚举（取 .value）、字符串、None 等多种输入，
    不 import 尚未实现的 emotion_detector 模块。
    """
    if emotion is None:
        return "calm"
    value = getattr(emotion, "value", emotion)
    return str(value)


#: 常见非疾病修饰词，用于从 query 中粗提取疾病/主题（去掉这些噪声词后保留主体）。
_TOPIC_NOISE_WORDS = (
    # 提问 / 语气 / 虚词
    "最新", "进展", "研究", "治疗", "疗法", "怎么办", "怎么样", "如何", "是什么",
    "有哪些", "哪个", "哪种", "更好", "区别", "副作用", "效果", "方案", "用药",
    "能不能", "可以吗", "吗", "呢", "啊", "的", "了", "和", "与", "或",
    "请问", "想了解", "了解", "咨询", "问题", "情况",
    # 人称 / 关系词
    "我", "你", "您", "他", "她", "朋友", "父亲", "母亲", "爸爸", "妈妈", "爸", "妈",
    "家人", "家属", "孩子", "儿子", "女儿", "老公", "老婆", "丈夫", "妻子",
    "爷爷", "奶奶", "外公", "外婆", "亲戚", "同事", "邻居",
    # 患病 / 动作类动词
    "得了", "得", "患了", "患", "有", "长了", "长", "查出", "确诊", "诊断",
    "最近", "突然", "现在", "目前",
)

#: 人称/关系残留词：去噪后若片段仍含这些，视为提取失败（避免"朋友父亲得"这类垃圾主题）。
_TOPIC_RESIDUAL_MARKERS = (
    "我", "你", "您", "他", "她", "朋友", "父亲", "母亲", "爸", "妈",
    "家人", "家属", "孩子", "儿子", "女儿", "老公", "老婆", "丈夫", "妻子",
    "爷爷", "奶奶", "外公", "外婆", "亲戚", "同事", "邻居",
    "得", "患", "查出", "确诊", "诊断",
)


def _extract_disease_topic(query: str) -> str:
    """从患者 query 中粗略提取疾病/主题词，用于无证据时定制条目。

    采用轻量启发式（不依赖外部 NLP）：去除常见的提问修饰词、人称/关系词与标点，
    保留疾病/药物等主体片段。

    去噪后做合理性校验：若剩余片段仍含明显的人称/关系/动词残留，或长度异常、
    不像疾病名，则返回空字符串——宁可让调用方走完全通用模板，也不塞一个错误主题。
    """
    if not query:
        return ""
    topic = query.strip()
    # 去除标点与空白
    topic = re.sub(r"[，。、？！,.\?!；;：:\s]+", " ", topic).strip()
    # 逐个剔除噪声修饰词（按长度降序，先剔长词避免子串残留，如先去"父亲"再去"父"）
    for word in sorted(_TOPIC_NOISE_WORDS, key=len, reverse=True):
        topic = topic.replace(word, " ")
    # 合并多余空格，取最长的主体片段（通常是疾病/药物名）
    fragments = [f for f in topic.split() if f]
    if not fragments:
        return ""
    topic = max(fragments, key=len)

    # ── 合理性校验 ────────────────────────────────────────────────
    # 1) 过短（如单字残留）视为无效
    if len(topic) < 2:
        return ""
    # 2) 过长，不像一个疾病/药物名（多半是没切干净的句子片段）
    if len(topic) > 20:
        return ""
    # 3) 仍含人称/关系/患病动词残留 → 判定为垃圾片段，返回空
    if any(marker in topic for marker in _TOPIC_RESIDUAL_MARKERS):
        return ""
    return topic


def _build_evidence_digest(evidences: list[dict], top_k: int = 5) -> str:
    """把证据列表压缩成一段供 LLM 参考的摘要文本。"""
    parts = []
    for i, ev in enumerate(evidences[:top_k], 1):
        title = (ev.get("title") or "").strip()
        abstract = (ev.get("abstract") or "").strip()
        source = ev.get("source_type", "unknown")
        parts.append(
            f"[证据 {i}] 来源类型: {source}\n"
            f"标题: {title}\n"
            f"摘要: {abstract[:400]}\n"
        )
    return "\n".join(parts)


def _build_prompt(query: str, evidence_digest: str, emotion: str, has_evidence: bool) -> str:
    """构造注入人格+合规约束的任务提示词。"""
    disease_topic = _extract_disease_topic(query)
    topic_hint = (
        f"本次查询的核心疾病/主题是「{disease_topic}」。" if disease_topic else ""
    )

    if has_evidence:
        context_block = f"""\
以下是检索到的与患者查询相关的医学证据摘要，请基于这些证据生成针对性的就医准备条目：

{evidence_digest}"""
        evidence_rule = (
            f"{topic_hint}\n"
            "请把每一条都牢牢锚定到上述具体疾病/主题与证据要点上："
            "引用证据中提到的治疗方向、药物类别、检查项目、疗效或风险等具体信息，"
            "生成只对「这次查询」成立的、个性化的沟通条目。"
            "严禁出现「我的情况严重吗」「有什么需要注意的」这类放之四海皆准的泛泛问题。"
        )
    else:
        context_block = "（本次未检索到相关医学证据。）"
        evidence_rule = (
            f"{topic_hint}\n"
            "虽然没有检索到针对性证据，但请紧扣上述疾病/主题本身的常见诊疗维度"
            "（如该病的主流治疗选择、典型检查、起效与复诊节奏、常见副作用与随访要点）"
            "生成具体、有指向性的就医准备条目，避免完全通用、与主题无关的空泛模板。"
        )

    example_block = _build_topic_example(disease_topic)

    task = f"""\
你的任务：为患者生成一份"就医准备包"，帮助他/她在见医生时知道该问什么、该说什么、该查什么、该确认什么。

患者查询：{query}
患者当前情绪倾向（仅用于微调语气，不改变内容）：{emotion}

{context_block}

{evidence_rule}
{example_block}

请生成以下四类条目，每类是若干条独立的文本项（每类 3-5 条）：
1. questions_for_doctor：该问医生的关键问题（必须是问句形式）。
2. info_to_tell_doctor：该主动告知医生的信息点（如症状、既往史、用药史等沟通要点）。
3. tests_to_request：该向医生了解或索取的检查/化验项（以"可以问医生是否需要做……"的沟通口吻）。
4. treatment_options_to_confirm：该与医生确认的治疗方案方向（以"需要和医生确认……"的沟通口吻）。

硬性要求：
- 每一条都必须紧扣本次查询的具体疾病/主题，能体现出"这是为这个病/这个问题量身准备的"，不能是任何疾病都适用的通用问题。
- 每一条都必须是"问句"或"与医生沟通的要点"形式，绝不能是诊断结论或处方剂量。
- 不得出现"你患了X""确诊为X"等诊断结论。
- 不得出现具体药物剂量、用药增减指令（如"每天吃X毫克"）。
- 语言平实、口语化，便于患者直接拿去和医生沟通。

只输出 JSON，不要任何额外文字，格式如下：
{{
  "questions_for_doctor": ["...", "..."],
  "info_to_tell_doctor": ["...", "..."],
  "tests_to_request": ["...", "..."],
  "treatment_options_to_confirm": ["...", "..."]
}}"""

    return with_persona(task)


def _build_topic_example(disease_topic: str) -> str:
    """给出一个具体 vs 泛泛的示例，引导模型产出锚定主题的条目。"""
    topic = disease_topic or "该疾病"
    return (
        "示例（仅示意「具体、有针对性」的风格，请结合本次主题改写，不要照抄）：\n"
        f"- 好的提问：针对「{topic}」，我适合药物治疗还是其他治疗方式？这类药物通常多久起效？复诊频率应该怎样安排？\n"
        "- 不好的提问：我的情况严重吗？我需要注意什么？（过于笼统，禁止这样写）"
    )


def _parse_pack_json(raw: str) -> Optional[dict]:
    """从 LLM 输出中解析四类条目 JSON，带提取回退。

    返回包含四类列表的 dict；解析失败返回 None。
    """
    if not raw:
        return None

    candidates = []
    # 1) 直接解析
    candidates.append(raw)
    # 2) 提取第一个 {...} 块
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        candidates.append(match.group())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and any(field in data for field in _PACK_FIELDS):
            return data
    return None


def _coerce_items(value) -> list[str]:
    """把任意 JSON 值规整为字符串条目列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    items = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            items.append(text)
    return items


def _generic_pack(query: str) -> dict:
    """无证据 / JSON 解析失败时的就医准备包模板（R7.5）。

    优先根据 query 主题定制条目；提取不到明确主题时退回完全通用的稳妥模板。
    """
    topic = _extract_disease_topic(query)
    if topic:
        return {
            "questions_for_doctor": [
                f"针对「{topic}」，目前主流的治疗方向有哪些？我比较适合哪一种？",
                f"针对「{topic}」，不同治疗方式的预期效果、起效时间和可能的副作用分别是什么？",
                f"我的「{topic}」目前大概处于什么阶段？接下来一段时间可能会怎样变化？",
                f"针对「{topic}」，复查和随访应该多久一次、需要重点关注哪些指标？",
                f"如果暂时观察等待，「{topic}」出现哪些信号时我需要尽快复诊？",
            ],
            "info_to_tell_doctor": [
                f"我和「{topic}」相关的主要症状、出现时间以及变化趋势。",
                "我过去的疾病史、手术史以及家族相关病史。",
                "我正在使用的所有药物、保健品和过敏史。",
                "我最近的生活状态变化，比如睡眠、食欲、体重和情绪。",
            ],
            "tests_to_request": [
                f"可以问医生：针对「{topic}」，是否需要做进一步检查来明确诊断或分期？",
                f"可以问医生：评估「{topic}」通常需要哪些检查或化验，现有结果是否已经足够？",
                "可以问医生：这些检查的目的、过程和注意事项分别是什么？",
            ],
            "treatment_options_to_confirm": [
                f"需要和医生确认：针对「{topic}」现在是否需要立即开始治疗，还是可以先观察？",
                f"需要和医生确认：针对「{topic}」不同治疗方向的利弊，以及哪种更适合我的整体情况。",
                "需要和医生确认：后续的复查与随访计划如何安排。",
            ],
        }

    return {
        "questions_for_doctor": [
            "我目前的情况，最需要优先关注和处理的是什么？",
            "针对我的情况，目前有哪些可选的检查或治疗方向？",
            "这些方案各自的预期效果、可能的风险和副作用分别是什么？",
            "我的情况大概处于什么阶段？接下来一段时间可能会有什么变化？",
            "如果选择观察等待，需要注意哪些信号、多久复查一次？",
        ],
        "info_to_tell_doctor": [
            "我目前最主要的症状、出现时间以及变化趋势。",
            "我过去的疾病史、手术史以及家族相关病史。",
            "我正在使用的所有药物、保健品和过敏史。",
            "我最近的生活状态变化，比如睡眠、食欲、体重和情绪。",
        ],
        "tests_to_request": [
            "可以问医生：针对我的情况，是否需要做进一步的检查来明确诊断？",
            "可以问医生：现有的检查结果是否已经足够，还是需要补充哪些项目？",
            "可以问医生：这些检查的目的、过程和注意事项分别是什么？",
        ],
        "treatment_options_to_confirm": [
            "需要和医生确认：目前是否需要立即开始治疗，还是可以先观察？",
            "需要和医生确认：不同治疗方向的利弊，以及哪种更适合我的整体情况。",
            "需要和医生确认：后续的复查与随访计划如何安排。",
        ],
    }


def _sanitize_pack(pack: dict, query: str) -> dict:
    """对四类条目逐条跑 compliance_guard，并组装成 VisitPrepPack 结构。

    - 每条字符串都经过 compliance_guard 清洗（剥离诊断/剂量）。
    - 清洗后为空字符串的条目丢弃。
    - 若某一类全部为空，则用通用模板对应类目补齐，保证清单可用。
    """
    fallback = _generic_pack(query)
    result: dict = {}

    for field in _PACK_FIELDS:
        cleaned_items: list[str] = []
        for item in _coerce_items(pack.get(field)):
            cleaned, _violations = compliance_guard(item)
            cleaned = cleaned.strip()
            if cleaned:
                cleaned_items.append(cleaned)

        if not cleaned_items:
            # 该类目缺失时用通用模板兜底（同样过一遍 guard 以保持一致）
            for item in fallback.get(field, []):
                cleaned, _violations = compliance_guard(item)
                cleaned = cleaned.strip()
                if cleaned:
                    cleaned_items.append(cleaned)

        result[field] = cleaned_items[:_MAX_ITEMS_PER_CATEGORY]

    result["positioning_note"] = DEFAULT_POSITIONING_NOTE
    return result


async def generate_visit_prep(
    query: str,
    evidences: list[dict],
    emotion,
    llm_client,
) -> dict:
    """生成就医准备包（VisitPrepPack 结构的 dict）。

    Args:
        query: 患者自然语言查询。
        evidences: 检索到的证据列表（dict 列表，可为空）。
        emotion: 情绪状态（EmotionState 枚举或字符串），仅用于微调语气。
        llm_client: 同步 LLM 客户端，需提供 `.chat(messages, ...)` 方法。

    Returns:
        符合 VisitPrepPack 结构的 dict：四类条目列表 + positioning_note。

    Raises:
        Exception: 当 LLM 调用失败，或连通用模板都无法产出有效清单时抛出，
            供路由层转 5xx（R7.6）。
    """
    evidences = evidences or []
    has_evidence = bool(evidences)
    emotion_value = _normalize_emotion(emotion)
    evidence_digest = _build_evidence_digest(evidences) if has_evidence else ""

    prompt = _build_prompt(query, evidence_digest, emotion_value, has_evidence)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "请按要求生成就医准备包 JSON。"},
    ]

    # LLM 调用失败（异常）直接向上抛出 → 路由层转 5xx（R7.6）。
    response = await asyncio.to_thread(
        llm_client.chat, messages, temperature=0.3, max_tokens=1500
    )

    # 解析 LLM 输出；解析彻底失败则回退到通用模板。
    parsed = _parse_pack_json(response)
    if parsed is None:
        parsed = _generic_pack(query)

    pack = _sanitize_pack(parsed, query)

    # 兜底校验：四类全空属于彻底失败（理论上不会发生，模板已兜底），抛异常。
    if not any(pack.get(field) for field in _PACK_FIELDS):
        raise ValueError("生成就医准备包失败：未能产出任何有效条目。")

    return pack
