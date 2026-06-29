"""
任务 5.6：infer_research_stage 与 validate_nct 单元测试

从需求方（甲方）视角验收以下验收标准：
- R12.1: 每条研究进展标注 Research_Stage，至少区分
         "突破性 RCT 证据 / 早期临床试验 / 动物实验·临床前研究" 三类。
- R12.3: 早期临床试验 / 动物实验阶段须显式说明结果尚未证实对患者个体有效；
         突破性 RCT 不附该不确定性提示。
- R11.2: 渲染 Trial_Card 前校验 NCT 编号与来源证据一致，校验不通过不渲染。

本文件只验证现有实现行为，发现缺陷如实报告，不修改实现迁就测试。
"""

import pytest

from backend.app.services.research_stage import (
    ResearchStage,
    infer_research_stage,
    validate_nct,
    build_uncertainty_note,
)


# ─────────────────────────────────────────────────────────────────────────────
# R12.1 infer_research_stage —— 早期临床试验 EARLY_TRIAL
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        {"title": "A Phase I study of drug X in solid tumors"},
        {"title": "phase 1 first-in-human trial"},
        {"title": "某新药 I期 临床研究"},
        {"abstract": "本研究为一项 first-in-human 剂量爬坡试验"},
        {"abstract": "dose escalation study of compound Y"},
        {"title": "II期临床试验结果", "abstract": "本试验招募晚期患者"},
        {"title": "新型疗法的早期临床探索"},
    ],
)
def test_infer_early_trial(evidence):
    assert infer_research_stage(evidence) is ResearchStage.EARLY_TRIAL, (
        f"应判定为早期临床试验: {evidence!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# R12.1 infer_research_stage —— 动物实验 / 临床前 PRECLINICAL
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        {"title": "小鼠模型中候选药物的抗肿瘤作用"},
        {"abstract": "in vitro experiments showed inhibition of growth"},
        {"title": "Antitumor activity in an animal model"},
        {"title": "临床前研究：化合物 Z 的药代动力学"},
        {"abstract": "实验在大鼠体内进行"},
        {"title": "Xenograft mouse study of agent A"},
        {"abstract": "体外细胞实验提示该通路被抑制"},
    ],
)
def test_infer_preclinical(evidence):
    assert infer_research_stage(evidence) is ResearchStage.PRECLINICAL, (
        f"应判定为动物实验/临床前: {evidence!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# R12.1 infer_research_stage —— 突破性 RCT / 高等级证据 BREAKTHROUGH_RCT
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        {"title": "A Phase III randomized controlled trial of drug X"},
        {"title": "randomized controlled trial of therapy B"},
        {"abstract": "本系统综述纳入 30 项随机对照试验"},
        {"title": "Meta-analysis of immunotherapy outcomes"},
        {"title": "某疗法的系统评价与荟萃分析"},
        {"title": "III期 关键性临床试验达到主要终点"},
        {"title": "An RCT comparing A versus B"},
        # 来源为指南 + 高/中等级证据 → 突破性（不依赖关键词）
        {"title": "临床实践指南", "source_type": "guide", "evidence_level": "high"},
        {"title": "权威综述", "source_type": "guide", "evidence_level": "moderate"},
    ],
)
def test_infer_breakthrough_rct(evidence):
    assert infer_research_stage(evidence) is ResearchStage.BREAKTHROUGH_RCT, (
        f"应判定为突破性 RCT: {evidence!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# R12.1 关键优先级边界：含 "phase III" 不能因子串 "phase i" 被误判为 EARLY_TRIAL
#   这是研究阶段标注正确性的核心——误判会把突破性证据降级，或反之误导患者。
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        {"title": "Phase III trial"},                          # 含 "phase i" 子串
        {"title": "phase iii randomized controlled trial"},
        {"title": "一项 III期 随机对照试验"},                    # 含 "i期" 子串语义
        {"abstract": "This phase III study enrolled 500 patients"},
    ],
)
def test_phase_iii_not_misjudged_as_early(evidence):
    stage = infer_research_stage(evidence)
    assert stage is ResearchStage.BREAKTHROUGH_RCT, (
        f"含 phase III 必须判为突破性 RCT，不得因子串误判为早期: {evidence!r} -> {stage}"
    )
    assert stage is not ResearchStage.EARLY_TRIAL


def test_phase_iii_over_phase_i_substring_explicit():
    """显式断言：'phase iii' 字符串确实包含 'phase i' 子串，但仍判为突破性。"""
    title = "Phase III"
    assert "phase i" in title.lower(), "前提：phase iii 包含 phase i 子串"
    assert infer_research_stage({"title": title}) is ResearchStage.BREAKTHROUGH_RCT


# ─────────────────────────────────────────────────────────────────────────────
# R12.1 边界：空 dict / 缺失字段 / 异常输入 → 安全默认，不抛异常，绝不误判为突破性
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        {},                              # 空 dict
        {"foo": "bar"},                  # 无关字段
        {"title": None, "abstract": None},
        {"title": 123, "abstract": []},  # 非字符串
        {"source_type": "paper_en"},     # 仅来源，无关键词
        None,                            # 非 dict
        "not a dict",
        12345,
    ],
)
def test_infer_safe_default_not_breakthrough(evidence):
    stage = infer_research_stage(evidence)
    # 不抛异常，且无证据时绝不能默认为突破性（会把不确定证据夸大为已确立结论）
    assert stage is not ResearchStage.BREAKTHROUGH_RCT, (
        f"无证据信号时不得默认突破性: {evidence!r} -> {stage}"
    )
    assert isinstance(stage, ResearchStage)


