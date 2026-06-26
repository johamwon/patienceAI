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

        # Step 1: 选择 Top 证据
        top_evidences = self._select_top_evidences(evidences, top_k=5)

        # Step 2: 合并证据文本
        evidence_text = self._merge_evidence_text(top_evidences)

        # Step 3: 运行 Simplification Loop（通俗化医学文本）
        simplified_text = await self._run_simplification_loop(evidence_text, original_query)

        # Step 4: 生成三层结构化回答
        result = await self._compose_three_layer_output(simplified_text, top_evidences, original_query)
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

    def _select_top_evidences(self, evidences: list[dict], top_k: int = 5) -> list[dict]:
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
            return (priority, -date_val)

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
        运行五位一体 Simplification Loop

        简化版流程（MVP 阶段合并部分步骤以减少 LLM 调用次数）：
        1. Layperson + Medical Expert → 术语注释（一次 LLM 调用）
        2. Simplifier → 通俗化改写（一次 LLM 调用）
        3. Language Clarifier + Redundancy Checker → 精简净化（一次 LLM 调用）
        4. 可读性检验 + 必要时重写
        """
        current_text = medical_text
        prev_text = ""

        for iteration in range(self.max_iterations):
            # ── Step 1+2: Layperson + Medical Expert (combined) ─────────────────
            annotations = await self._call_combined_layperson_expert(current_text)

            # ── Step 3: Simplifier ────────────────────────────────────────────
            simplified = await self._call_simplifier_agent(current_text, annotations)

            # ── Step 4+5: Language Clarifier + Redundancy Checker (combined) ───
            polished = await self._call_combined_clarifier_checker(simplified)
            t_i = polished

            # ── Step 6: 收敛判断 ────────────────────────────────────────────
            converged = await self._check_convergence(prev_text, t_i)
            if converged:
                break
            prev_text = t_i
            current_text = t_i

        # ── Step 7: 可读性检验 ──────────────────────────────────────────────
        final_text = await self._check_readability(t_i)
        return final_text

    async def _call_combined_layperson_expert(self, text: str) -> dict:
        """
        合并 Layperson + Medical Expert 为一个 LLM 调用
        返回术语注释列表
        """
        prompt = """\
You are a medical terminology assistant. Analyze the medical text below and identify complex terms, abbreviations, and statistical expressions that ordinary patients would find difficult to understand.

For each identified term, provide:
1. The term as it appears in the text
2. A plain-language explanation (max 20 Chinese characters)
3. A simple analogy if possible

Medical text:
{text}

Output JSON format:
{{
  "annotations": [
    {{"term": "OS", "plain": "总生存期，指从治疗开始到患者死亡的时间", "analogy": "可以理解为治疗后的存活时间"}},
    {{"term": "95% CI", "plain": "95%置信区间，表示真实值可能存在的范围", "analogy": "类似于"大概在XX到XX之间""}}
  ],
  "difficulty_score": 0.8
}}

Output ONLY valid JSON, no other text."""

        messages = [
            {"role": "system", "content": prompt.format(text=text[:3000])},
            {"role": "user", "content": "Please analyze the medical terms in the text above."},
        ]

        response = await asyncio.to_thread(self.llm.chat, messages, temperature=0.1, max_tokens=1000)

        # 尝试解析 JSON
        try:
            # 提取 JSON 部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except (json.JSONDecodeError, AttributeError):
            pass
        return {"annotations": [], "difficulty_score": 0.5}

    async def _call_simplifier_agent(self, text: str, annotations: dict) -> str:
        """Simplifier Agent：交叉注意力缝合，重塑文本"""
        annotations_str = json.dumps(annotations.get("annotations", []), ensure_ascii=False, indent=2)

        prompt = """\
You are a medical text simplifier. Rewrite the following medical text for ordinary patients.

Requirements:
1. Replace complex medical terms with plain language (use the annotations provided)
2. Break long sentences into short ones (max 20 words per sentence)
3. Use active voice
4. Keep all key medical facts and numbers
5. Use analogies to explain complex concepts
6. Target reading level: high school or below (FKGL <= 10)

Term annotations (term -> plain explanation):
{annotations}

Medical text to simplify:
{text}

Output the simplified text directly (no JSON, no markdown headers, just plain text)."""

        messages = [
            {"role": "system", "content": prompt.format(annotations=annotations_str, text=text[:4000])},
            {"role": "user", "content": "Please simplify the above medical text for patients."},
        ]

        return await asyncio.to_thread(self.llm.chat, messages, temperature=0.3, max_tokens=2000)

    async def _call_combined_clarifier_checker(self, text: str) -> str:
        """合并 Language Clarifier + Redundancy Checker 为一个 LLM 调用"""
        prompt = """\
You are a medical text editor. Polish the following patient-friendly medical text.

Requirements:
1. Replace remaining academic jargon with everyday words
2. Remove redundant phrases and repetitive content
3. Remove unnecessary modifiers and filler words
4. Keep sentences concise but complete
5. Ensure the text is easy to read and understand
6. Do NOT change any medical facts or numbers

Text to polish:
{text}

