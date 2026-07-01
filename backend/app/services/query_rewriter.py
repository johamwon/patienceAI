"""
查询重写与优化

将患者自然语言查询转化为适合 KnowS AI 检索的优化查询：
  - 提取核心医学术语（中文）
  - 翻译为英文医学术语（用于 paper_en 端点）
  - 基于查询内容建议最佳检索源
"""

import json
import re
from typing import Optional
from ..services.llm_client import llm_client

# 用于匹配已知药物名的简单规则（作为 LLM 失败时的后备）
KNOWN_DRUG_PATTERNS = [
    "奥希替尼", "吉非替尼", "厄洛替尼", "阿法替尼", "达可替尼",
    "克唑替尼", "阿来替尼", "劳拉替尼", "卡博替尼",
    "帕博利珠单抗", "纳武利尤单抗", "阿替利珠单抗", "度伐利尤单抗",
    "贝伐珠单抗", "西妥昔单抗", "曲妥珠单抗",
    "奥拉帕利", "尼拉帕利", "卢卡帕利",
    "伊布替尼", "泽布替尼", "阿卡替尼",
    "索拉非尼", "仑伐替尼", "瑞戈非尼",
    "伊马替尼", "达沙替尼", "尼洛替尼",
    "来那度胺", "泊马度胺", "沙利度胺",
]

# 触发额外源选择的关键词规则
SOURCE_HINT_RULES = {
    "package_insert": KNOWN_DRUG_PATTERNS + ["说明书", "用法", "用量", "禁忌", "不良反应", "副作用", "服用", "注射"],
    "meeting": ["最新", "进展", "新药", "突破", "ASCO", "ESMO", "AACR", "2024", "2025"],
    "trial": ["临床试验", "招募", "入组", "试验", "NCT", "III期", "II期", "三期", "二期", "新药"],
    "guide": ["指南", "规范", "共识", "标准", "是什么", "诊断", "分期", "分型"],
}

REWRITE_SYSTEM_PROMPT = """你是医学文献检索查询优化助手。你的任务是从患者的自然语言查询中提取核心医学术语，用于医学文献数据库检索。

规则：
1. 提取核心医学概念（疾病名、药物名、治疗方法、检查项目等）
2. 去除口语化表达、情感词汇、个人化描述
3. 保持术语的专业性和准确性
4. 英文翻译使用标准医学英文术语（如 MeSH 词表中的术语）

请以 JSON 格式输出，不要输出其他内容：
{"medical_terms_cn": "中文医学关键词，空格分隔", "medical_terms_en": "English medical terms, space separated", "suggested_sources": ["建议的检索源列表"]}

可选的检索源：paper_en, paper_cn, guide, trial, meeting, package_insert"""

REWRITE_USER_TEMPLATE = "患者查询：{query}\n\n请提取核心医学术语并翻译为英文。"


class QueryRewriteResult:
    """查询重写结果"""

    def __init__(
        self,
        medical_terms_cn: str,
        medical_terms_en: str,
        suggested_sources: list[str],
        original_query: str,
    ):
        self.medical_terms_cn = medical_terms_cn
        self.medical_terms_en = medical_terms_en
        self.suggested_sources = suggested_sources
        self.original_query = original_query

    def get_query_for_source(self, source: str) -> str:
        """根据检索源返回对应的优化查询"""
        if source == "paper_en":
            # 英文端点使用英文术语
            return self.medical_terms_en if self.medical_terms_en else self.original_query
        else:
            # 中文端点使用中文术语
            return self.medical_terms_cn if self.medical_terms_cn else self.original_query


def rewrite_query(query: str) -> QueryRewriteResult:
    """
    使用 LLM 重写患者查询为医学检索术语

    Args:
        query: 患者原始自然语言查询

    Returns:
        QueryRewriteResult 包含中英文术语和建议源
    """
    try:
        messages = [
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": REWRITE_USER_TEMPLATE.format(query=query)},
        ]

        response = llm_client.chat(
            messages=messages,
            temperature=0.1,
            max_tokens=300,
        )

        parsed = _parse_rewrite_response(response)
        if parsed:
            cn_terms = parsed.get("medical_terms_cn", "").strip()
            en_terms = parsed.get("medical_terms_en", "").strip()
            if not cn_terms and not en_terms:
                return _fallback_rewrite(query)
            # 用规则补充 suggested_sources
            enhanced_sources = _enhance_sources_with_rules(query, parsed.get("suggested_sources", []))
            return QueryRewriteResult(
                medical_terms_cn=cn_terms,
                medical_terms_en=en_terms,
                suggested_sources=enhanced_sources,
                original_query=query,
            )
    except Exception as e:
        print(f"[WARN] Query rewrite failed, using fallback: {e}")

    # Fallback: 使用规则提取
    return _fallback_rewrite(query)


def _parse_rewrite_response(response: str) -> Optional[dict]:
    """解析 LLM 返回的 JSON 响应"""
    # 尝试直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 块
    json_match = re.search(r'\{[^{}]*"medical_terms_cn"[^{}]*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # 尝试提取 ```json ... ``` 块
    code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _enhance_sources_with_rules(query: str, llm_sources: list[str]) -> list[str]:
    """用规则补充 LLM 建议的检索源"""
    sources = set(llm_sources) if llm_sources else set()

    for source, keywords in SOURCE_HINT_RULES.items():
        for kw in keywords:
            if kw in query:
                sources.add(source)
                break

    # 确保至少有基础源
    if not sources:
        sources = {"paper_en", "paper_cn", "guide"}

    valid_sources = {"paper_en", "paper_cn", "guide", "trial", "meeting", "package_insert"}
    return [s for s in sources if s in valid_sources]


def _fallback_rewrite(query: str) -> QueryRewriteResult:
    """
    LLM 调用失败时的后备方案：基于规则提取关键词

    不做翻译（因为没有 LLM），直接返回原始查询
    """
    # 基于规则推断 sources
    sources = _enhance_sources_with_rules(query, [])

    # 简单清理：去除常见口语词
    stopwords = {"请问", "想问", "我想", "帮我", "能不能", "是不是", "有没有",
                 "告诉我", "了解一下", "想知道", "请教", "麻烦"}
    cleaned = query
    for sw in stopwords:
        cleaned = cleaned.replace(sw, "")
    cleaned = cleaned.strip()

    return QueryRewriteResult(
        medical_terms_cn=cleaned if cleaned else query,
        medical_terms_en="",  # 无 LLM 时不提供英文翻译
        suggested_sources=sources,
        original_query=query,
    )
