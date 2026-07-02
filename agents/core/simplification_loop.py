"""
五位一体 Simplification Loop 核心引擎

智能体协同流程：
  Layperson Agent → Medical Expert Agent → Simplifier Agent
      → Language Clarifier Agent → Redundancy Checker Agent
      → [编辑距离收敛判断] → 可读性检验 → 三层结构化输出

这是产品的核心创新点。
"""

import asyncio
import json
import re
from typing import Optional
from ..prompts.system_prompts import get_prompt
from backend.app.services.answer_alignment import analyze_query_focus, rerank_evidences_for_query


class SimplificationLoop:
    """
    多智能体通俗化翻译闭环

    输入：KnowS AI 返回的结构化医学证据列表
    输出：患者可读的三层结构化回答
    """

    def __init__(self, llm_client, max_iterations: int = 3, convergence_threshold: float = 0.05):
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold

    async def run(self, evidences: list[dict], original_query: str) -> dict:
        """
        运行完整的多智能体通俗化循环

        Args:
            evidences: KnowS AI 返回的证据列表
            original_query: 原始患者查询

        Returns:
            三层结构化回答
        """
        if not evidences:
            return self._empty_result(original_query)

        focus = analyze_query_focus(original_query)
        evidences = rerank_evidences_for_query(evidences, focus)

        # Step 1: 选择 Top 证据
        top_evidences = self._select_top_evidences(evidences, top_k=5, focus=focus)

        # Step 2: 合并证据文本
        evidence_text = self._merge_evidence_text(top_evidences)

        # Step 3: 运行 Simplification Loop（通俗化医学文本）
        simplified_text = await self._run_simplification_loop(evidence_text, original_query)

        # Step 4: 生成三层结构化回答
        result = await self._compose_three_layer_output(
            simplified_text, top_evidences, original_query
        )
        return result

    def _empty_result(self, query: str) -> dict:
        """无证据时的默认回答"""
        return {
            "layer1_conclusion": {
                "text": "未找到与您查询相关的权威医学证据，请尝试使用更具体的疾病名称或医学术语。",
                "citations": [],
            },
            "layer2_evidence_cards": [],
            "layer3_patient_explanation": {
                "what_is_it": "目前没有找到与您查询相关的权威医学文献。",
                "what_evidence_says": "建议您尝试使用更具体的疾病名称或医学术语进行查询，例如使用'肺腺癌'而不是'肺癌'。",
                "what_it_means_for_you": "如需了解特定疾病信息，请咨询您的主治医生或前往正规医疗机构。",
                "when_to_see_doctor": "如您有具体症状或健康问题，请及时就医。",
                "disclaimer": "本内容为医学文献通俗化解释，仅供参考，不构成诊疗建议，不替代医生判断。",
            },
        }

    def _select_top_evidences(
        self, evidences: list[dict], top_k: int = 5, focus=None
    ) -> list[dict]:
        """按来源优先级选择 Top 证据"""
        priority_map = {
            "package_insert": 1,
            "guide": 2,
            "meeting": 3,
            "trial": 4,
            "paper_en": 5,
            "paper_cn": 6,
            "unknown": 7,
        }

        def sort_key(e):
            relevance = 0
            if focus is not None:
                from backend.app.services.answer_alignment import score_evidence_relevance

                relevance = score_evidence_relevance(e, focus)
            priority = priority_map.get(e.get("source_type", "unknown"), 7)
            pub_date = e.get("publish_date") or ""
            # 将日期转换为可排序的数值
            if hasattr(pub_date, 'year'):
                date_val = pub_date.year * 10000 + pub_date.month * 100 + pub_date.day
            elif isinstance(pub_date, str):
                try:
                    parts = pub_date.split("-")
                    date_val = int(parts[0]) * 10000 + int(parts[1]) * 100 + int(parts[2])
                except (ValueError, IndexError):
                    date_val = 0
            else:
                date_val = 0
            return (-relevance, priority, -date_val)

        sorted_evidences = sorted(evidences, key=sort_key)
        return sorted_evidences[:top_k]

    def _merge_evidence_text(self, evidences: list[dict]) -> str:
        """将多条证据合并为一段文本"""
        parts = []
        for i, ev in enumerate(evidences, 1):
            title = ev.get("title", "")
            abstract = ev.get("abstract", "") or ""
            source = ev.get("source_type", "unknown")
            source_id = ev.get("pmid") or ev.get("doi") or ev.get("nct_id") or ""
            pub_date = str(ev.get("publish_date", ""))
            parts.append(
                f"[Evidence {i}] Source: {source} | ID: {source_id} | Date: {pub_date}\n"
                f"Title: {title}\n"
                f"Abstract: {abstract}\n"
            )
        return "\n".join(parts)

    async def _run_simplification_loop(self, medical_text: str, query: str) -> str:
        """
        运行通俗化改写（性能优化版：单次 LLM 调用 + 必要时一次可读性重写）。

        历史上这里是"五位一体"多轮循环（术语注释→简化→净化，最多 6 次 LLM 调用），
        但后续 composer 还会重组叙述，多轮迭代对最终质量提升有限却显著拖慢响应。
        现在合并为"一次通俗化改写"：用单个提示词让模型直接把医学证据文本通俗化
        （替换术语、短句、主动语态、保留数字事实、目标高中以下可读性）。

        LLM 调用次数：1 次通俗化改写 + 最多 1 次可读性重写（仅当 FKGL 明显超标）。
        对外行为不变：返回纯文本 simplified_text 供 composer 使用。
        """
        # ── Step 1: 一次性通俗化改写（合并原术语注释 + 简化 + 净化三步）──────────
        simplified = await self._call_popularize_agent(medical_text)

        # ── Step 2: 可读性检验，仅在明显超标时触发一次重写 ──────────────────────
        final_text = await self._check_readability(simplified)
        return final_text

    async def _call_popularize_agent(self, text: str) -> str:
        """单次 LLM 调用：把医学证据文本直接通俗化改写为患者可读文本。

        合并了原先的"术语注释 → 简化改写 → 语言净化"三步，避免多次串行 LLM 调用。
        """
        prompt = """\
You are a medical text simplifier for ordinary patients. Rewrite the medical evidence text below into plain, patient-friendly language in ONE pass.

Requirements:
1. Replace complex medical terms, abbreviations, and statistical expressions (e.g. OS, 95% CI, HR, p-value) with plain language; briefly explain them inline when first used.
2. Break long sentences into short ones (aim for <= 20 words per sentence).
3. Use active voice and everyday words; remove redundant phrases and filler.
4. Keep ALL key medical facts and numbers accurate — do not invent or drop data.
5. Use simple analogies to explain difficult concepts when helpful.
6. Target reading level: high school or below (FKGL <= 10).
7. Write in the same language as the patient-facing context (Chinese).

Medical evidence text:
{text}

Output the simplified plain text directly (no JSON, no markdown headers, just the text)."""

        messages = [
            {"role": "system", "content": prompt.format(text=text[:4000])},
            {"role": "user", "content": "Please rewrite the above medical text into plain language for patients."},
        ]

        return await asyncio.to_thread(self.llm.chat, messages, temperature=0.3, max_tokens=1200)

    async def _check_readability(self, text: str) -> str:
        """可读性检验，若 FKGL > 10 则触发重新润色"""
        try:
            from textstat import flesch_kincaid_grade
            fkgl = flesch_kincaid_grade(text)
        except Exception:
            fkgl = 12.0

        if fkgl > 10:
            prompt = """\
Rewrite the following text to a high school reading level or below (FKGL <= 10).

Requirements:
- Use simple words and short sentences
- Replace medical jargon with everyday language
- Keep all key facts and numbers
- Output only the rewritten text

Text:
{text}"""
            messages = [
                {"role": "system", "content": prompt.format(text=text[:3000])},
                {"role": "user", "content": "Rewrite this for a high school reading level."},
            ]
            return await asyncio.to_thread(self.llm.chat, messages, temperature=0.3, max_tokens=2000)

        return text

    #: source_type → 中文研究类型名，用于证据卡片 study_type 字段
    _SOURCE_TYPE_CN = {
        "package_insert": "药品说明书",
        "guide": "临床指南",
        "guideline": "临床指南",
        "meeting": "会议摘要",
        "trial": "临床试验",
        "paper_en": "英文文献",
        "paper_cn": "中文文献",
        "paper": "学术论文",
        "unknown": "未知来源",
    }

    def _build_evidence_cards(self, evidences: list[dict]) -> list[dict]:
        """从结构化证据数据直接组装 layer2 证据卡片（不经过 LLM）。

        证据卡片完全由代码从已结构化的 evidences 组装，避免让 LLM 重新输出
        大段 JSON 而被 max_tokens 截断。两处（解析成功 / fallback）复用本方法。
        """
        cards = []
        for ev in evidences[:5]:
            source_type = ev.get("source_type") or "unknown"
            study_type = self._SOURCE_TYPE_CN.get(source_type, source_type)
            abstract = ev.get("abstract") or ""
            cards.append({
                "study_type": study_type,
                "sample_size": None,
                "intervention": None,
                "comparator": None,
                "outcome": abstract[:100] if abstract else None,
                "limitations": None,
                "evidence_level": ev.get("evidence_level") or "unknown",
                "source_id": ev.get("pmid") or ev.get("doi") or ev.get("nct_id") or ev.get("id", ""),
                "source_url": ev.get("url"),
            })
        return cards

    async def _compose_three_layer_output(self, simplified_text: str, evidences: list[dict], query: str) -> dict:
        """
        生成三层结构化回答

        核心思路：LLM 只生成叙述性文本（layer1 结论 + layer3 患者解释），
        证据卡片（layer2）由代码从结构化证据直接组装。这样 composer 的 LLM
        输出体量很小，不易被 max_tokens 截断，从根本上避免"原始 JSON 被当正文显示"。
        """
        # 构建证据摘要（仅供 LLM 参考写叙述，不要求其输出卡片）
        evidence_summary = "\n".join([
            f"- [{ev.get('source_type', 'unknown')}] {ev.get('title', '')[:100]} "
            f"(ID: {ev.get('pmid') or ev.get('doi') or ev.get('nct_id') or 'N/A'})"
            for ev in evidences[:5]
        ])
        focus = analyze_query_focus(query)
        focus_context = focus.prompt_context()

        prompt = """\
You are a medical information assistant for patients. Given the patient's query, retrieved evidence, and simplified explanation, compose the NARRATIVE parts of a patient-facing response.

You ONLY write the narrative text (the core conclusion and the patient explanation). Do NOT output evidence cards — those are assembled separately by the system.

Patient query: {query}

Question focus extracted by the system:
{focus_context}

Retrieved evidence:
{evidence_summary}

Simplified explanation:
{simplified_text}

CRITICAL — layer1_conclusion.text is the patient's "core answer at a glance":
- It MUST directly and substantively ANSWER the patient's question, not be a vague slogan or empty placeholder.
- Synthesize "what it is" + "what to do about it" into a 2-4 sentence informative core answer (roughly 40-120 Chinese characters) that a patient can read once and walk away with the main takeaway.
- Ground it in the retrieved evidence and simplified explanation above; mention the key finding/direction concretely.
- If the question focus is latest_treatment, directly answer in this order: current mainstream evidence-based treatment direction, newer disease-modifying/clinical-trial direction if evidence supports it, main limitations/uncertainty, and what to ask the doctor. Do not answer only by listing document titles.
- If key patient context is missing, say what information would change the answer instead of pretending certainty.
- Stay compliant: do NOT diagnose the individual, do NOT give prescriptions or dosages, do NOT phrase population evidence as personal medical advice. Use everyday Chinese.
- Bad (reject): "建议咨询医生了解更多。" / "这是一个需要重视的问题。"
- Good (accept): "针对XX，目前主流的循证方向是A和B；研究显示A在……方面有获益。具体是否适合你，需要结合个人情况和医生讨论。"

Output a JSON object with EXACTLY these two top-level keys (no evidence cards):
{{
  "layer1_conclusion": {{
    "text": "2-4 sentence informative core answer that directly answers the question",
    "citations": ["PMID1", "PMID2"]
  }},
  "layer3_patient_explanation": {{
    "what_is_it": "Explain the disease/concept using an analogy",
    "what_evidence_says": "Directly summarize what the evidence says for the user's specific question, not just what documents were found",
    "what_it_means_for_you": "2-3 actionable, non-prescriptive discussion points for the patient/family to ask the doctor",
    "when_to_see_doctor": "Specific symptoms that require immediate medical attention",
    "disclaimer": "This content is a plain-language interpretation of medical literature for reference only. It does not constitute medical advice and does not replace a doctor's judgment."
  }}
}}

Output ONLY valid JSON, no other text."""

        messages = [
            {"role": "system", "content": prompt.format(
                query=query,
                focus_context=focus_context,
                evidence_summary=evidence_summary,
                simplified_text=simplified_text[:3000],
            )},
            {"role": "user", "content": "Please compose the narrative two-layer response (no evidence cards)."},
        ]

        composed = await asyncio.to_thread(self.llm.chat, messages, temperature=0.3, max_tokens=1500)

        # 解析 JSON（仅叙述部分）；layer2 由代码组装
        result = self._parse_three_layer_json(composed, evidences, simplified_text, query)
        return result

    def _parse_three_layer_json(
        self,
        composed_text: str,
        evidences: list[dict],
        simplified_text: str = "",
        query: str = "",
    ) -> dict:
        """解析 composer 返回的叙述 JSON（layer1 + layer3），带回退机制。

        解析成功 → 用代码组装的证据卡片补上 layer2，返回完整三层。
        解析失败 → fallback 使用纯文本 simplified_text（绝不灌入原始 composed JSON）。
        """
        data = None
        # 尝试直接解析
        try:
            parsed = json.loads(composed_text)
            if self._validate_narrative(parsed):
                data = parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试提取 JSON 部分
        if data is None:
            try:
                json_match = re.search(r'\{.*\}', composed_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if self._validate_narrative(parsed):
                        data = parsed
            except (json.JSONDecodeError, AttributeError):
                pass

        if data is None:
            # 解析失败：用纯文本 simplified_text 兜底，绝不使用 composed JSON 文本
            return self._fallback_output(evidences, simplified_text, query)

        # 解析成功：用代码组装证据卡片补上 layer2，并清洗叙述字段防脏数据
        data["layer2_evidence_cards"] = self._build_evidence_cards(evidences)
        self._sanitize_narrative_fields(data, evidences, simplified_text, query)
        return data

    def _validate_narrative(self, data: dict) -> bool:
        """验证 composer 叙述输出是否含 layer1_conclusion + layer3_patient_explanation。"""
        if not isinstance(data, dict):
            return False
        required = ["layer1_conclusion", "layer3_patient_explanation"]
        return all(key in data for key in required)

    @staticmethod
    def _looks_like_raw_json(text) -> bool:
        """判断某展示字段是否仍是 JSON 痕迹（脏数据）。"""
        if not isinstance(text, str):
            return False
        stripped = text.lstrip()
        return stripped.startswith("{") or '"layer1_conclusion"' in text

    def _sanitize_narrative_fields(
        self, data: dict, evidences: list[dict], simplified_text: str, query: str = ""
    ) -> None:
        """保险：若任一展示字段残留 JSON 痕迹，用 simplified_text 兜底替换。

        就地修改 data 的 layer1_conclusion.text 与 layer3 各叙述字段。
        """
        layer1 = data.get("layer1_conclusion")
        if isinstance(layer1, dict):
            if self._looks_like_raw_json(layer1.get("text")):
                layer1["text"] = self._compose_fallback_conclusion(evidences, simplified_text, query)
        else:
            data["layer1_conclusion"] = {
                "text": self._compose_fallback_conclusion(evidences, simplified_text, query),
                "citations": [],
            }

        layer3 = data.get("layer3_patient_explanation")
        if isinstance(layer3, dict):
            clean_text = (simplified_text or "").strip()
            for field in ("what_is_it", "what_evidence_says", "what_it_means_for_you", "when_to_see_doctor"):
                if self._looks_like_raw_json(layer3.get(field)):
                    layer3[field] = clean_text[:500] if clean_text else "详见下方完整解释。"

    def _compose_fallback_conclusion(self, evidences: list[dict], raw_text: str, query: str = "") -> str:
        """从简化文本/证据中提取一段有信息量的核心答案，而非只取第一句。

        优先用简化文本的前若干句拼出 2-4 句、约 40-160 字的核心答案；
        简化文本不足时，用 Top 证据标题兜底，保证结论非空且有内容。
        """
        focus = analyze_query_focus(query)
        if focus.intent == "latest_treatment":
            disease = focus.disease or "这个疾病"
            source_types = {str(ev.get("source_type") or "") for ev in evidences[:5]}
            directions = []
            if "guide" in source_types:
                directions.append("指南/专家共识中的规范治疗")
            if "trial" in source_types:
                directions.append("临床试验或新疗法研究")
            if "meeting" in source_types:
                directions.append("近期会议报道的新进展")
            if not directions:
                directions.append("已发表研究中的治疗证据")
            return (
                f"关于{disease}的最新治疗，当前证据更适合分成"
                f"{'、'.join(directions)}来看。是否适合患者，取决于疾病阶段、"
                "既往用药、合并疾病和医生评估；建议带着这些问题和专科医生讨论。"
            )[:220]

        # 1) 优先从简化/合成文本中提取前几句有意义内容
        text = (raw_text or "").strip()
        if text:
            # 按中英文句末标点切句，过滤过短的碎片
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[。！？.!?])\s*", text)
                if len(s.strip()) >= 6
            ]
            if sentences:
                conclusion = ""
                for s in sentences:
                    if len(conclusion) >= 120:
                        break
                    conclusion += s
                conclusion = conclusion.strip()
                if len(conclusion) >= 20:
                    return conclusion[:200]
                # 内容太短，继续走证据兜底，但保留已有片段作为前缀
                if conclusion:
                    text = conclusion

        # 2) 用 Top 证据标题拼出一句有指向性的核心答案
        titles = [
            (ev.get("title") or "").strip()
            for ev in evidences[:2]
            if (ev.get("title") or "").strip()
        ]
        if titles:
            joined = "；".join(t[:60] for t in titles)
            return (
                f"根据检索到的权威医学证据，与该问题相关的研究主要涉及：{joined}。"
                "具体是否适合你的情况，请结合个人病情与医生讨论。"
            )[:200]

        # 3) 实在没有可用内容时的中性兜底
        if text:
            return text[:200]
        return "已为你检索到相关医学证据，请查看下方证据卡片与通俗解释了解详情。"

    def _fallback_output(self, evidences: list[dict], simplified_text: str, query: str = "") -> dict:
        """LLM 叙述输出解析失败时的回退方案。

        关键：所有展示字段使用纯文本 simplified_text（由 loop 产出），
        绝不使用 composer 返回的原始 JSON 文本，从根源杜绝"原始 JSON 当正文显示"。
        """
        # 证据卡片由代码从结构化证据直接组装（与解析成功路径一致）
        evidence_cards = self._build_evidence_cards(evidences)

        # 从简化文本/证据中提取有意义的核心答案，而非只取第一句
        conclusion_text = self._compose_fallback_conclusion(evidences, simplified_text, query)

        clean_text = (simplified_text or "").strip()
        focus = analyze_query_focus(query)
        what_is_it = clean_text[:500] if clean_text else "详见下方完整解释。"
        what_evidence_says = (
            clean_text[500:1000] if len(clean_text) > 500 else "详见下方完整解释。"
        )
        what_it_means = "请结合您的主治医生建议综合判断。"
        if focus.intent == "latest_treatment":
            what_it_means = (
                "可以和医生重点确认：目前处于哪个阶段、现有治疗目标是什么、"
                "是否适合新药或临床试验，以及这些方案的风险和随访要求。"
            )

        return {
            "layer1_conclusion": {
                "text": conclusion_text,
                "citations": [ev.get("pmid") for ev in evidences[:3] if ev.get("pmid")],
            },
            "layer2_evidence_cards": evidence_cards,
            "layer3_patient_explanation": {
                "what_is_it": what_is_it,
                "what_evidence_says": what_evidence_says,
                "what_it_means_for_you": what_it_means,
                "when_to_see_doctor": "如出现症状加重或不适，请及时就医。",
                "disclaimer": "本内容为医学文献通俗化解释，仅供参考，不构成诊疗建议，不替代医生判断。",
            },
        }
