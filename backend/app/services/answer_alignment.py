"""
回答对齐工具：把用户自然语言问题拆成"疾病主题 + 任务意图"。

焦点抽取（disease / intent / audience / treatment_angle）保持为规则层纯函数，
为检索排序和回答 prompt 提供硬约束，避免回答只复述证据标题。

追问生成（clarification_questions）改为 LLM 驱动：根据查询语义动态判断
"是否需要追问"并生成针对性问题，不再使用硬编码模板。
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any


@dataclass(frozen=True)
class QueryFocus:
    """用户问题的轻量结构化焦点。"""

    disease: str = ""
    intent: str = "general"
    audience: str = "self"
    treatment_angle: str = ""
    keywords_cn: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)

    def prompt_context(self) -> str:
        """给 composer 的紧凑上下文，控制最终答案必须围绕原问。"""
        lines = [
            f"- 用户真正想问：{self.intent}",
            f"- 疾病/主题：{self.disease or '未明确'}",
            f"- 询问对象：{self.audience}",
        ]
        if self.treatment_angle:
            lines.append(f"- 重点方向：{self.treatment_angle}")
        if self.clarification_questions:
            lines.append("- 如需更精准，可补充：" + "；".join(self.clarification_questions[:3]))
        return "\n".join(lines)


_DISEASE_ALIASES: list[tuple[str, str, list[str]]] = [
    (
        "阿尔茨海默病",
        r"阿尔[兹茨]海默|老年痴呆|认知障碍|痴呆",
        ["阿尔茨海默病", "阿尔兹海默症", "认知障碍", "痴呆"],
    ),
    ("帕金森病", r"帕金森", ["帕金森病"]),
    ("肺腺癌", r"肺腺癌", ["肺腺癌"]),
    ("肺癌", r"肺癌", ["肺癌"]),
    ("胰腺癌", r"胰腺癌", ["胰腺癌"]),
    ("胶质母细胞瘤", r"胶质母细胞瘤|胶质瘤", ["胶质母细胞瘤", "胶质瘤"]),
    ("渐冻症", r"渐冻症|肌萎缩侧索硬化|ALS", ["渐冻症", "ALS", "肌萎缩侧索硬化"]),
]

_TREATMENT_TERMS = [
    "治疗方案",
    "最新治疗",
    "新疗法",
    "新药",
    "用药",
    "药物",
    "靶向",
    "免疫",
    "临床试验",
    "方案",
    "治疗",
]

_LATEST_TERMS = ["最新", "新进展", "进展", "前沿", "突破", "2024", "2025", "2026"]
_TRIAL_TERMS = ["临床试验", "招募", "入组", "NCT", "试验"]
_DRUG_TERMS = ["药物", "新药", "用药", "副作用", "不良反应", "剂量"]
_TEST_TERMS = ["检查", "化验", "指标", "报告", "CT", "MRI", "PET"]
_THIRD_PARTY_TERMS = ["朋友", "父亲", "母亲", "爸爸", "妈妈", "家人", "亲人", "老人", "孩子"]
_LATEST_SOURCE_PRIORITY = {
    "meeting": 6,
    "trial": 5,
    "guide": 4,
    "paper_en": 3,
    "paper_cn": 2,
    "package_insert": 1,
}


def analyze_query_focus(query: str) -> QueryFocus:
    """从原始问题中提取回答焦点，并生成非阻塞式追问。"""
    q = (query or "").strip()
    q_lower = q.lower()

    disease = _detect_disease(q)
    intent = _detect_intent(q, q_lower)
    audience = "family_or_friend" if any(term in q for term in _THIRD_PARTY_TERMS) else "self"
    treatment_angle = _detect_treatment_angle(q)

    keywords = []
    if disease:
        keywords.append(disease)
    keywords.extend(_keywords_for_intent(intent, treatment_angle))
    keywords = list(dict.fromkeys([kw for kw in keywords if kw]))

    # clarification_questions 由 LLM 异步生成（见 generate_clarification_questions），
    # 这里保持为空，由调用方在需要时异步补全。
    return QueryFocus(
        disease=disease,
        intent=intent,
        audience=audience,
        treatment_angle=treatment_angle,
        keywords_cn=keywords,
        clarification_questions=[],
    )


def has_clarification_answers(answers: Any) -> bool:
    """用户是否已经回答过至少一个有效追问。"""
    if not answers:
        return False
    for item in answers:
        answer = _answer_value(item, "answer")
        if answer.strip():
            return True
    return False


def format_clarification_context(answers: Any) -> str:
    """把前端逐题追问得到的回答整理成可放入检索/回答上下文的文本。"""
    if not answers:
        return ""

    lines: list[str] = []
    for item in answers:
        question = _answer_value(item, "question")
        answer = _answer_value(item, "answer")
        if not answer.strip():
            continue
        if question.strip():
            lines.append(f"- {question.strip()}：{answer.strip()}")
        else:
            lines.append(f"- {answer.strip()}")
    return "\n".join(lines)


def build_query_with_clarifications(query: str, answers: Any) -> str:
    """将原始问题和用户已回答的追问信息合并，供检索重写、排序和生成使用。"""
    base = (query or "").strip()
    context = format_clarification_context(answers)
    if not context:
        return base
    return f"{base}\n\n用户补充信息：\n{context}"


def is_latest_focused_query(focus: QueryFocus) -> bool:
    """是否应把检索重点放在近期研究、指南、会议和临床试验上。"""
    return focus.intent == "latest_treatment" or focus.treatment_angle in {
        "最新治疗方案",
        "最新研究进展",
    }


def latest_source_priority(source_type: str) -> int:
    return _LATEST_SOURCE_PRIORITY.get((source_type or "").lower(), 0)


def rank_latest_evidences(evidences: list[dict], focus: QueryFocus) -> list[dict]:
    """最新研究类问题：相关性优先，近期证据和前沿源靠前。"""
    if not evidences:
        return evidences
    indexed = list(enumerate(evidences))
    ranked = sorted(
        indexed,
        key=lambda item: (
            score_evidence_relevance(item[1], focus),
            _recentness_score(item[1]),
            latest_source_priority(str(item[1].get("source_type") or "")),
            -item[0],
        ),
        reverse=True,
    )
    return [item for _idx, item in ranked]


def _answer_value(item: Any, key: str) -> str:
    if isinstance(item, dict):
        return str(item.get(key) or "")
    return str(getattr(item, key, "") or "")


def _detect_disease(query: str) -> str:
    for canonical, pattern, _aliases in _DISEASE_ALIASES:
        if re.search(pattern, query, flags=re.IGNORECASE):
            return canonical
    return ""


def _detect_intent(query: str, query_lower: str) -> str:
    if any(term in query for term in _TRIAL_TERMS):
        return "clinical_trial"
    if any(term in query for term in _TEST_TERMS):
        return "test_explanation"
    if any(term in query for term in _DRUG_TERMS):
        return "drug_info"
    if any(term in query for term in _TREATMENT_TERMS) or any(term in query for term in _LATEST_TERMS):
        return "latest_treatment"
    if "是什么" in query or "什么意思" in query or "怎么回事" in query:
        return "disease_understanding"
    if "真的吗" in query or "听说" in query_lower or "谣言" in query:
        return "rumor_check"
    return "general"


def _detect_treatment_angle(query: str) -> str:
    if any(term in query for term in _LATEST_TERMS) and any(term in query for term in _TREATMENT_TERMS):
        return "最新治疗方案"
    if any(term in query for term in _LATEST_TERMS):
        return "最新研究进展"
    if any(term in query for term in _TRIAL_TERMS):
        return "临床试验/入组机会"
    if any(term in query for term in _DRUG_TERMS):
        return "药物信息"
    if any(term in query for term in _TREATMENT_TERMS):
        return "治疗选择"
    return ""


def _keywords_for_intent(intent: str, treatment_angle: str) -> list[str]:
    if intent == "latest_treatment":
        return ["治疗方案", "最新治疗", "新疗法", "临床试验", "指南"]
    if intent == "clinical_trial":
        return ["临床试验", "招募", "入组"]
    if intent == "drug_info":
        return ["药物", "疗效", "安全性", "副作用"]
    if intent == "test_explanation":
        return ["检查", "指标", "意义"]
    if treatment_angle:
        return [treatment_angle]
    return []


# ─── LLM 驱动追问生成 ────────────────────────────────────────────────────────

_CLARIFY_SYSTEM_PROMPT = """你是一位医学信息咨询助手。患者向你提出了一个医学问题，你需要判断：这个问题是否缺少关键信息，导致直接检索会得到过于宽泛或不精准的结果？

