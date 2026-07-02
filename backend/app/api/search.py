"""
搜索 API 路由

提供 KnowS AI 多源检索接口
支持查询重写：将患者自然语言转为优化医学术语
"""

from typing import Any
import re

from fastapi import APIRouter, HTTPException
from ..models.schemas import SearchRequest, SearchResponse, Evidence
from ..services.answer_alignment import (
    analyze_query_focus,
    build_query_with_clarifications,
    is_latest_focused_query,
    rerank_evidences_for_query,
)
from ..services.knows_client import knows_client
from ..services.intent_classifier import parse_query
from ..services.query_rewriter import rewrite_query

router = APIRouter()

# 默认检索源集合（意图未知 / 回退时使用）
DEFAULT_SOURCES = ["paper_en", "paper_cn", "guide"]

# 罕见病/重症专门检索源：优先前沿源 + 至少一类 guide 交叉佐证（R10.1 / R10.3）
RARE_SEVERE_SOURCES = ["trial", "meeting", "paper_en", "guide"]

# “最新研究/最新治疗”需要优先看近期会议、临床试验、指南更新和近年论文。
LATEST_RESEARCH_SOURCES = ["meeting", "trial", "guide", "paper_en", "paper_cn"]

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


def select_sources(parsed: dict, focus=None) -> list[str]:
    """
    根据查询解析结果选择检索源（纯函数，便于单测）。

    - R10.1 / R10.3：当 rare_disease 或 severe_condition 为 True 时，
      优先返回前沿源 trial + meeting + paper_en，并保留 guide 用于交叉佐证。
    - 否则按 intent 从 INTENT_TO_SOURCES 选源，未知意图回退 DEFAULT_SOURCES。
    """
    if focus is not None and is_latest_focused_query(focus):
        return list(LATEST_RESEARCH_SOURCES)
    if parsed.get("rare_disease") or parsed.get("severe_condition"):
        return list(RARE_SEVERE_SOURCES)
    return INTENT_TO_SOURCES.get(parsed.get("intent"), DEFAULT_SOURCES)


def _publish_date_sort_key(evidence: Any) -> tuple[int, int, int, int]:
    """
    从 Evidence 对象或 dict 中稳健提取 publish_date 的可比较排序键。

    返回 (has_date, year, month, day)：
    - has_date=1 表示存在可解析日期，0 表示缺失/无法解析（排在最后）。
    - publish_date 可能是 datetime.date、ISO 字符串（如 "2024-01-15" / "2024"）或 None。
    """
    if isinstance(evidence, dict):
        pub = evidence.get("publish_date")
    else:
        pub = getattr(evidence, "publish_date", None)

    if pub is None:
        return (0, 0, 0, 0)

    # date / datetime 对象
    year = getattr(pub, "year", None)
    if year is not None:
        return (1, year, getattr(pub, "month", 0) or 0, getattr(pub, "day", 0) or 0)

    # 字符串日期（容忍仅年份或 年-月-日 等格式）
    if isinstance(pub, str):
        text = pub.strip()
        if not text:
            return (0, 0, 0, 0)
        parts = re.split(r"[-/.]", text)
        try:
            y = int(parts[0])
        except (ValueError, IndexError):
            return (0, 0, 0, 0)
        m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        d = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        return (1, y, m, d)

    return (0, 0, 0, 0)


def sort_evidences(evidences: list, parsed: dict, focus=None) -> list:
    """
    根据查询解析结果排序证据（纯函数，便于单测）。

    - R10.2：当 rare_disease 或 severe_condition 为 True 时，按 publish_date 降序
      （最新发表在前），缺失/无法解析日期的证据排在最后。
    - 否则保留现有顺序（来源优先级排序）。

    稳健处理：evidences 元素可能是 Evidence pydantic 对象或 dict，
    publish_date 可能是 date / 字符串 / None。
    """
    if not evidences:
        return evidences
    if focus is not None and is_latest_focused_query(focus):
        normalized = [ev if isinstance(ev, dict) else ev.model_dump() for ev in evidences]
        return rerank_evidences_for_query(normalized, focus)
    if parsed.get("rare_disease") or parsed.get("severe_condition"):
        # 稳定排序：has_date=0（缺失）的排序键最小，reverse 后落到末尾
        return sorted(evidences, key=_publish_date_sort_key, reverse=True)
    return evidences


def _run_search(sources: list[str], rewrite_result, max_results: int) -> list[Evidence]:
    """按源并行检索并去重（每个源使用对应语言的优化查询）。

    用 knows_client.search_multi_queries 并行发起多源检索，总耗时 ≈ 最慢的单源；
    单源异常不影响其他源；结果按 sources 顺序稳定合并去重。
    """
    max_per_source = max_results // max(len(sources), 1) + 1
    source_query_pairs = [
        (source, rewrite_result.get_query_for_source(source)) for source in sources
    ]
    return knows_client.search_multi_queries(
        source_query_pairs, max_results_per_source=max_per_source
    )


@router.post("/search", response_model=SearchResponse)
async def search_evidence(req: SearchRequest):
    """
    检索医学证据

    - 自动识别查询意图（含罕见病/重症标记）
    - LLM 重写查询：提取医学术语 + 英文翻译
    - 智能源选择：罕见病/重症优先前沿源；否则结合意图分类与查询重写建议
    - 罕见病/重症结果按发表时间降序；专门源无结果时回退默认源
    - 返回结构化证据列表
    """
    # 1. 意图识别（含 rare_disease / severe_condition 标记）
    effective_query = build_query_with_clarifications(req.query, req.clarification_answers)
    focus = analyze_query_focus(effective_query)
    parsed = parse_query(effective_query)
    is_rare_severe = bool(parsed.get("rare_disease") or parsed.get("severe_condition"))

    # 2. 查询重写：提取医学术语 + 英文翻译
    rewrite_result = rewrite_query(effective_query)
    print(f"[QueryRewrite] CN: '{rewrite_result.medical_terms_cn}' | EN: '{rewrite_result.medical_terms_en}'")

    # 3. 智能源选择
    #    用户显式指定 > 罕见病/重症专门源（R9.5/R10.1/R10.3）> 意图映射 + 重写建议融合
    if req.sources:
        sources = req.sources
    elif is_latest_focused_query(focus):
        sources = select_sources(parsed, focus)
    elif is_rare_severe:
        sources = select_sources(parsed, focus)
    else:
        intent_sources = INTENT_TO_SOURCES.get(parsed["intent"], list(DEFAULT_SOURCES))
        rewrite_sources = rewrite_result.suggested_sources
        # 以意图映射为基础，补充重写建议的源（去重）
        sources = list(dict.fromkeys(intent_sources + rewrite_sources))

    # 4. 按源类型使用对应语言的优化查询调用 KnowS AI
    try:
        evidences = _run_search(sources, rewrite_result, req.max_results)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KnowS AI 检索失败: {str(e)}")

    # 4b. R10.4：罕见病/重症专门源无结果时，回退默认源集合再检索一次
    if not evidences and not req.sources and is_rare_severe and sources != DEFAULT_SOURCES:
        try:
            evidences = _run_search(DEFAULT_SOURCES, rewrite_result, req.max_results)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"KnowS AI 检索失败: {str(e)}")

    # 4c. 排序：罕见病/重症时按发表时间降序（R10.2），否则保留现有顺序
    evidences = sort_evidences(evidences, parsed, focus)

    # 5. 构造响应
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
