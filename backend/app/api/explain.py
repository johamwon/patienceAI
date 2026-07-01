"""
通俗化解释 API 路由

提供三层结构化回答生成接口
支持本地缓存 + 每日自动更新 + 查询重写优化检索质量

在基础三层解释之上集成（patient-companion-enhancements）：
- 情绪识别（Emotion_Detector）→ emotion_state（R2.5）
- 急症联动（R2.4）：URGENT 时强制提升 risk_level 至 high 并注入就医提示
- 轻量会话记忆（Session_Memory）→ 多轮上下文（R4）
- 检索路由（Search_Router）：按 rare/severe/intent 选源排序（R9.5）
- 陪伴暖场白（Companion_Engine）→ companion_message（R3.1）
- 研究进展标注 + 临床试验卡片（R11.1/R12.1/R12.2）
"""

from datetime import datetime
import asyncio
import json

from fastapi import APIRouter, HTTPException
from ..models.schemas import ExplainRequest, ExplainResponse, EmotionState, TrialCard, SubscriptionOffer
from ..services.llm_client import llm_client
from ..services.cache_service import cache_service, start_background_refresh
from ..services.query_rewriter import rewrite_query
import traceback

router = APIRouter()

# 启动后台自动刷新线程
start_background_refresh()

# 会话记忆读取的最近轮数（传给陪伴引擎做上下文）
_HISTORY_TURNS = 5

# 急症联动（R2.4）：URGENT 情绪下若无风险提示文案时的兜底就医提示
_URGENT_RISK_MESSAGE = (
    "您的描述提示可能存在紧急状况，本系统无法判断病情。请立即就医或拨打急救电话，"
    "由专业医生当面评估处理。"
)


def _build_subscription_offer(query: str) -> SubscriptionOffer | None:
    """Build an opt-in research radar offer from the query topic.

    This does not create a subscription. It only gives the frontend a disease
    keyword and a patient-facing prompt; creation happens only after explicit
    user action.
    """
    try:
        from agents.core.visit_prep_generator import _extract_disease_topic

        topic = _extract_disease_topic(query)
    except Exception:
        topic = query.strip()[:20]

    if not topic or len(topic.strip()) < 2:
        return None

    text = (
        f"要不要让小光帮你持续关注「{topic}」的最新研究？"
        "如果以后有新的高质量指南、临床试验或重要研究，"
        "我可以通过邮件提醒你，"
        "并用能看懂的话解释研究阶段和不确定性。"
    )
    text = _clean(text)
    return SubscriptionOffer(disease_keyword=topic.strip(), prompt_text=text)


def _evidence_to_dict(ev) -> dict:
    """把证据统一规整为 dict（Evidence pydantic 对象 → model_dump，dict 原样）。

    供 companion_engine / research_stage / validate_nct 等以 dict 为输入的工具复用。
    """
    if isinstance(ev, dict):
        return ev
    if hasattr(ev, "model_dump"):
        try:
            return ev.model_dump()
        except Exception:
            pass
    # 兜底：尝试 __dict__
    return dict(getattr(ev, "__dict__", {}) or {})


def _pick(evidence: dict, *keys) -> str:
    """从 evidence 顶层或其 raw 子字典中按 keys 顺序取第一个非空值，缺失返回空串。"""
    raw = evidence.get("raw") if isinstance(evidence.get("raw"), dict) else {}
    for key in keys:
        for source in (evidence, raw):
            val = source.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    return ""


def _build_trial_card(evidence: dict) -> TrialCard:
    """从一条 trial 证据组装 TrialCard，缺失字段交由模型默认（"信息未提供"）。"""
    nct_id = _pick(evidence, "nct_id", "nctId", "nct")
    fields: dict = {"nct_id": nct_id}

    status = _pick(evidence, "recruitment_status", "status", "recruitmentStatus", "overall_status")
    if status:
        fields["recruitment_status"] = status

    phase = _pick(evidence, "phase", "trial_phase", "study_phase")
    if phase:
        fields["phase"] = phase

    eligibility = _pick(
        evidence, "eligibility", "eligibility_criteria", "inclusion_criteria", "criteria"
    )
    if eligibility:
        fields["eligibility"] = eligibility

    location = _pick(evidence, "location", "locations", "site", "country", "city")
    if location:
        fields["location"] = location

    return TrialCard(**fields)


def _is_empty_evidence_cache(cached_data: dict) -> bool:
    """
    检查缓存结果是否为空证据（之前因检索失败而缓存的空结果）

    如果 layer2_evidence_cards 为空列表，说明之前没有找到证据，
    应该跳过缓存重新检索，因为可能是之前的临时检索失败。
    """
    cards = cached_data.get("layer2_evidence_cards", None)
    return cards is not None and len(cards) == 0


