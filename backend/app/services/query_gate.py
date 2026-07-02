"""
QueryGate — 问题门禁

在意图识别和检索之前，对用户问题做"适不适合答"的分类判定。
规则层（零延迟，确定性高）+ LLM 层（覆盖模糊边界），返回六种结果之一。

设计原则：
- block 类直接拒绝，不进入后续检索/解释
- redirect 类不检索，但交给其他模块（陪伴/追问）
- pass 类正常走原有流程
"""

import re
import json
from enum import Enum
from typing import Optional
from .llm_client import LLMClient

# ─── 判决枚举 ─────────────────────────────────────────────────────────────────────────────

class GateStatus(str, Enum):
    PASS = "pass"
    BLOCK_DIAGNOSIS = "block_diagnosis"      # 求诊断/处方 → 温和拒绝
    BLOCK_EMERGENCY = "block_emergency"       # 急症/危机 → 强制就医引导
    BLOCK_OFF_TOPIC = "block_off_topic"       # 非医学问题 → 能力范围说明
    REDIRECT_COMPANION = "redirect_companion"  # 纯情绪表达 → 陪伴引擎
    REDIRECT_CLARIFY = "redirect_clarify"      # 信息不足 → 追问（现有流程）


# ─── 规则层关键词 ──────────────────────────────────────────────────────────────────────────

# 急症/危机关键词（硬阻止，必须就医）
EMERGENCY_KEYWORDS = [
    "呼吸困难", "咳血", "吐血", "昏迷", "休克", "抽搐",
    "自杀", "自残", "想死", "不想活", "活不下去了",
    "胸痛", "心梗", "中风", "脑梗", "大出血",
    "过敏休克", "喉头水肿", "窒息",
]

# 求诊断/开药关键词（硬阻止）
DIAGNOSIS_PRESCRIPTION_KEYWORDS = [
    "帮我开", "给我开", "开药", "开点药", "处方", "药方",
    "我是不是得了", "确诊", "是不是癌", "是不是癌症",
    "能治好吗", "还能活多久", "我这是",
    "帮我诊断", "给我诊断", "给我确诊", "帮我确诊",
]

# 非医学关键词（硬阻止）
# 分为强信号（1个命中即阻止）和弱信号（需2个同时命中）
STRONG_OFF_TOPIC_KEYWORDS = [
    "写代码", "编程", "帮我做网站", "帮我写作文",
    "推荐电影", "推荐音乐", "推荐歌", "推荐书",
    "菜谱", "做菜", "旅游攻略", "天气预报",
    "炒股推荐", "基金推荐", "股票推荐",
]

WEAK_OFF_TOPIC_KEYWORDS = [
    "python", "javascript", "react", "vue",
    "帮我画", "帮我设计", "帮我翻译",
    "今天是什么日子", "今天是几号", "现在几点",
]

# 纯情绪表达关键词（转介陪伴引擎，不含实质医学问题）
PURE_EMOTION_KEYWORDS = [
    "好害怕", "好担心", "好焦虑", "好绝望", "崩溃了",
    "我受不了", "我撑不住", "我不知道怎么办", "我害怕",
    "心里难受", "睡不着觉", "吃不下饭", "每天都想哭",
    "我很绝望", "我很害怕", "我很焦虑",
]


# ─── 用户可见的拒绝文案（品牌话术，非错误信息）─────────────────────────────────────────

GATE_USER_MESSAGES = {
    GateStatus.BLOCK_DIAGNOSIS: (
        "我无法判断你是否患了某种疾病。诊断是医生的专业工作，需要结合查体、影像和检验结果综合判断。"
        "我帮你整理了相关研究信息供参考，但最终判断请交给医生。"
    ),
    GateStatus.BLOCK_EMERGENCY: (
        "你描述的症状需要紧急处理，请不要等待。\n\n"
        "立刻行动：\n"
        "1. 拨打 120 或前往最近的急诊科\n"
        "2. 不要自行服药或等待观察\n"
        "3. 拨打 120 时告知你的症状和位置\n\n"
        "你的安全比任何事情都重要。"
    ),
    GateStatus.BLOCK_OFF_TOPIC: (
        "我是面向患者的循证医学助手，擅长解答以下类型的问题：\n\n"
        "• 看懂检查报告和指标\n"
        "• 理解疾病和治疗方案\n"
        "• 查询药物的作用和副作用\n"
        "• 求证网络流传的健康说法\n"
        "• 了解临床试验和研究进展\n\n"
        "请提出一个医学相关的问题，我会尽力帮你找到循证答案。"
    ),
    GateStatus.REDIRECT_COMPANION: (
        "我听到了你的担忧，这些感受是真实且重要的。陪你一起面对。"
    ),
}


# ─── 第 0 层：规则快速过滤 ──────────────────────────────────────────────────────────────────

