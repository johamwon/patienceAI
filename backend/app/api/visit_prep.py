"""
就医准备包 API 路由

提供 POST /visit-prep：基于患者查询 + 检索证据 + 情绪状态，
生成结构化的"医患沟通清单"（VisitPrepPack）。

缓存策略（R7.3/R7.4）：
- 复用全局 cache_service，但缓存键统一加 `visitprep::` 前缀，
  与 explain 结果隔离，避免互相覆盖。
- 命中且未过期则直接返回缓存的 VisitPrepResponse。
- 未命中则走完整检索 + 生成流程，结果写入缓存。

错误处理（R7.6）：
- 生成过程抛异常 → 返回 HTTP 500 描述性错误。
"""

import importlib
import traceback

from fastapi import APIRouter, HTTPException

from ..models.schemas import VisitPrepRequest, VisitPrepResponse, EmotionState
from ..services.llm_client import llm_client
from ..services.cache_service import cache_service
from ..services.intent_classifier import parse_query
from ..services.knows_client import knows_client

from agents.core.visit_prep_generator import generate_visit_prep
from agents.demo_scenarios import get_demo_scenario

router = APIRouter()

# 缓存命名空间前缀：与 explain 缓存隔离（R7.3/R7.4）
_CACHE_PREFIX = "visitprep::"

# 意图 → 检索源映射（参考 explain.py / search.py 的意图选源逻辑）
_INTENT_TO_SOURCES = {
    "disease_understanding": ["paper_en", "paper_cn", "guide"],
    "treatment_progress": ["paper_en", "paper_cn", "meeting", "guide"],
    "drug_info": ["paper_en", "paper_cn", "package_insert", "guide"],
    "test_explanation": ["guide", "paper_en"],
    "clinical_trial": ["trial", "paper_en"],
    "rumor_check": ["guide", "paper_cn"],
    "high_risk": ["guide", "paper_en"],
    "unknown": ["paper_en", "paper_cn", "guide"],
}
_DEFAULT_SOURCES = ["paper_en", "paper_cn", "guide"]


def _detect_emotion_safe(query: str) -> str:
    """情绪检测（容错）。

    emotion_detector 模块在本任务中可能尚未实现：
    - 若 `backend/app/services/emotion_detector.py` 存在并暴露 detect_emotion，
      则调用之（未来该模块出现时自动启用）。
    - 否则回退默认 "calm"，保证当前可运行。

    返回归一化的情绪字符串值。
    """
    try:
        module = importlib.import_module("..services.emotion_detector", __package__)
        detect_emotion = getattr(module, "detect_emotion", None)
        if callable(detect_emotion):
            emotion = detect_emotion(query, llm_client)
            # 兼容枚举（取 .value）或字符串
            return str(getattr(emotion, "value", emotion))
    except Exception as e:  # 模块缺失或调用失败均不阻塞主流程
        print(f"[INFO] emotion_detector 不可用，使用默认情绪 calm: {e}")
    return EmotionState.CALM.value


def _to_evidence_dicts(evidences) -> list[dict]:
    """将证据列表统一规整为 dict 列表。

    KnowS 返回的是 Evidence(pydantic) 对象，需经 model_dump() 转 dict；
    demo_scenarios 返回的已是 dict。generate_visit_prep 内部用 ev.get(...)，
    因此必须保证传入的是 dict。
    """
    result: list[dict] = []
    for ev in evidences or []:
        if isinstance(ev, dict):
            result.append(ev)
        elif hasattr(ev, "model_dump"):
            result.append(ev.model_dump())
    return result


@router.post("/visit-prep", response_model=VisitPrepResponse)
async def visit_prep(req: VisitPrepRequest):
    """
    生成就医准备包

    流程：
    1. 查缓存（visitprep:: 前缀），命中且未过期直接返回。
    2. 未命中：意图识别 → 检索证据（KnowS，失败/无结果回退 demo，仍无则空）。
    3. 情绪检测（emotion_detector 不存在时回退 calm）。
    4. 调用 generate_visit_prep 生成 pack。
    5. 组装 VisitPrepResponse（evidence_based + 无证据 note）。
    6. 写入缓存后返回。
    """
    cache_key = f"{_CACHE_PREFIX}{req.query}"

    try:
        # 1. 查缓存（R7.3）
        cached = cache_service.get(cache_key)
        if cached is not None:
            print(f"[Cache] visit-prep 缓存命中: {req.query[:30]}...")
            return VisitPrepResponse(**cached)

        print(f"[Cache] visit-prep 缓存未命中，开始生成: {req.query[:30]}...")

        # 2. 意图识别 + 检索证据（R7.1/R7.2）
        parsed = parse_query(req.query)
        sources = _INTENT_TO_SOURCES.get(parsed["intent"], _DEFAULT_SOURCES)

        try:
            evidences = knows_client.search_multi(
                req.query, sources, max_results_per_source=10
            )
        except Exception as e:
            print(f"[WARN] KnowS search failed: {e}")
            evidences = []

        # KnowS 失败 / 无结果 → 回退 demo 场景
        if not evidences:
            demo = get_demo_scenario(req.query)
            if demo:
                evidences = demo.get("evidences", [])
                if evidences:
                    print(f"[INFO] visit-prep 使用 demo 场景: {demo['id']}")

        evidence_dicts = _to_evidence_dicts(evidences)

        # 3. 情绪检测（容错）
        emotion = _detect_emotion_safe(req.query)

        # 4. 生成就医准备包（generate_visit_prep 为 async，需 await）
        pack = await generate_visit_prep(
            req.query, evidence_dicts, emotion, llm_client
        )

        # 5. 组装响应（R7.5）
        evidence_based = bool(evidence_dicts)
        note = None if evidence_based else "未找到针对性证据，以下为通用就医准备建议"
        resp = VisitPrepResponse(
            visit_prep_pack=pack,
            evidence_based=evidence_based,
            note=note,
        )

        # 6. 写入缓存（R7.4）
        cache_service.set(cache_key, resp.model_dump())
        print(f"[Cache] visit-prep 已缓存: {req.query[:30]}...")
        return resp

    except Exception as e:
        # 7. 生成失败 → 5xx 描述性错误（R7.6）
        print(f"[ERROR] visit_prep failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"就医准备包生成失败: {str(e)}")