def test_infer_empty_dict_returns_conservative_default():
    """空 dict 应返回保守默认 EARLY_TRIAL（带不确定性提示），符合实现约定。"""
    assert infer_research_stage({}) is ResearchStage.EARLY_TRIAL


# ─────────────────────────────────────────────────────────────────────────────
# R11.2 validate_nct —— 合法 NCT
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        {"nct_id": "NCT12345678", "source_type": "trial"},
        {"nct_id": "NCT00000000", "source_type": "trial"},
        {"nct_id": "  NCT87654321  ", "source_type": "trial"},  # 含空白，strip 后合法
        {"nct_id": "NCT12345678", "source_type": "Trial"},      # 大小写不敏感
        {"nct_id": "NCT12345678"},                              # 缺 source_type，仅看格式
    ],
)
def test_validate_nct_true(evidence):
    assert validate_nct(evidence) is True, f"应校验通过: {evidence!r}"


# ─────────────────────────────────────────────────────────────────────────────
# R11.2 validate_nct —— 格式错误
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        {"nct_id": "NCT123", "source_type": "trial"},          # 位数不足
        {"nct_id": "NCT1234567", "source_type": "trial"},      # 7 位
        {"nct_id": "NCT123456789", "source_type": "trial"},    # 9 位
        {"nct_id": "NCT1234567A", "source_type": "trial"},     # 含字母
        {"nct_id": "12345678", "source_type": "trial"},        # 缺前缀
        {"nct_id": "nct12345678", "source_type": "trial"},     # 小写前缀
        {"nct_id": "", "source_type": "trial"},                # 空字符串
        {"nct_id": "   ", "source_type": "trial"},             # 纯空白
        {"nct_id": "NCT 12345678", "source_type": "trial"},    # 中间含空格
    ],
)
def test_validate_nct_bad_format(evidence):
    assert validate_nct(evidence) is False, f"格式错误应校验失败: {evidence!r}"


# ─────────────────────────────────────────────────────────────────────────────
# R11.2 validate_nct —— 来源类型与 NCT 不一致
#   合法格式但 source_type 非 trial（如 paper_en）→ False，不渲染试验卡片
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "source_type",
    ["paper_en", "guide", "meeting", "paper_cn", "news"],
)
def test_validate_nct_source_inconsistent(source_type):
    evidence = {"nct_id": "NCT12345678", "source_type": source_type}
    assert validate_nct(evidence) is False, (
        f"来源类型 {source_type!r} 与 NCT 不一致应失败"
    )


# ─────────────────────────────────────────────────────────────────────────────
# R11.2 validate_nct —— 缺失 nct_id / 异常输入 → False，不抛异常
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evidence",
    [
        {"source_type": "trial"},        # 缺 nct_id
        {},                              # 空 dict
        {"nct_id": None, "source_type": "trial"},
        {"nct_id": 12345678, "source_type": "trial"},  # 非字符串
        None,                            # 非 dict
        "NCT12345678",                   # 字符串而非 dict
    ],
)
def test_validate_nct_missing_or_bad_input(evidence):
    assert validate_nct(evidence) is False, f"缺失/异常输入应校验失败: {evidence!r}"


# ─────────────────────────────────────────────────────────────────────────────
# R12.3 build_uncertainty_note —— 早期/临床前必须给出非空提示；突破性返回 None
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "stage",
    [ResearchStage.EARLY_TRIAL, ResearchStage.PRECLINICAL],
)
def test_uncertainty_note_present_for_early_and_preclinical(stage):
    note = build_uncertainty_note(stage)
    assert note is not None, f"{stage} 必须返回不确定性提示"
    assert isinstance(note, str) and note.strip(), "提示文本应非空"


def test_uncertainty_note_none_for_breakthrough():
    assert build_uncertainty_note(ResearchStage.BREAKTHROUGH_RCT) is None


# ─────────────────────────────────────────────────────────────────────────────
# R12.3 端到端一致性：早期/临床前的证据经 infer 后必带提示，突破性不带
# ─────────────────────────────────────────────────────────────────────────────

def test_early_evidence_carries_uncertainty_note():
    stage = infer_research_stage({"title": "Phase I first-in-human study"})
    assert stage is ResearchStage.EARLY_TRIAL
    assert build_uncertainty_note(stage) is not None


def test_preclinical_evidence_carries_uncertainty_note():
    stage = infer_research_stage({"title": "小鼠模型抗肿瘤研究"})
    assert stage is ResearchStage.PRECLINICAL
    assert build_uncertainty_note(stage) is not None


def test_breakthrough_evidence_has_no_uncertainty_note():
    stage = infer_research_stage({"title": "Phase III randomized controlled trial"})
    assert stage is ResearchStage.BREAKTHROUGH_RCT
    assert build_uncertainty_note(stage) is None
