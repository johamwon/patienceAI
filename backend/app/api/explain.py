"""
通俗化解释 API 路由

提供三层结构化回答生成接口
支持本地缓存 + 每日自动更新
"""

from fastapi import APIRouter, HTTPException
from ..models.schemas import ExplainRequest, ExplainResponse
from ..services.llm_client import llm_client
from ..services.cache_service import cache_service, start_background_refresh
import traceback

router = APIRouter()

# 启动后台自动刷新线程
start_background_refresh()


@router.post("/explain", response_model=ExplainResponse)
async def explain_evidence(req: ExplainRequest):
    """
    将医学证据解释为患者可读的三层结构化回答

    缓存策略：
    - 先查本地缓存，命中且未过期则直接返回
    - 未命中则走完整检索+通俗化流程
    - 结果写入缓存供后续使用
    - 热门疾病查询每日自动更新
    """
    from ..services.knows_client import knows_client
    from ..services.intent_classifier import parse_query
    from agents.core.simplification_loop import SimplificationLoop
    from agents.demo_scenarios import get_demo_scenario

    try:
        # 1. 尝试从缓存获取
        cache_key = f"{req.query}"
        cached_result = cache_service.get(req.query, max_results=5)
        if cached_result is not None:
            print(f"[Cache] 缓存命中: {req.query[:30]}...")
            return ExplainResponse(**cached_result)

        print(f"[Cache] 缓存未命中，开始生成: {req.query[:30]}...")

        # 2. 意图识别
        parsed = parse_query(req.query)
        risk_level = parsed["risk_level"]

        # 3. 检索证据
        sources = {
            "disease_understanding": ["paper_en", "paper_cn", "guide"],
            "treatment_progress": ["paper_en", "paper_cn", "meeting", "guide"],
            "drug_info": ["paper_en", "paper_cn", "package_insert", "guide"],
            "test_explanation": ["guide", "paper_en"],
            "clinical_trial": ["trial", "paper_en"],
            "rumor_check": ["guide", "paper_cn"],
            "high_risk": ["guide", "paper_en"],
            "unknown": ["paper_en", "paper_cn", "guide"],
        }.get(parsed["intent"], ["paper_en", "paper_cn", "guide"])

        try:
            evidences = knows_client.search_multi(req.query, sources, max_results_per_source=10)
        except Exception as e:
            print(f"[WARN] KnowS search failed: {e}")
            evidences = []

        # 4. 如果 KnowS 无结果，尝试匹配演示场景
        if not evidences:
            demo = get_demo_scenario(req.query)
            if demo:
                evidences = demo["evidences"]
                if demo.get("risk_level"):
                    risk_level = demo["risk_level"]
                print(f"[INFO] Using demo scenario: {demo['id']}")

        # 5. 仍然无证据
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
            # 缓存空结果
            cache_service.set(req.query, result.model_dump(), max_results=5)
            return result

        # 6. 多智能体通俗化翻译
        loop = SimplificationLoop(llm_client=llm_client, max_iterations=2)
        loop_result = await loop.run(evidences, req.query)

        result = ExplainResponse(
            layer1_conclusion=loop_result["layer1_conclusion"],
            layer2_evidence_cards=loop_result["layer2_evidence_cards"],
            layer3_patient_explanation=loop_result["layer3_patient_explanation"],
            risk_level=risk_level,
            risk_message=parsed.get("risk_message"),
        )

        # 7. 写入缓存
        cache_service.set(req.query, result.model_dump(), max_results=5)
        print(f"[Cache] 已缓存: {req.query[:30]}...")
        return result

    except Exception as e:
        print(f"[ERROR] explain_evidence failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"解释生成失败: {str(e)}")
