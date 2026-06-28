"""
通俗化解释 API 路由

提供三层结构化回答生成接口
支持本地缓存 + 每日自动更新
支持查询重写优化检索质量
"""

from fastapi import APIRouter, HTTPException
from ..models.schemas import ExplainRequest, ExplainResponse
from ..services.llm_client import llm_client
from ..services.cache_service import cache_service, start_background_refresh
from ..services.query_rewriter import rewrite_query
import traceback

router = APIRouter()

# 启动后台自动刷新线程
start_background_refresh()


def _is_empty_evidence_cache(cached_data: dict) -> bool:
    """
    检查缓存结果是否为空证据（之前因检索失败而缓存的空结果）

    如果 layer2_evidence_cards 为空列表，说明之前没有找到证据，
    应该跳过缓存重新检索，因为可能是之前的临时检索失败。
    """
    cards = cached_data.get("layer2_evidence_cards", None)
    return cards is not None and len(cards) == 0


@router.post("/explain", response_model=ExplainResponse)
async def explain_evidence(req: ExplainRequest):
    """
    将医学证据解释为患者可读的三层结构化回答

    缓存策略：
    - 先查本地缓存，命中且未过期则直接返回
    - 如果缓存结果的证据卡片为空，跳过缓存重新检索
    - 未命中则走完整检索+通俗化流程
    - 结果写入缓存供后续使用
    - 热门疾病查询每日自动更新
    """
    from ..services.knows_client import knows_client
    from ..services.intent_classifier import parse_query
    from agents.core.simplification_loop import SimplificationLoop
    from agents.demo_scenarios import get_demo_scenario

    try:
        # 1. 尝试从缓存获取（跳过空证据缓存）
        cached_result = cache_service.get(req.query, max_results=5)
        if cached_result is not None:
            if _is_empty_evidence_cache(cached_result):
                # 缓存的是空结果，删除并重新生成
                print(f"[Cache] 跳过空证据缓存，重新检索: {req.query[:30]}...")
                cache_service.delete(req.query, max_results=5)
            else:
                print(f"[Cache] 缓存命中: {req.query[:30]}...")
                return ExplainResponse(**cached_result)

        print(f"[Cache] 缓存未命中，开始生成: {req.query[:30]}...")

        # 2. 意图识别
        parsed = parse_query(req.query)
        risk_level = parsed["risk_level"]

        # 3. 查询重写：提取医学术语 + 英文翻译
        rewrite_result = rewrite_query(req.query)
        print(f"[QueryRewrite] CN: '{rewrite_result.medical_terms_cn}' | EN: '{rewrite_result.medical_terms_en}'")

        # 4. 智能源选择：合并意图映射和查询内容分析
        intent_sources = {
            "disease_understanding": ["paper_en", "paper_cn", "guide"],
            "treatment_progress": ["paper_en", "paper_cn", "meeting", "guide"],
            "drug_info": ["paper_en", "paper_cn", "package_insert", "guide"],
            "test_explanation": ["guide", "paper_en"],
            "clinical_trial": ["trial", "paper_en"],
            "rumor_check": ["guide", "paper_cn"],
            "high_risk": ["guide", "paper_en"],
            "unknown": ["paper_en", "paper_cn", "guide"],
        }.get(parsed["intent"], ["paper_en", "paper_cn", "guide"])

        # 合并意图映射和重写建议的源
        rewrite_sources = rewrite_result.suggested_sources
        sources = list(dict.fromkeys(intent_sources + rewrite_sources))

        # 5. 按源类型使用对应语言的优化查询检索
        try:
            all_evidences = []
            seen_ids: set[str] = set()

            for source in sources:
                optimized_query = rewrite_result.get_query_for_source(source)
                try:
                    results = knows_client.search(source, optimized_query, max_results=10)
                    for ev in results:
                        dedup_key = ev.pmid or ev.doi or ev.nct_id or ev.id
                        if dedup_key not in seen_ids:
                            seen_ids.add(dedup_key)
                            all_evidences.append(ev)
                except Exception as e:
                    print(f"[WARN] KnowS search failed for {source}: {e}")
                    continue

            evidences = all_evidences
        except Exception as e:
            print(f"[WARN] KnowS search failed: {e}")
            evidences = []

        # 6. 如果 KnowS 无结果，尝试匹配演示场景
        if not evidences:
            demo = get_demo_scenario(req.query)
            if demo:
                evidences = demo["evidences"]
                if demo.get("risk_level"):
                    risk_level = demo["risk_level"]
                print(f"[INFO] Using demo scenario: {demo['id']}")

        # 7. 仍然无证据
        if not evidences:
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
                risk_message=parsed.get("risk_message"),
            )
            # 不缓存空结果——下次重试时可能检索成功
            return result

        # 8. 多智能体通俗化翻译
        loop = SimplificationLoop(llm_client=llm_client, max_iterations=2)
        # 将 Evidence Pydantic 对象转为 dict 供 SimplificationLoop 使用
        evidences_dicts = [
            e.model_dump() if hasattr(e, 'model_dump') else e
            for e in evidences
        ]
        loop_result = await loop.run(evidences_dicts, req.query)

        result = ExplainResponse(
            layer1_conclusion=loop_result["layer1_conclusion"],
            layer2_evidence_cards=loop_result["layer2_evidence_cards"],
            layer3_patient_explanation=loop_result["layer3_patient_explanation"],
            risk_level=risk_level,
            risk_message=parsed.get("risk_message"),
        )

        # 9. 写入缓存（仅缓存有证据的结果）
        cache_service.set(req.query, result.model_dump(), max_results=5)
        print(f"[Cache] 已缓存: {req.query[:30]}...")
        return result

    except Exception as e:
        print(f"[ERROR] explain_evidence failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"解释生成失败: {str(e)}")
