"""
搜索 API 路由

提供 KnowS AI 多源检索接口
"""

from fastapi import APIRouter, HTTPException
from ..models.schemas import SearchRequest, SearchResponse, Evidence
from ..services.knows_client import knows_client
from ..services.intent_classifier import parse_query

router = APIRouter()

# 意图 → 检索源映射
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
    - 根据意图选择 KnowS AI 检索源
    - 返回结构化证据列表
    """
    # 1. 意图识别
    parsed = parse_query(req.query)

    # 2. 选择检索源
    if req.sources:
        sources = req.sources
    else:
        sources = INTENT_TO_SOURCES.get(parsed["intent"], ["paper_en", "paper_cn", "guide"])

    # 3. 并行调用 KnowS AI
    try:
        evidences = knows_client.search_multi(
            query=req.query,
            sources=sources,
            max_results_per_source=req.max_results // len(sources) + 1,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KnowS AI 检索失败: {str(e)}")

    # 4. 构造响应
    return SearchResponse(
        query=req.query,
        intent=parsed["intent"],
        risk_level=parsed["risk_level"],
        evidences=evidences,
        total=len(evidences),
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
