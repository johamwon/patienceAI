"""
回答对齐工具：把用户自然语言问题拆成“疾病主题 + 任务意图 + 缺失上下文”。

这里刻意保持为规则层纯函数，不依赖 LLM 或外部检索。它的作用不是替代模型，
而是在检索排序和最终回答 prompt 中提供硬约束，避免回答只复述证据标题、
没有真正回应用户问的“最新治疗方案/副作用/检查含义”等具体诉求。
"""

from dataclasses import dataclass, field
import re


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

    questions = _build_clarification_questions(
        disease=disease,
        intent=intent,
        audience=audience,
        query=q,
    )

    return QueryFocus(
        disease=disease,
        intent=intent,
        audience=audience,
        treatment_angle=treatment_angle,
        keywords_cn=keywords,
        clarification_questions=questions,
    )


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


def _build_clarification_questions(
    *,
    disease: str,
    intent: str,
    audience: str,
    query: str,
) -> list[str]:
    """模型拿不准时的追问，但不阻塞当前回答。"""
    questions: list[str] = []

    if not disease:
        questions.append("你想了解的是哪一种疾病或诊断名称？")

    if intent in {"latest_treatment", "clinical_trial", "drug_info"}:
        if disease == "阿尔茨海默病":
            questions.append("目前诊断处于轻度、中度还是重度？是否还属于轻度认知障碍阶段？")
            questions.append("现在是否正在使用多奈哌齐、美金刚、仑卡奈单抗等药物？")
        else:
            questions.append("目前处于哪个分期/阶段，已经接受过哪些治疗？")
        questions.append("你更想了解已获批治疗、临床试验机会，还是日常照护和就医沟通？")

    if audience == "family_or_friend" and intent in {"latest_treatment", "general"}:
        questions.append("患者年龄、主要症状和最近一次医生诊断是什么？")

    # 去重并限制长度，避免前端占太多空间。
    return list(dict.fromkeys(questions))[:3]


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
    elif focus.intent == "clinical_trial":
        if source_type == "trial":
            score += 8
    elif focus.intent == "drug_info":
        if source_type in {"package_insert", "guide", "paper_en", "paper_cn"}:
            score += 4

    return score


def rerank_evidences_for_query(evidences: list[dict], focus: QueryFocus) -> list[dict]:
    """按问题相关性稳定重排证据；同分时保持原顺序。"""
    if not evidences:
        return evidences
    indexed = list(enumerate(evidences))
    ranked = sorted(
        indexed,
        key=lambda item: (score_evidence_relevance(item[1], focus), -item[0]),
        reverse=True,
    )
    return [item for _idx, item in ranked]
