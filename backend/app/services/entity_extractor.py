"""
医学实体提取器 — LLM 驱动的疾病/药物/生物标志物/治疗类型结构化提取。

用于研究雷达订阅：从用户自然语言查询中提取关键医学实体，
构建精准的 KnowS AI 检索查询词，替代原文扔进检索的粗放做法。
"""

from __future__ import annotations

import json
import re
from typing import Any


# ── LLM 提示词 ──────────────────────────────────────────────────────

_EXTRACT_SYSTEM_PROMPT = """\
你是一位医学信息提取助手。从患者查询中提取以下结构化医学实体。
只提取查询中明确提到的内容，不要推测或补充。

返回严格 JSON 格式（不要 markdown 代码块、不要额外解释）：
{
  "primary_disease": "最主要的疾病名（中文标准名），没有则为空字符串",
  "secondary_diseases": ["其他提到的疾病/并发症"],
  "drugs": ["提到的药物名称（通用名/商品名）"],
  "biomarkers": ["提到的生物标志物/基因突变/检测指标"],
  "treatment_types": ["提到的治疗方式（靶向治疗/化疗/免疫治疗/手术等）"],
  "search_queries": ["2-4 条用于医学文献检索的英文/中文查询短语"]
}

search_queries 规则：
- 每条 2-6 个词，应为对检索最有效的关键词组合
- 优先用英文医学术语（PubMed 兼容），也可包含中文关键词
- 涵盖不同维度：疾病+治疗、疾病+生物标志物、药物+疾病等
- 不要包含"最新""研究""进展"等检索噪声词"""


def _clean_json(raw: str) -> str:
    """清理 LLM 返回中可能夹带的 markdown 代码块标记。"""
    raw = raw.strip()
    # 去掉 ```json ... ``` 包裹
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    return raw.strip()


def _parse_entities(raw: str, query: str) -> dict[str, Any]:
    """安全解析 LLM 返回的 JSON，失败时返回降级结构。"""
    try:
        data = json.loads(_clean_json(raw))
    except (json.JSONDecodeError, TypeError):
        return _fallback_entities(query)

    return {
        "primary_disease": str(data.get("primary_disease") or "").strip(),
        "secondary_diseases": _ensure_str_list(data.get("secondary_diseases")),
        "drugs": _ensure_str_list(data.get("drugs")),
        "biomarkers": _ensure_str_list(data.get("biomarkers")),
        "treatment_types": _ensure_str_list(data.get("treatment_types")),
        "search_queries": _ensure_str_list(data.get("search_queries")),
    }


def _ensure_str_list(value: Any) -> list[str]:
    """安全转为字符串列表。"""
    if not value or not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if item and str(item).strip()]


def _fallback_entities(query: str) -> dict[str, Any]:
    """LLM 提取失败时的降级方案：至少保留原始关键词作为检索词。"""
    keyword = query.strip()[:80]
    return {
        "primary_disease": keyword,
        "secondary_diseases": [],
        "drugs": [],
        "biomarkers": [],
        "treatment_types": [],
        "search_queries": [keyword],
    }


def extract_medical_entities_sync(query: str, llm_client) -> dict[str, Any]:
    """同步提取医学实体（供异步环境和同步降级使用）。

    Args:
        query: 患者原始查询
        llm_client: LLM 客户端（需支持 .chat() 方法）

    Returns:
        {
            "primary_disease": str,
            "secondary_diseases": [str],
            "drugs": [str],
            "biomarkers": [str],
            "treatment_types": [str],
            "search_queries": [str],  # 可直接用于 KnowS AI 检索
        }
    """
    if llm_client is None:
        return _fallback_entities(query)

    user_prompt = f"患者查询：{query.strip()}"

    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=400,
        )
    except Exception:
        return _fallback_entities(query)

    if not raw or not raw.strip():
        return _fallback_entities(query)

    return _parse_entities(raw, query)


async def extract_medical_entities(query: str, llm_client) -> dict[str, Any]:
    """异步提取医学实体。

    同 extract_medical_entities_sync，但通过 asyncio.to_thread 包装同步 LLM 调用。
    """
    import asyncio

    if llm_client is None:
        return _fallback_entities(query)

    try:
        return await asyncio.to_thread(extract_medical_entities_sync, query, llm_client)
    except Exception:
        return _fallback_entities(query)


def build_search_queries(entities: dict[str, Any], fallback_keyword: str = "") -> list[tuple[str, str]]:
    """从实体构建 (source_type, query) 搜索对列表，用于 KnowS AI 多源检索。

    优先使用 LLM 生成的 search_queries，不足时用实体字段自动补充。
    """
    queries = list(entities.get("search_queries") or [])

    # 如果 LLM 没生成足够的检索词，自动从实体字段拼接
    if len(queries) < 2:
        primary = entities.get("primary_disease", "")
        drugs = entities.get("drugs", [])
        biomarkers = entities.get("biomarkers", [])
        treatments = entities.get("treatment_types", [])

        if primary:
            # 疾病 + 治疗方式
            for t in treatments[:2]:
                q = f"{primary} {t}"
                if q not in queries:
                    queries.append(q)
            # 疾病 + 生物标志物
            for b in biomarkers[:2]:
                q = f"{primary} {b}"
                if q not in queries:
                    queries.append(q)
            # 药物 + 疾病
            for d in drugs[:2]:
                q = f"{d} {primary}"
                if q not in queries:
                    queries.append(q)

    # 仍然没有足够的 query → 用 fallback
    if not queries and fallback_keyword:
        queries = [fallback_keyword]

    # 限制数量
    queries = queries[:6]

    # 每条 query 在 4 个来源上各搜一次
    SOURCES = ("trial", "meeting", "guide", "paper_en")
    pairs: list[tuple[str, str]] = []
    for source in SOURCES:
        for q in queries:
            pairs.append((source, q))

    return pairs


def get_display_keyword(entities: dict[str, Any], fallback: str = "") -> str:
    """从实体提取用于前端展示的关键词。

    优先: 主要疾病名
    其次: 疾病 + 治疗方式组合
    最后: fallback
    """
    primary = entities.get("primary_disease", "")
    if primary:
        treatments = entities.get("treatment_types", [])
        if treatments:
            return f"{primary} · {treatments[0]}"
        return primary

    return fallback.strip()[:30] if fallback else "未知主题"