def _rule_filter(query: str) -> Optional[GateStatus]:
    """
    基于关键词的确定性规则过滤。
    返回 None 表示规则无法确定，需进入 LLM 层。
    """
    q = query.lower()

    # 急症/危机 → 硬阻止
    for kw in EMERGENCY_KEYWORDS:
        if kw in q:
            return GateStatus.BLOCK_EMERGENCY

    # 求诊断/开药 → 硬阻止
    for kw in DIAGNOSIS_PRESCRIPTION_KEYWORDS:
        if kw in q:
            return GateStatus.BLOCK_DIAGNOSIS

    # 非医学 → 硬阻止（强信号 1 命中即阻止，弱信号需 2 个同时命中）
    strong_hits = sum(1 for kw in STRONG_OFF_TOPIC_KEYWORDS if kw in q)
    weak_hits = sum(1 for kw in WEAK_OFF_TOPIC_KEYWORDS if kw in q)
    if strong_hits >= 1 or (strong_hits + weak_hits) >= 2:
        return GateStatus.BLOCK_OFF_TOPIC

    # 纯情绪 → 转介陪伴（条件是：命中情绪词 且 不含实质医学问题）
    # 实质医学问题的简单检测：包含疾病名/检查/药物/治疗等关键词
    medical_signals = re.findall(
        r"癌|瘤|病|症|炎|药|治疗|检查|化验|报告|指标|CT|MRI|PET|手术|化疗|放疗|靶向|免疫|基因|突变",
        q,
    )
    emotion_signals = sum(1 for kw in PURE_EMOTION_KEYWORDS if kw in q)
    if emotion_signals >= 1 and not medical_signals:
        return GateStatus.REDIRECT_COMPANION

    return None


# ─── 第 1 层：LLM 模糊边界判断 ──────────────────────────────────────────────────────────────────

_LLM_GATE_PROMPT = """\
你是一个医学助手的问题门禁分类器。判断用户输入是否可以由循证医学助手来回答。

输入：
{query}

分类选项（只输出一个）：
- pass：属于可以回答的循证医学问题（疾病理解、治疗进展、药物信息、检查解释、临床试验、谣言求证等）
- block_diagnosis：在求个体化诊断或处方（如"我这个肿块是不是癌""给我开XX药"）
- block_emergency：描述急症或危机（如"我现在呼吸困难""我想死"）
- block_off_topic：完全不是医学问题
- redirect_companion：纯情绪表达，没有实质医学问题

判断原则：
- 如果用户问了医学问题但表达了焦虑/担忧 → pass（可以回答，陪伴由后续引擎处理）
- "我查出来XX指标高了，怎么办" 是 pass
- "我好害怕" 单独出现 → redirect_companion
- 只有明确求诊断/处方/急症的才 block
- 宁错放不过杀：不确定时输出 pass

只输出上述五个单词之一，不要任何额外文字。"""


def _llm_classify(query: str, llm: LLMClient) -> GateStatus:
    """用轻量 LLM 调用做模糊边界分类。LLM 失败时安全回退到 pass。"""
    try:
        prompt = _LLM_GATE_PROMPT.format(query=query)
        raw = llm.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30,
            temperature=0.0,
        )
        raw = raw.strip().lower()

        # 直接映射
        valid = {s.value for s in GateStatus}
        # 只取第一个匹配的有效状态词
        for word in raw.split():
            if word in valid:
                return GateStatus(word)

        # 模糊匹配：block 类优先
        if "block" in raw and "emergency" in raw:
            return GateStatus.BLOCK_EMERGENCY
        if "block" in raw and ("diagnos" in raw or "presc" in raw):
            return GateStatus.BLOCK_DIAGNOSIS
        if "block" in raw:
            return GateStatus.BLOCK_OFF_TOPIC
        if "redirect" in raw or "companion" in raw:
            return GateStatus.REDIRECT_COMPANION

        return GateStatus.PASS

    except Exception:
        # LLM 调用失败时安全放行（不因门禁故障阻断有效查询）
        return GateStatus.PASS


# ─── 统一入口 ──────────────────────────────────────────────────────────────────────────────

_llm_client: Optional[LLMClient] = None


def _get_llm() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def classify_query_gate(query: str) -> dict:
    """
    问题门禁主入口。

    Returns:
        {
            "status": str,       # pass / block_diagnosis / block_emergency / block_off_topic / redirect_companion / redirect_clarify
            "user_message": str, # 展示给用户的品牌话术
            "companion_trigger": bool,
        }

    策略：
    1. 规则层（第 0 层）→ 命中的直接返回
    2. 规则未命中 → LLM 层（第 1 层）模糊分类
    3. 所有 block 非 pass 的结果都附带品牌话术
    """
    if not query or not isinstance(query, str):
        return _gate_result(GateStatus.PASS)

    # 第 0 层：规则快速过滤
    rule_result = _rule_filter(query)
    if rule_result is not None:
        return _gate_result(rule_result)

    # 第 1 层：LLM 模糊分类
    llm_result = _llm_classify(query, _get_llm())
    return _gate_result(llm_result)


def _gate_result(status: GateStatus) -> dict:
    """将 GateStatus 组装为标准返回格式。"""
    companion_trigger = status == GateStatus.REDIRECT_COMPANION
    return {
        "status": status.value,
        "user_message": GATE_USER_MESSAGES.get(status, ""),
        "companion_trigger": companion_trigger,
    }