判断标准：
- 如果问题已经足够具体（如"PD-L1阳性代表什么"、"EGFR突变阳性的非小细胞肺癌一线靶向药有哪些"），不需要追问。
- 如果问题缺少关键医疗上下文（如分期、既往治疗、具体药物名、检测指标数值），需要追问。

追问原则：
- 最多生成 3 个追问，按重要性排序
- 问题要简短、具体，让患者容易回答
- 不要问患者的个人信息（姓名、电话等）
- 不要给出诊断建议
- 如果不需要追问，needs_clarification 为 false

返回严格的 JSON 格式（不要包含任何其他文字）：
{"needs_clarification": true/false, "questions": ["问题1", "问题2", "问题3"]}"""


async def generate_clarification_questions(
    query: str,
    focus: "QueryFocus",
    llm_client,
) -> list[str]:
    """使用 LLM 判断是否需要追问，并动态生成针对性追问问题。

    Args:
        query: 用户原始查询
        focus: 规则层已提取的焦点信息（disease / intent / audience）
        llm_client: LLMClient 实例

    Returns:
        追问问题列表（最多 3 条），不需要追问时返回空列表
    """
    # 构建 LLM 输入上下文
    context_parts = [f"患者查询：{query}"]
    if focus.disease:
        context_parts.append(f"识别到的疾病/主题：{focus.disease}")
    if focus.intent and focus.intent != "general":
        intent_cn = {
            "latest_treatment": "想了解最新治疗方案",
            "clinical_trial": "想了解临床试验",
            "drug_info": "想了解药物信息",
            "test_explanation": "想了解检查/化验结果",
            "disease_understanding": "想了解疾病基本知识",
            "rumor_check": "在求证某个说法",
        }.get(focus.intent, focus.intent)
        context_parts.append(f"用户意图：{intent_cn}")
    if focus.audience == "family_or_friend":
        context_parts.append("用户是代家人或朋友询问")

    user_prompt = "\n".join(context_parts)

    try:
        raw = await asyncio.to_thread(
            llm_client.chat,
            [
                {"role": "system", "content": _CLARIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        data = json.loads(raw)
        if data.get("needs_clarification") and isinstance(data.get("questions"), list):
            questions = [q.strip() for q in data["questions"] if q and q.strip()]
            return questions[:3]
    except (json.JSONDecodeError, TypeError, KeyError, Exception):
        # LLM 返回异常或解析失败时，不回退到规则模板——直接返回空列表，
        # 让用户直接进入检索，不在链路中阻塞。
        pass

    return []


def score_evidence_relevance(evidence: dict, focus: QueryFocus) -> int:
    """给单条证据打相关性分，用于在同源检索结果中优先选择更贴近原问的证据。"""
    if not isinstance(evidence, dict):
        return 0

    title = str(evidence.get("title") or "")
    abstract = str(evidence.get("abstract") or "")
    source_type = str(evidence.get("source_type") or "")
    text = f"{title} {abstract}"
    score = 0

    for kw in focus.keywords_cn:
        if kw and kw in text:
            score += 6 if kw == focus.disease else 3

    if focus.intent == "latest_treatment":
        if source_type in {"guide", "trial", "meeting"}:
            score += 5
        if any(term in text for term in ["治疗", "药物", "疗法", "临床试验", "指南", "共识"]):
            score += 4
        if any(term in text for term in ["2024", "2025", "2026", "最新", "新进展"]):
            score += 3
        score += _recentness_score(evidence)
    elif focus.intent == "clinical_trial":
        if source_type == "trial":
            score += 8
    elif focus.intent == "drug_info":
        if source_type in {"package_insert", "guide", "paper_en", "paper_cn"}:
            score += 4

    return score


def _recentness_score(evidence: dict) -> int:
    pub = evidence.get("publish_date") if isinstance(evidence, dict) else None
    if pub is None:
        return 0

    year = getattr(pub, "year", None)
    if year is None:
        match = re.search(r"(20\d{2})", str(pub))
        if not match:
            return 0
        try:
            year = int(match.group(1))
        except ValueError:
            return 0

    current_year = date.today().year
    if year >= current_year:
        return 6
    if year == current_year - 1:
        return 5
    if year == current_year - 2:
        return 4
    if year == current_year - 3:
        return 2
    return 0


def rerank_evidences_for_query(evidences: list[dict], focus: QueryFocus) -> list[dict]:
    """按问题相关性稳定重排证据；同分时保持原顺序。"""
    if not evidences:
        return evidences
    if is_latest_focused_query(focus):
        return rank_latest_evidences(evidences, focus)
    indexed = list(enumerate(evidences))
    ranked = sorted(
        indexed,
        key=lambda item: (score_evidence_relevance(item[1], focus), -item[0]),
        reverse=True,
    )
    return [item for _idx, item in ranked]