Output the polished text directly (no JSON, no markdown headers, just plain text)."""

        messages = [
            {"role": "system", "content": prompt.format(text=text[:4000])},
            {"role": "user", "content": "Please polish the above text."},
        ]

        return await asyncio.to_thread(self.llm.chat, messages, temperature=0.2, max_tokens=2000)

    async def _check_convergence(self, prev_text: str, curr_text: str) -> bool:
        """检查相邻迭代是否收敛"""
        if not prev_text or not curr_text:
            return False
        len_diff = abs(len(prev_text) - len(curr_text))
        max_len = max(len(prev_text), len(curr_text))
        if max_len == 0:
            return True
        normalized_diff = len_diff / max_len
        return normalized_diff < self.convergence_threshold

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

    async def _compose_three_layer_output(self, simplified_text: str, evidences: list[dict], query: str) -> dict:
        """
        生成三层结构化回答

        使用 LLM 将简化后的文本和证据合成为标准格式
        """
        # 构建证据摘要
        evidence_summary = "\n".join([
            f"- [{ev.get('source_type', 'unknown')}] {ev.get('title', '')[:100]} "
            f"(ID: {ev.get('pmid') or ev.get('doi') or ev.get('nct_id') or 'N/A'})"
            for ev in evidences[:5]
        ])

        prompt = """\
You are a medical information assistant for patients. Given the patient's query, retrieved evidence, and simplified explanation, compose a structured three-layer response.

Patient query: {query}

Retrieved evidence:
{evidence_summary}

Simplified explanation:
{simplified_text}

Output a JSON object with this exact structure:
{{
  "layer1_conclusion": {{
    "text": "One sentence conclusion (max 50 chars)",
    "citations": ["PMID1", "PMID2"]
  }},
  "layer2_evidence_cards": [
    {{
      "study_type": "RCT/系统综述/指南/...",
      "sample_size": "923 patients",
      "intervention": "Pembrolizumab + Chemotherapy",
      "comparator": "Chemotherapy alone",
      "outcome": "Median OS 22.0 vs 10.7 months",
      "limitations": "Limited Asian population",
      "evidence_level": "high",
      "source_id": "PMID: 32743622",
      "source_url": "https://pubmed.ncbi.nlm.nih.gov/32743622"
    }}
  ],
  "layer3_patient_explanation": {{
    "what_is_it": "Explain the disease/concept using an analogy",
    "what_evidence_says": "What the latest research found, in everyday language",
    "what_it_means_for_you": "2-3 actionable suggestions for the patient",
    "when_to_see_doctor": "Specific symptoms that require immediate medical attention",
    "disclaimer": "This content is a plain-language interpretation of medical literature for reference only. It does not constitute medical advice and does not replace a doctor's judgment."
  }}
}}

Output ONLY valid JSON, no other text."""

        messages = [
            {"role": "system", "content": prompt.format(
                query=query,
                evidence_summary=evidence_summary,
                simplified_text=simplified_text[:3000],
            )},
            {"role": "user", "content": "Please compose the structured three-layer response."},
        ]

        composed = await asyncio.to_thread(self.llm.chat, messages, temperature=0.3, max_tokens=3000)

        # 解析 JSON
        result = self._parse_three_layer_json(composed, evidences)
        return result

    def _parse_three_layer_json(self, composed_text: str, evidences: list[dict]) -> dict:
        """解析 LLM 输出的 JSON，带回退机制"""
        # 尝试直接解析
        try:
            data = json.loads(composed_text)
            if self._validate_output(data):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试提取 JSON 部分
        try:
            json_match = re.search(r'\{.*\}', composed_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if self._validate_output(data):
                    return data
        except (json.JSONDecodeError, AttributeError):
            pass

        # 回退：从证据构建结构化输出
        return self._fallback_output(evidences, composed_text)

    def _validate_output(self, data: dict) -> bool:
        """验证输出结构是否完整"""
        required = ["layer1_conclusion", "layer2_evidence_cards", "layer3_patient_explanation"]
        return all(key in data for key in required)

    def _fallback_output(self, evidences: list[dict], raw_text: str) -> dict:
        """LLM 输出解析失败时的回退方案"""
        # 从证据构建基本输出
        evidence_cards = []
        for ev in evidences[:5]:
            evidence_cards.append({
                "study_type": ev.get("source_type", "unknown"),
                "sample_size": None,
                "intervention": None,
                "comparator": None,
                "outcome": ev.get("abstract", "")[:100] if ev.get("abstract") else None,
                "limitations": None,
                "evidence_level": ev.get("evidence_level", "unknown"),
                "source_id": ev.get("pmid") or ev.get("doi") or ev.get("nct_id") or ev.get("id", ""),
                "source_url": ev.get("url"),
            })

        # 从原始文本提取第一句话作为结论
        first_sentence = raw_text.split(".")[0] + "." if raw_text else "请查看下方详细解释。"

        return {
            "layer1_conclusion": {
                "text": first_sentence[:200],
                "citations": [ev.get("pmid") for ev in evidences[:3] if ev.get("pmid")],
            },
            "layer2_evidence_cards": evidence_cards,
            "layer3_patient_explanation": {
                "what_is_it": raw_text[:500] if raw_text else "详见下方完整解释。",
                "what_evidence_says": raw_text[500:1000] if len(raw_text) > 500 else "详见下方完整解释。",
                "what_it_means_for_you": "请结合您的主治医生建议综合判断。",
                "when_to_see_doctor": "如出现症状加重或不适，请及时就医。",
                "disclaimer": "本内容为医学文献通俗化解释，仅供参考，不构成诊疗建议，不替代医生判断。",
            },
        }
