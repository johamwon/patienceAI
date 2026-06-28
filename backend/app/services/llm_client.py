"""
LLM 调用封装

统一管理 LLM 调用，支持 OpenAI 兼容接口
"""

import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Optional

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")


class LLMClient:
    """OpenAI 兼容接口的 LLM 调用客户端"""

    def __init__(
        self,
        base_url: str = LLM_BASE_URL,
        api_key: str = LLM_API_KEY,
        model: str = LLM_MODEL,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = httpx.Client(timeout=60.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        response_format: Optional[dict] = None,
        enable_thinking: bool = False,
    ) -> str:
        """
        调用 Chat Completions 接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称（默认使用环境变量配置）
            temperature: 生成温度
            max_tokens: 最大生成 token 数
            response_format: 响应格式约束（如 JSON Schema）
            enable_thinking: 是否启用 Qwen3 思考模式（默认关闭以降低延迟）

        Returns:
            模型输出的文本内容
        """
        model = model or self.model

        # Demo mode: 无 API Key 或使用占位符时返回模拟响应
        if not self.api_key or self.api_key in ("your-siliconflow-api-key-here", "sk-xxx", "xxx"):
            return self._mock_response(messages, model)

        # 对 Qwen3 模型，默认禁用 thinking 以降低延迟
        if not enable_thinking and "qwen3" in (model or "").lower():
            # 在最后一条 user 消息前加上 /no_think 标记
            messages = [m.copy() for m in messages]
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    messages[i]["content"] = "/no_think\n" + messages[i]["content"]
                    break

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        resp = self._client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("LLM returned empty choices")

        return choices[0]["message"]["content"]

    def _mock_response(self, messages: list[dict], model: str) -> str:
        """Demo 模式：无 API Key 时返回模拟响应"""
        # 合并所有消息内容进行判断
        all_content = " ".join(m.get("content", "") for m in messages).lower()
        
        if "simplif" in all_content or "改写" in all_content or "simplifier" in all_content:
            return "免疫治疗是一种帮助身体免疫系统识别并攻击癌细胞的治疗方法。最新研究显示，将免疫治疗与化疗联合使用，比单独使用化疗效果更好。接受联合治疗的患者平均多存活约11个月。大约每10个患者中，有4-5个能从中获益。"
        elif "three layer" in all_content or "三层" in all_content or "compose" in all_content:
            return '{"layer1_conclusion": {"text": "免疫治疗联合化疗已成为晚期肺腺癌的标准一线方案之一，约45%患者获益", "citations": ["32743622", "35123456"]}, "layer2_evidence_cards": [{"study_type": "RCT", "sample_size": "923名晚期NSCLC患者", "intervention": "帕博利珠单抗+化疗", "comparator": "单纯化疗", "outcome": "中位OS 22.0 vs 10.7个月", "limitations": "亚洲人群占比有限", "evidence_level": "high", "source_id": "PMID: 32743622", "source_url": "https://pubmed.ncbi.nlm.nih.gov/32743622"}, {"study_type": "系统综述", "sample_size": "纳入12项RCT，共5,847名患者", "intervention": "免疫联合化疗", "comparator": "单纯化疗", "outcome": "降低死亡风险约21%", "limitations": "异质性中等", "evidence_level": "high", "source_id": "PMID: 35123456", "source_url": "https://pubmed.ncbi.nlm.nih.gov/35123456"}], "layer3_patient_explanation": {"what_is_it": "免疫治疗就像给身体的"保安队"（免疫系统）装上了"望远镜"，让它们能重新发现并攻击癌细胞。癌细胞会穿上一件叫PD-L1的"隐形衣"躲避免疫系统，免疫治疗就是帮保安队脱掉这件隐形衣。", "what_evidence_says": "最新大型研究显示，把免疫治疗和化疗一起用，比单独化疗效果好得多——患者平均多活了约11个月。大约每10个患者中，有4-5个能从中获益。", "what_it_means_for_you": "1. 不是所有人都适合免疫治疗，需要先做PD-L1表达检测；2. 如果检测结果较高，免疫治疗可能对你更有效；3. 具体是否适合，一定要和主治医生详细讨论。", "when_to_see_doctor": "如出现呼吸困难、咳血、持续高热，或接受免疫治疗期间出现严重皮疹、腹泻、气喘，请立即就医。", "disclaimer": "本内容为医学文献通俗化解释，仅供参考，不构成诊疗建议，不替代医生判断。"}}'
        elif "查询优化" in all_content or "medical_terms_cn" in all_content or "检索查询优化" in all_content:
            # Query rewrite mock response
            import re as _re
            # 从用户消息中提取查询
            user_msg = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
            query_match = _re.search(r"患者查询[：:]\s*(.+?)(?:\n|$)", user_msg)
            raw_query = query_match.group(1).strip() if query_match else user_msg
            return f'{{"medical_terms_cn": "{raw_query}", "medical_terms_en": "lung adenocarcinoma immunotherapy", "suggested_sources": ["paper_en", "paper_cn", "guide"]}}'
        elif "polish" in all_content or "净化" in all_content or "精简" in all_content or "clarifier" in all_content or "redundancy" in all_content:
            text = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
            return text[:500] if text else "免疫治疗联合化疗已成为晚期肺腺癌的标准一线方案。"
        elif "analyze" in all_content or "分析" in all_content or "术语" in all_content or "annot" in all_content or "layperson" in all_content or "medical_expert" in all_content:
            return '{"annotations": [{"term": "OS", "plain": "总生存期，从治疗开始到患者死亡的时间", "analogy": "治疗后的存活时间"}, {"term": "95% CI", "plain": "95%置信区间", "analogy": "真实值可能的范围"}, {"term": "p<0.001", "plain": "统计学显著性", "analogy": "结果不太可能是巧合"}], "difficulty_score": 0.7}'
        else:
            last_msg = messages[-1].get("content", "") if messages else ""
            return last_msg[:500] + "\n\n[模拟响应] 请配置 LLM_API_KEY 以获取真实模型输出。"

    def close(self):
        self._client.close()


# ─── 全局单例 ───────────────────────────────────────────────────────────────

llm_client = LLMClient()