_PROMPT_LEAK_MARKERS = (
    "Rewrite this for a high school reading level",
    "[模拟响应]",
    "请配置 LLM_API_KEY",
    "请你以\"小光\"的身份",
    "用户现在需要",
    "患者的提问：",
    "检索到的证据摘要：",
    "写作要求：",
    "Got it",
    "let's tackle",
    "original text is",
    "First I need",
    "Chinese expert consensus",
)


def _contains_prompt_leak(data) -> bool:
    """Detect cached mock/prompt leakage and force regeneration."""
    try:
        text = json.dumps(data, ensure_ascii=False)
    except TypeError:
        text = str(data)
    return any(marker in text for marker in _PROMPT_LEAK_MARKERS)


@router.post("/explain", response_model=ExplainResponse)
async def explain_evidence(req: ExplainRequest):
    """
    将医学证据解释为患者可读的三层结构化回答

    缓存策略：
    - 先查本地缓存，命中且未过期则直接返回（含新增的陪伴/情绪/研究字段）
    - 如果缓存结果的证据卡片为空，跳过缓存重新检索（可能是之前临时检索失败）
    - 未命中则走完整检索+通俗化流程
    - 结果写入缓存供后续使用（不缓存空证据结果）
    - 热门疾病查询每日自动更新
    """
    from ..services.knows_client import knows_client
    from ..services.intent_classifier import parse_query
    from ..services.emotion_detector import detect_emotion
    from ..services.session_memory import session_store, SessionTurn
    from ..services.companion_engine import generate_companion_message
    from ..services.research_stage import to_research_progress, validate_nct
    from .search import select_sources, sort_evidences
    from agents.core.simplification_loop import SimplificationLoop
    from agents.demo_scenarios import get_demo_scenario

    try:
        # 1. 情绪识别（R2.5）与 查询重写（检索前置）——两者互不依赖，并发执行。
        #    detect_emotion / rewrite_query 都是含 LLM 的同步函数，用 to_thread 包裹后
        #    asyncio.gather 并发，省去一次串行 LLM 往返。两者都需在检索前完成
        #    （emotion 用于急症联动/陪伴，rewrite 用于选源），故在此处一起算好。
        emotion, rewrite_result = await asyncio.gather(
            asyncio.to_thread(detect_emotion, req.query, llm_client),
            asyncio.to_thread(rewrite_query, req.query),
        )

        # 2. 会话记忆（R4）：有 session_id 才读写；append 本轮，再取最近 N 轮做 history
        history = []
        if req.session_id:
            session_store.append(
                req.session_id,
                SessionTurn(
                    query=req.query,
                    emotion=emotion.value,
                    timestamp=datetime.now().isoformat(),
                ),
            )
            history = session_store.recent(req.session_id, _HISTORY_TURNS)

        # 3. 尝试从缓存获取（跳过空证据缓存；命中时补齐情绪/陪伴等会话相关字段）
        cached_result = cache_service.get(req.query, max_results=5)
        if cached_result is not None and (
            _is_empty_evidence_cache(cached_result) or _contains_prompt_leak(cached_result)
        ):
            print(f"[Cache] 跳过不可用缓存，重新检索: {req.query[:30]}...")
            cache_service.delete(req.query, max_results=5)
            cached_result = None
        if cached_result is not None:
            print(f"[Cache] 缓存命中: {req.query[:30]}...")
            result = ExplainResponse(**cached_result)
            # 情绪/陪伴/会话相关字段与请求强相关，缓存命中也按本轮重算
            result.emotion_state = emotion.value
            risk_level = result.risk_level
            risk_message = result.risk_message
            # 急症联动（R2.4）
            risk_level, risk_message = _apply_urgent_escalation(
                emotion, risk_level, risk_message
            )
            result.risk_level = risk_level
            result.risk_message = risk_message
            evidence_dicts = [
                c.model_dump() if hasattr(c, "model_dump") else c
                for c in (result.layer2_evidence_cards or [])
            ]
            result.companion_message = await generate_companion_message(
                req.query, emotion, evidence_dicts, risk_level, risk_message, history, llm_client
            )
            result.subscription_offer = _build_subscription_offer(req.query)
            return _apply_compliance_gate(result)

        print(f"[Cache] 缓存未命中，开始生成: {req.query[:30]}...")

        # 4. 意图识别（含 rare_disease / severe_condition 标记）
        parsed = parse_query(req.query)
        risk_level = parsed["risk_level"]
        risk_message = parsed.get("risk_message")

        # 5. 查询重写结果（已在第 1 步与情绪识别并发算好）
        print(f"[QueryRewrite] CN: '{rewrite_result.medical_terms_cn}' | EN: '{rewrite_result.medical_terms_en}'")

        # 6. 检索路由（R9.5）：罕见病/重症优先前沿源；否则意图映射 + 重写建议融合
        if parsed.get("rare_disease") or parsed.get("severe_condition"):
            sources = select_sources(parsed)
        else:
            intent_sources = select_sources(parsed)
            rewrite_sources = rewrite_result.suggested_sources
            sources = list(dict.fromkeys(intent_sources + rewrite_sources))

        # 7. 按源类型使用对应语言的优化查询并行检索（每源不同 query）
        try:
            source_query_pairs = [
                (source, rewrite_result.get_query_for_source(source))
                for source in sources
            ]
            evidences = knows_client.search_multi_queries(
                source_query_pairs, max_results_per_source=10
            )
        except Exception as e:
            print(f"[WARN] KnowS search failed: {e}")
            evidences = []

        # 8. 如果 KnowS 无结果，尝试匹配演示场景
        if not evidences:
            demo = get_demo_scenario(req.query)
            if demo:
                evidences = demo["evidences"]
                if demo.get("risk_level"):
                    risk_level = demo["risk_level"]
                print(f"[INFO] Using demo scenario: {demo['id']}")

        # 9. 排序（罕见病/重症按发表时间降序，否则保持原序）
        evidences = sort_evidences(evidences, parsed)

        # 10. 急症联动（R2.4）：URGENT 时强制提升 risk_level 并注入就医提示
        risk_level, risk_message = _apply_urgent_escalation(
            emotion, risk_level, risk_message
        )

        # 统一规整证据为 dict，供陪伴/研究阶段/试验卡片复用
        evidence_dicts = [_evidence_to_dict(ev) for ev in evidences]

        # 11. 仍然无证据：返回空结果路径（仍带情绪/陪伴/风险字段；不缓存空结果）
        if not evidences:
            companion_message = await generate_companion_message(
                req.query, emotion, evidence_dicts, risk_level, risk_message, history, llm_client
            )
            result = ExplainResponse(
                layer1_conclusion={
                    "text": "未找到相关医学证据，请尝试使用更具体的医学名词进行查询。",
                    "citations": [],
                },
                layer2_evidence_cards=[],
                layer3_patient_explanation={
                    "what_is_it": "抱歉，目前没有找到与您查询相关的权威医学文献。",
                    "what_evidence_says": "建议您尝试使用更具体的疾病名称或医学术语进行查询，例如'肺腺癌'而不是'肺癌'。",
                    "what_it_means_for_you": "如需了解特定疾病信息，请咨询您的主治医生或前往正规医疗机构。",
                    "when_to_see_doctor": "如您有具体症状或健康问题，请及时就医。",
                    "disclaimer": "本内容为医学文献通俗化解释，仅供参考，不构成诊疗建议，不替代医生判断。",
                },
                risk_level=risk_level,
                risk_message=risk_message,
                companion_message=companion_message,
                emotion_state=emotion.value,
                trial_cards=[],
                research_progress=[],
                subscription_offer=_build_subscription_offer(req.query),
            )
            # 不缓存空结果——下次重试时可能检索成功
            return _apply_compliance_gate(result)

        # 12. 通俗化主体回答 与 陪伴暖场白 并发执行（互不依赖，最大并行收益）。
        #     - SimplificationLoop.run 产出 simplified_text 供 composer（仍含 1-2 次 LLM）
        #     - generate_companion_message 生成暖场白（1 次 LLM）
        #     急症联动已在第 10 步完成，companion 拿到的是提升后的 risk_level/risk_message。
        loop = SimplificationLoop(llm_client=llm_client, max_iterations=2)
        loop_result, companion_message = await asyncio.gather(
            loop.run(evidence_dicts, req.query),
            generate_companion_message(
                req.query, emotion, evidence_dicts, risk_level, risk_message, history, llm_client
            ),
        )

        # 13. 研究进展标注（R11.1）
        research_progress = [to_research_progress(ev) for ev in evidence_dicts]

        # 14. 临床试验卡片（R12.1/R12.2）：source_type=="trial" 且 NCT 校验通过
        trial_cards = []
        for ev in evidence_dicts:
            source_type = (ev.get("source_type") or "").lower()
            if source_type == "trial" and validate_nct(ev):
                trial_cards.append(_build_trial_card(ev))

        result = ExplainResponse(
            layer1_conclusion=loop_result["layer1_conclusion"],
            layer2_evidence_cards=loop_result["layer2_evidence_cards"],
            layer3_patient_explanation=loop_result["layer3_patient_explanation"],
            risk_level=risk_level,
            risk_message=risk_message,
            companion_message=companion_message,
            emotion_state=emotion.value,
            trial_cards=trial_cards,
            research_progress=research_progress,
            subscription_offer=_build_subscription_offer(req.query),
        )

        # 16. 写入缓存（仅缓存有证据的结果）
        cache_service.set(req.query, result.model_dump(), max_results=5)
        print(f"[Cache] 已缓存: {req.query[:30]}...")
        return _apply_compliance_gate(result)

    except Exception as e:
        print(f"[ERROR] explain_evidence failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"解释生成失败: {str(e)}")


def _clean(text):
    """对单个文本字段过 compliance_guard 取清洗后文本；非字符串/空值原样返回。"""
    from agents.prompts.persona import compliance_guard

    if not text or not isinstance(text, str):
        return text
    cleaned, _violations = compliance_guard(text)
    return cleaned


# 风险等级兜底提示（R13.5）：high/prohibited 必须有非空 risk_message。
_RISK_FALLBACK_MESSAGE = {
    "high": (
        "您的提问涉及个体化诊疗决策，系统无法提供此类建议。"
        "请立即咨询您的主治医生或前往正规医疗机构就诊。"
    ),
    "prohibited": (
        "本系统仅提供医学文献的通俗化解释服务，不提供诊断、处方或个体化治疗建议。"
        "请咨询专业医生。"
    ),
}


def _apply_compliance_gate(result: ExplainResponse) -> ExplainResponse:
    """出口合规闸（R1.4/R1.5/R13.1-R13.5）。

    在所有返回路径统一调用：对所有患者可见文本过 compliance_guard 清洗
    （剥离面向个体的诊断/处方/剂量表述），并强制保留 high/prohibited 风险提示。

    - 清洗：companion_message、layer1_conclusion.text、layer3 各内容字段
      （跳过 disclaimer 免责声明本身）、research_progress[].summary、
      layer2 证据卡片文本字段（outcome/intervention/comparator/limitations/study_type）。
    - 风险提示强制保留：risk_level ∈ {high, prohibited} 且 risk_message 为空时，
      注入对应等级的兜底提示；companion_message 不替代 risk_message，两者并存。

    直接修改并返回同一个 ExplainResponse 对象。
    """
    # 1) 陪伴暖场白
    result.companion_message = _clean(result.companion_message)

    # 2) 第一层结论
    if result.layer1_conclusion is not None:
        result.layer1_conclusion.text = _clean(result.layer1_conclusion.text)

    # 3) 第三层患者解释（跳过 disclaimer 免责声明本身）
    explanation = result.layer3_patient_explanation
    if explanation is not None:
        explanation.what_is_it = _clean(explanation.what_is_it)
        explanation.what_evidence_says = _clean(explanation.what_evidence_says)
        explanation.what_it_means_for_you = _clean(explanation.what_it_means_for_you)
        explanation.when_to_see_doctor = _clean(explanation.when_to_see_doctor)

    # 4) 研究进展
    for progress in result.research_progress or []:
        progress.summary = _clean(progress.summary)
        if progress.uncertainty_note:
            progress.uncertainty_note = _clean(progress.uncertainty_note)

    # 4.5) 订阅邀约
    if result.subscription_offer is not None:
        result.subscription_offer.prompt_text = _clean(result.subscription_offer.prompt_text)

    # 5) 第二层证据卡片文本字段
    for card in result.layer2_evidence_cards or []:
        card.study_type = _clean(card.study_type)
        card.sample_size = _clean(card.sample_size)
        card.intervention = _clean(card.intervention)
        card.comparator = _clean(card.comparator)
        card.outcome = _clean(card.outcome)
        card.limitations = _clean(card.limitations)

    # 6) 风险提示强制保留（R13.5）：清洗后仍要保证 high/prohibited 有 risk_message
    level = (result.risk_level or "").lower()
    if level in _RISK_FALLBACK_MESSAGE:
        if not result.risk_message or not str(result.risk_message).strip():
            result.risk_message = _RISK_FALLBACK_MESSAGE[level]

    return result


def _apply_urgent_escalation(emotion: EmotionState, risk_level: str, risk_message):
    """急症联动（R2.4）：URGENT 时把 risk_level 提升至至少 high，并确保 risk_message 含就医提示。

    返回 (risk_level, risk_message)。非 URGENT 原样返回。
    """
    if emotion != EmotionState.URGENT:
        return risk_level, risk_message

    # prohibited 已高于 high，不下调；其余统一提升到 high
    if (risk_level or "").lower() != "prohibited":
        risk_level = "high"

    if not risk_message or not str(risk_message).strip():
        risk_message = _URGENT_RISK_MESSAGE

    return risk_level, risk_message
