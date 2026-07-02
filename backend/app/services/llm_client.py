"""
LLM 调用封装

统一管理 LLM 调用，支持 OpenAI 兼容接口
"""

import os
import re
import json
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

        message = choices[0].get("message", {}) or {}
        content = message.get("content") or ""
        # 兼容推理类模型：content 为空时回退 reasoning_content
        if not content.strip():
            content = message.get("reasoning_content") or ""

        return self._sanitize_content(content)

    @staticmethod
    def _sanitize_content(text: str) -> str:
        """清理模型输出的包裹标记，便于后续 JSON / 文本解析。

        - 剥离 StepFun 等模型常见的 \\boxed{...} 包裹。
        - 剥离 markdown 代码块围栏（```json ... ``` / ``` ... ```）。
        """
        if not text:
            return text
        s = text.strip()

        # 去除 ```json / ``` 代码块围栏
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
            if s.endswith("```"):
                s = s[: -3]
            s = s.strip()

        # 去除 \boxed{ ... } 包裹（取最外层大括号内的内容）
        boxed = re.search(r"\\boxed\{(.*)\}", s, re.DOTALL)
        if boxed:
            s = boxed.group(1).strip()

        return s

    def _mock_response(self, messages: list[dict], model: str) -> str:
        """Demo 模式：无 API Key 时返回模拟响应"""
        # 合并所有消息内容进行判断
        all_content = " ".join(m.get("content", "") for m in messages).lower()

        if "暖场白" in all_content or "小光" in all_content and "只输出" in all_content:
            return (
                "我知道你是想把这件事弄清楚，这种担心很正常。"
                "我会先把目前能找到的公开研究信息整理成容易理解的话，也会把不确定的地方说清楚，"
                "方便你之后和医生进一步核对。"
            )
        elif "three layer" in all_content or "三层" in all_content or "compose" in all_content:
            return json.dumps(
                {
                    "layer1_conclusion": {
                        "text": "这次检索到的资料提示，这个问题需要先分清疾病类型、检测指标和治疗阶段。公开研究能帮助你了解大方向，但不能直接判断某个人该用哪种方案；更稳妥的做法是把病理、基因检测和既往治疗资料带给主治医生一起确认。",
                        "citations": ["32743622", "35123456"],
                    },
                    "layer3_patient_explanation": {
                        "what_is_it": "可以把这些医学信息理解成医生做判断前会看的线索：疾病名称、检测结果、治疗阶段和既往用药，都会影响下一步讨论。",
                        "what_evidence_says": "目前公开研究通常是在特定人群中观察治疗或检测的价值，结论更适合用来了解方向，而不是直接套用到个人身上。",
                        "what_it_means_for_you": "你可以把关心的问题整理成清单，并带上病理报告、基因检测、影像检查和用药记录，与主治医生核对这些证据是否适用于你的情况。",
                        "when_to_see_doctor": "如果出现呼吸困难、咳血、持续高热、胸痛加重，或治疗期间出现严重皮疹、腹泻、气喘等情况，应及时就医。",
                        "disclaimer": "本内容为医学文献通俗化解释，仅供参考，不构成诊疗建议，不替代医生判断。",
                    },
                },
                ensure_ascii=False,
            )
        if "rewrite the following text to a high school reading level" in all_content:
            return (
                "免疫治疗是一种帮助身体免疫系统识别并攻击癌细胞的治疗方法。"
                "目前研究显示，它在部分肺癌患者中可能带来获益，但具体是否适合个人情况，"
                "需要结合病理、基因检测和医生评估。"
            )
        if "simplif" in all_content or "改写" in all_content or "simplifier" in all_content:
            return "免疫治疗是一种帮助身体免疫系统识别并攻击癌细胞的治疗方法。最新研究显示，将免疫治疗与化疗联合使用，比单独使用化疗效果更好。接受联合治疗的患者平均多存活约11个月。大约每10个患者中，有4-5个能从中获益。"
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
