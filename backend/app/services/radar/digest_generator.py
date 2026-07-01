"""Push_Digest generation for Research Radar.

This module keeps patient-facing radar push content honest and bounded:
it summarizes population-level research progress, labels evidence stage,
adds uncertainty notes for early/preclinical work, and runs the global
compliance guard before anything is delivered.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from ...models.schemas import PushDigest, PushDigestItem
from ..research_stage import to_research_progress
from agents.prompts.persona import compliance_guard


def _evidence_to_dict(evidence: Any) -> dict:
    if isinstance(evidence, dict):
        return evidence
    if hasattr(evidence, "model_dump"):
        return evidence.model_dump()
    return dict(getattr(evidence, "__dict__", {}) or {})


def _source_id(evidence: dict) -> str | None:
    for key in ("id", "pmid", "doi", "nct_id"):
        value = evidence.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _fallback_summary(disease_keyword: str, evidence: dict) -> str:
    title = str(evidence.get("title") or "一项新的研究进展").strip()
    source = str(evidence.get("source_type") or "医学证据").strip()
    return (
        f"小光为你关注到 {disease_keyword} 相关的新进展：{title}。"
        f"它来自{source}，代表群体层面的研究信息，是否与你的情况相关需要和医生讨论。"
    )


async def _llm_summary(disease_keyword: str, evidence: dict, llm_client) -> str:
    if llm_client is None:
        return _fallback_summary(disease_keyword, evidence)

    title = evidence.get("title") or ""
    abstract = evidence.get("abstract") or ""
    source_type = evidence.get("source_type") or ""
    evidence_level = evidence.get("evidence_level") or "unknown"
    prompt = f"""\
请用中文为患者生成一段研究进展推送摘要，要求：
1. 只描述群体层面的研究进展，不给个体诊断、处方、剂量或治疗指令。
2. 保持克制、有希望但诚实，不夸大早期研究。
3. 80-140字，适合站内消息和邮件。

病症：{disease_keyword}
来源类型：{source_type}
证据等级：{evidence_level}
标题：{title}
摘要：{abstract[:1200]}
"""
    try:
        return await asyncio.to_thread(
            llm_client.chat,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
        )
    except Exception:
        return _fallback_summary(disease_keyword, evidence)


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned, _violations = compliance_guard(text)
    return cleaned


async def generate_push_digest(
    disease_keyword: str,
    new_evidences: list[Any],
    llm_client=None,
    *,
    is_demo: bool = False,
) -> PushDigest:
    """Generate a compliant PushDigest from fresh evidence items."""
    items: list[PushDigestItem] = []

    for raw in new_evidences:
        evidence = _evidence_to_dict(raw)
        progress = to_research_progress(evidence)
        summary = await _llm_summary(disease_keyword, evidence, llm_client)
        summary = _clean(summary) or _fallback_summary(disease_keyword, evidence)
        uncertainty_note = _clean(progress.get("uncertainty_note"))

        items.append(
            PushDigestItem(
                summary=summary,
                research_stage=progress["research_stage"],
                evidence_level=progress.get("evidence_level") or "very_low",
                uncertainty_note=uncertainty_note,
                source_id=progress.get("source_id") or _source_id(evidence),
            )
        )

    return PushDigest(
        disease_keyword=disease_keyword,
        items=items,
        generated_at=datetime.now().isoformat(),
        is_demo=is_demo,
    )
