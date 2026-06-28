"""
搜索 API 路由

提供 KnowS AI 多源检索接口
支持查询重写：将患者自然语言转为优化医学术语
"""

from fastapi import APIRouter, HTTPException
from ..models.schemas import SearchRequest, SearchResponse, Evidence
from ..services.knows_client import knows_client
from ..services.intent_classifier import parse_query
from ..services.query_rewriter import rewrite_query

router = APIRouter()

# 意图 → 检索源映射（作为 LLM 重写建议的后备）
INTENT_TO_SOURCES = {
    "disease_understanding": ["paper_en", "paper_cn", "guide"],
    "treatment_progress": ["paper_en", "paper_cn", "meeting", "guide"],
    "drug_info": ["paper_en", "paper_cn", "package_insert", "guide"],
    "test_explanation": ["guide", "paper_en"],
    "clinical_trial": ["trial", "paper_en"],
    "rumor_check": ["guide", "paper_cn"],
    "high_risk": ["guide", "paper_en"],
    "unknown": ["paper_en", "paper_cn", "guide"],
}

SOURCE_DISPLAY_NAMES = {
    "paper_en": "英文论文",
    "paper_cn": "中文论文",
    "guide": "临床指南",
    "trial": "临床试验",
    "meeting": "医学会议",
    "package_insert": "药品说明书",
}


@router.post("/search", response_model=SearchResponse)
async def search_evidence(req: SearchRequest):
    """
    检索医学证据

    - 自动识别查询意图
    - LLM 重写查询：提取医学术语 + 英文翻译
    - 智能源选择：结合意图分类和查询内容
    - 返回结构化证据列表
    """
    # 1. 意图识别
    parsed = parse_query(req.query)

    # 2. 查询重写：提取医学术语 + 英文翻译
    rewrite_result = rewrite_query(req.query)
    print(f"[QueryRewrite] CN: '{rewrite_result.medical_terms_cn}' | EN: '{rewrite_result.medical_terms_en}'")

    # 3. 智能源选择：合并意图分类和查询内容分析的结果
    if req.sources:
        # 用户显式指定了源，尊重用户选择
        sources = req.sources
    else:
        # 合并意图映射的源和 LLM/规则建议的源（去重）
        intent_sources = INTENT_TO_SOURCES.get(parsed["intent"], ["paper_en", "paper_cn", "guide"])
        rewrite_sources = rewrite_result.suggested_sources
        # 以意图映射为基础，补充重写建议的源
        sources = list(dict.fromkeys(intent_sources + rewrite_sources))

    # 4. 按源类型使用对应语言的优化查询调用 KnowS AI
    try:
        all_evidences: list[Evidence] = []
        seen_ids: set[str] = set()
        max_per_source = req.max_results // len(sources) + 1

        for source in sources:
            # 根据端点选择合适的查询语言
            optimized_query = rewrite_result.get_query_for_source(source)
            try:
                results = knows_client.search(source, optimized_query, max_per_source)
                for ev in results:
                    dedup_key = ev.pmid or ev.doi or ev.nct_id or ev.id
                    if dedup_key not in seen_ids:
                        seen_ids.add(dedup_key)
                        all_evidences.append(ev)
            except Exception as e:
                print(f"[WARN] KnowS search failed for {source}: {e}")
                continue

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KnowS AI 检索失败: {str(e)}")

    # 5. 构造响应
    return SearchResponse(
        query=req.query,
        intent=parsed["intent"],
        risk_level=parsed["risk_level"],
        evidences=all_evidences,
        total=len(all_evidences),
    )


@router.get("/sources")
async def list_sources():
    """列出可用的检索源"""
    return {
        "sources": [
            {"id": "paper_en", "name": "英文论文", "description": "国际医学文献检索"},
            {"id": "paper_cn", "name": "中文论文", "description": "中文医学文献检索"},
            {"id": "guide", "name": "临床指南", "description": "权威临床诊疗指南"},
            {"id": "trial", "name": "临床试验", "description": "临床试验注册信息"},
            {"id": "meeting", "name": "医学会议", "description": "最新会议摘要"},
            {"id": "package_insert", "name": "药品说明书", "description": "官方药品说明书"},
        ]
    }
