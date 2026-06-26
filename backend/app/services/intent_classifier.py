"""
查询意图识别与风险等级判定

将患者口语化查询分类为意图类型和风险等级
"""

import re
from enum import Enum
from typing import Literal


class IntentType(str, Enum):
    DISEASE_UNDERSTANDING = "disease_understanding"
    TREATMENT_PROGRESS = "treatment_progress"
    DRUG_INFO = "drug_info"
    TEST_EXPLANATION = "test_explanation"
    CLINICAL_TRIAL = "clinical_trial"
    RUMOR_CHECK = "rumor_check"
    HIGH_RISK = "high_risk"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


# 高风险关键词规则
HIGH_RISK_KEYWORDS = [
    # 诊断类
    "我是不是得了", "是不是癌症", "是不是癌", "确诊了吗", "能治好吗",
    "还能活多久", "存活率", "预后怎么样",
    # 用药类
    "要不要停药", "能不能停药", "要不要换药", "能不能换药",
    "剂量", "用药量", "怎么服用", "一次吃多少",
    # 急症类
    "紧急", "急诊", "急救", "快死了", "疼死了",
    "呼吸困难", "咳血", "吐血", "昏迷",
    # 孕产类
    "怀孕", "孕妇", "哺乳期", "备孕",
    # 儿童
    "小孩", "宝宝", "婴儿", "新生儿",
]

MEDIUM_RISK_KEYWORDS = [
    "副作用", "不良反应", "并发症", "会不会",
    "推荐", "建议", "哪个更好", "选哪个",
    "疗效", "有效率", "治愈率",
]

PROHIBITED_KEYWORDS = [
    "帮我开", "给我开", "处方", "药方",
    "直接告诉我答案", "确诊",
]

# 意图关键词映射
INTENT_KEYWORDS = {
    IntentType.DISEASE_UNDERSTANDING: ["是什么", "什么意思", "怎么回事", "定义", "简介", "概述"],
    IntentType.TREATMENT_PROGRESS: ["最新进展", "研究进展", "新疗法", "新方案", "临床试验", "靶向", "免疫"],
    IntentType.DRUG_INFO: ["药物", "药品", "副作用", "不良反应", "耐药", "用法", "剂量"],
    IntentType.TEST_EXPLANATION: ["检查", "化验", "检测", "指标", "报告", "CT", "MRI", "PET"],
    IntentType.CLINICAL_TRIAL: ["招募", "试验", "临床研究", "入组"],
    IntentType.RUMOR_CHECK: ["真的吗", "是不是真的", "谣言", "听说", "传言", "能治", "饿死癌细胞"],
}


def classify_intent(query: str) -> IntentType:
    """基于关键词规则的意图分类"""
    query_lower = query.lower()

    scores = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        scores[intent] = score

    best_intent = max(scores, key=scores.get)
    if scores[best_intent] == 0:
        return IntentType.UNKNOWN
    return best_intent


def assess_risk_level(query: str, intent: IntentType) -> RiskLevel:
    """评估查询的风险等级"""
    query_lower = query.lower()

    # 先检查禁止级关键词
    for kw in PROHIBITED_KEYWORDS:
        if kw in query_lower:
            return RiskLevel.PROHIBITED

    # 检查高风险关键词
    for kw in HIGH_RISK_KEYWORDS:
        if kw in query_lower:
            return RiskLevel.HIGH

    # 基于意图判断
    if intent == IntentType.HIGH_RISK:
        return RiskLevel.HIGH

    # 检查中风险关键词
    for kw in MEDIUM_RISK_KEYWORDS:
        if kw in query_lower:
            return RiskLevel.MEDIUM

    return RiskLevel.LOW


def get_risk_message(risk_level: RiskLevel) -> str | None:
    """获取风险提示消息"""
    messages = {
        RiskLevel.LOW: None,
        RiskLevel.MEDIUM: "以下内容仅供参考，具体治疗方案请遵医嘱，如有疑问请咨询您的主治医生。",
        RiskLevel.HIGH: "您的提问涉及个体化诊疗决策，系统无法提供此类建议。请立即咨询您的主治医生或前往正规医疗机构就诊。",
        RiskLevel.PROHIBITED: "本系统仅提供医学文献的通俗化解释服务，不提供诊断、处方或个体化治疗建议。请咨询专业医生。",
    }
    return messages.get(risk_level)


def parse_query(query: str) -> dict:
    """
    完整查询解析

    Returns:
        {
            "original_query": str,
            "intent": IntentType,
            "risk_level": RiskLevel,
            "risk_message": str | None,
            "keywords": list[str],
        }
    """
    intent = classify_intent(query)
    risk_level = assess_risk_level(query, intent)
    risk_message = get_risk_message(risk_level)

    # 提取关键词（简单实现：去除停用词后的词列表）
    stopwords = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这", "那", "什么", "怎么", "吗", "啊", "呢", "吧"}
    keywords = [
        w.strip()
        for w in re.sub(r"[，。！？、；：\s]", " ", query).split()
        if w.strip() and w not in stopwords and len(w) > 1
    ]

    return {
        "original_query": query,
        "intent": intent.value,
        "risk_level": risk_level.value,
        "risk_message": risk_message,
        "keywords": keywords,
    }
