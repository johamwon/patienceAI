"""
研究阶段标注 + NCT 校验工具（R11.2, R12.1, R12.3, R12.4, R12.5）

把一条证据（evidence dict）映射到研究阶段标签 Research_Stage，并对
临床试验来源的 NCT 编号做格式与来源一致性校验。所有函数均为纯函数、
对缺失字段安全处理、不抛异常，便于单元测试（5.6）与 explain 编排（7.x）复用。
"""

import re
from enum import Enum
from typing import Optional


class ResearchStage(str, Enum):
    """研究阶段标签（R12.1，至少区分三类）"""
    BREAKTHROUGH_RCT = "breakthrough_rct"   # 突破性 RCT / 系统综述等高等级证据
    EARLY_TRIAL = "early_trial"             # 早期临床试验（I/II 期、first-in-human）
    PRECLINICAL = "preclinical"             # 动物实验 / 体外 / 临床前研究


# NCT 编号格式：NCT 后接 8 位数字
NCT_PATTERN = re.compile(r"^NCT\d{8}$")


# 早期临床试验信号词（标题/摘要，小写匹配）
_EARLY_TRIAL_KEYWORDS = [
    "phase i", "phase 1", "phase i/ii", "phase 1/2", "i/ii期", "i期", "ii期",
    "1期", "2期", "first-in-human", "first in human", "早期", "早期临床",
    "dose escalation", "dose-escalation", "剂量爬坡",
]

# 临床前 / 动物实验信号词（小写匹配）
_PRECLINICAL_KEYWORDS = [
    "小鼠", "大鼠", "动物", "动物模型", "细胞实验", "细胞系", "临床前",
    "in vitro", "in vivo", "preclinical", "pre-clinical", "mouse", "mice",
    "rat", "animal", "xenograft", "细胞株", "体外", "体内",
]

# 突破性 RCT / 高等级证据信号词（小写匹配）
_BREAKTHROUGH_KEYWORDS = [
    "phase iii", "phase 3", "iii期", "3期", "randomized controlled",
    "randomised controlled", "随机对照", "随机对照试验", "rct",
    "systematic review", "meta-analysis", "meta analysis", "荟萃分析",
    "系统综述", "系统评价", "meta分析",
]


def _text_blob(evidence: dict) -> str:
    """安全拼接标题与摘要并转小写，用于关键词匹配。"""
    if not isinstance(evidence, dict):
        return ""
    parts = []
    for key in ("title", "abstract"):
        val = evidence.get(key)
        if isinstance(val, str):
            parts.append(val)
    return " ".join(parts).lower()


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def infer_research_stage(evidence: dict) -> ResearchStage:
    """
    基于 source_type / evidence_level / 标题与摘要关键词推断研究阶段。

    判定优先级（保守，避免把临床前误判为突破性）：
    1. 临床前 / 动物实验信号 → PRECLINICAL
    2. 突破性 RCT / 系统综述信号，或（guide/系统综述来源且证据等级 high/moderate）
       → BREAKTHROUGH_RCT（先于早期判定，避免 "phase iii"/"iii期" 被
       "phase i"/"i期" 子串误命中为早期）
    3. 早期临床试验信号 → EARLY_TRIAL
    4. 无法判断 → 默认 EARLY_TRIAL（保守，附带不确定性提示，绝不默认突破性）

    对缺失字段安全处理，不抛异常。
    """
    if not isinstance(evidence, dict):
        return ResearchStage.EARLY_TRIAL

    text = _text_blob(evidence)
    source_type = (evidence.get("source_type") or "").lower() if isinstance(
        evidence.get("source_type"), str
    ) else ""
    evidence_level = (evidence.get("evidence_level") or "").lower() if isinstance(
        evidence.get("evidence_level"), str
    ) else ""

    # 1. 临床前优先（防止动物实验被高估）
    if _contains_any(text, _PRECLINICAL_KEYWORDS):
        return ResearchStage.PRECLINICAL

    # 2. 突破性 RCT / 高等级证据（先于早期，避免 "phase iii" 命中 "phase i" 子串）
    if _contains_any(text, _BREAKTHROUGH_KEYWORDS):
        return ResearchStage.BREAKTHROUGH_RCT
    if source_type == "guide" and evidence_level in ("high", "moderate"):
        return ResearchStage.BREAKTHROUGH_RCT

    # 3. 早期临床试验
    if _contains_any(text, _EARLY_TRIAL_KEYWORDS):
        return ResearchStage.EARLY_TRIAL

    # 4. 保守默认
    return ResearchStage.EARLY_TRIAL


def validate_nct(evidence: dict) -> bool:
    """
    校验 NCT 编号格式合法且与证据来源一致（R11.2）。

    返回 True 的条件：
    - evidence 为 dict 且含非空 nct_id，且匹配 NCT_PATTERN（NCT + 8 位数字）；
    - 来源类型与 nct 一致：source_type 缺失时仅看格式；存在时要求为 "trial"。

    缺失 / 格式错误 / 来源不一致 → False，不抛异常。
    """
    if not isinstance(evidence, dict):
        return False

    nct_id = evidence.get("nct_id")
    if not isinstance(nct_id, str) or not NCT_PATTERN.match(nct_id.strip()):
        return False

    source_type = evidence.get("source_type")
    # 来源类型存在时必须为 trial 才算一致；缺失时只要格式正确即认为可用
    if isinstance(source_type, str) and source_type.strip():
        if source_type.strip().lower() != "trial":
            return False

    return True


# 早期 / 临床前阶段的统一不确定性提示文本（R12.3 / R12.4）
_UNCERTAINTY_NOTE = "该结果尚未在患者身上证实有效，仍处于研究阶段，不代表对患者个体的确切获益。"


def build_uncertainty_note(stage: ResearchStage) -> Optional[str]:
    """
    为研究阶段生成不确定性提示（R12.3 / R12.4）。

    - EARLY_TRIAL / PRECLINICAL → 返回提示文本（早期/临床前必须标注尚未证实）
    - BREAKTHROUGH_RCT → 返回 None
    """
    if stage in (ResearchStage.EARLY_TRIAL, ResearchStage.PRECLINICAL):
        return _UNCERTAINTY_NOTE
    return None


def to_research_progress(evidence: dict) -> dict:
    """
    将一条 evidence 转换为 ResearchProgress dict，供 explain 编排（7.x）使用。

    产出字段对应 schemas.ResearchProgress：
        summary / research_stage / evidence_level / uncertainty_note / source_id

    对缺失字段安全处理，不抛异常。
    """
    safe = evidence if isinstance(evidence, dict) else {}

    stage = infer_research_stage(safe)

    # summary 优先取标题，其次摘要，最后兜底
    summary = safe.get("title") or safe.get("abstract") or "研究进展"
    if not isinstance(summary, str) or not summary.strip():
        summary = "研究进展"

    evidence_level = safe.get("evidence_level")
    if not isinstance(evidence_level, str) or not evidence_level.strip():
        evidence_level = "very_low"

    source_id = safe.get("id")
    if not isinstance(source_id, str) or not source_id.strip():
        source_id = None

    return {
        "summary": summary.strip(),
        "research_stage": stage.value,
        "evidence_level": evidence_level,
        "uncertainty_note": build_uncertainty_note(stage),
        "source_id": source_id,
    }
