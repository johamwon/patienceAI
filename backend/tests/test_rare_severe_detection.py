"""
任务 5.2：罕见病/重症检测单元测试

从需求方（甲方）视角验收 Requirement 9 的以下验收标准：
- R9.1: parse_query 输出包含 rare_disease / severe_condition 两个布尔字段。
- R9.2: 查询匹配罕见病判定条件时 detect_rare_disease 返回 True。
- R9.3: 查询匹配重症判定条件时 detect_severe_condition 返回 True。
- R9.4: 无关查询 / 输入异常时安全返回 False，不抛异常。
- R9.6: 罕见病/重症判定为 True 时，risk_level 仍按现有规则独立判定（互不污染）。

测试只验证现有实现行为，不修改实现。
"""

import pytest

from backend.app.services.intent_classifier import (
    detect_rare_disease,
    detect_severe_condition,
    parse_query,
    RiskLevel,
)


# ─────────────────────────────────────────────────────────────────────────────
# R9.2 罕见病命中 → detect_rare_disease 返回 True
#   覆盖 SMA、渐冻症/ALS、DMD、血友病等代表病种；含中英文别名、大小写、中英混杂
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    [
        # SMA / 脊髓性肌萎缩
        "孩子确诊了SMA该怎么办",
        "脊髓性肌萎缩症有没有新药",
        "脊肌萎缩症的治疗进展",
        "sma 基因治疗",                       # 小写
        "SMA",                                # 纯大写英文缩写
        # ALS / 渐冻症
        "渐冻症最新研究",
        "肌萎缩侧索硬化症能治吗",
        "ALS有什么临床试验",
        "als 渐冻人 病程",                    # 中英混杂
        "运动神经元病的护理",
        # DMD / 杜氏肌营养不良
        "DMD杜氏肌营养不良基因疗法",
        "假肥大型肌营养不良怎么康复",
        "dmd 最新进展",
        # 血友病
        "血友病A型用什么药",
        "hemophilia treatment options",       # 纯英文
        "Haemophilia 出血处理",                # 英式拼写 + 大小写
        # 其他代表性罕见病
        "戈谢病酶替代治疗",
        "Gaucher disease 进展",
        "法布雷病的症状",
        "Fabry 病的诊断",
        "庞贝病新疗法",
        "苯丙酮尿症饮食管理",
        "PKU 患儿能吃什么",
        "亨廷顿舞蹈症遗传咨询",
    ],
)
def test_detect_rare_disease_true(query):
    assert detect_rare_disease(query) is True, f"应判定为罕见病: {query!r}"


# ─────────────────────────────────────────────────────────────────────────────
# R9.4 无关查询 → detect_rare_disease 返回 False
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    [
        "感冒怎么办",
        "高血压饮食注意什么",
        "糖尿病可以吃水果吗",
        "今天天气真好",
        "如何提高睡眠质量",
        "颈椎病的锻炼方法",
    ],
)
def test_detect_rare_disease_false(query):
    assert detect_rare_disease(query) is False, f"不应判定为罕见病: {query!r}"


# ─────────────────────────────────────────────────────────────────────────────
# R9.3 重症命中 → detect_severe_condition 返回 True
#   覆盖 胰腺癌、胶质母细胞瘤、晚期、转移、复发、IV期 等
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    [
        "胰腺癌晚期还能活多久",
        "pancreatic cancer 治疗",
        "胶质母细胞瘤的标准治疗",
        "胶质瘤复发怎么办",
        "Glioblastoma 临床试验",
        "GBM 新药",
        "肿瘤已经转移到肝",
        "转移性乳腺癌",
        "癌症复发了",
        "病情恶化",
        "IV期肺癌",
        "ⅳ期患者",
        "四期胃癌",
        "III期结肠癌",
        "三期治疗方案",
        "恶性肿瘤",
        "广泛转移怎么办",
        "白血病骨髓移植",
        "leukemia treatment",
        "淋巴瘤分期",
        "末期患者护理",
    ],
)
def test_detect_severe_condition_true(query):
    assert detect_severe_condition(query) is True, f"应判定为重症: {query!r}"


# ─────────────────────────────────────────────────────────────────────────────
# R9.4 无关查询 → detect_severe_condition 返回 False
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    [
        "感冒怎么办",
        "高血压饮食注意什么",
        "如何健康减肥",
        "维生素C的作用",
        "怎么预防蛀牙",
    ],
)
def test_detect_severe_condition_false(query):
    assert detect_severe_condition(query) is False, f"不应判定为重症: {query!r}"


# ─────────────────────────────────────────────────────────────────────────────
# R9.4 边界：空字符串 / None / 非字符串 → 安全返回 False，不抛异常
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad_input", ["", None, 123, [], {}])
def test_detect_rare_disease_safe_on_bad_input(bad_input):
    assert detect_rare_disease(bad_input) is False


@pytest.mark.parametrize("bad_input", ["", None, 123, [], {}])
def test_detect_severe_condition_safe_on_bad_input(bad_input):
    assert detect_severe_condition(bad_input) is False


# ─────────────────────────────────────────────────────────────────────────────
# R9.1 parse_query 输出包含 rare_disease / severe_condition 两个布尔字段
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_query_has_boolean_flags():
    result = parse_query("胰腺癌晚期还能活多久")
    assert "rare_disease" in result
    assert "severe_condition" in result
    assert isinstance(result["rare_disease"], bool)
    assert isinstance(result["severe_condition"], bool)


def test_parse_query_flags_for_unrelated_query():
    result = parse_query("感冒怎么办")
    assert result["rare_disease"] is False
    assert result["severe_condition"] is False


# ─────────────────────────────────────────────────────────────────────────────
# R9.6 独立性：罕见病/重症标记为 True 不污染 risk_level
#   risk_level 仍须严格按现有规则（HIGH_RISK / MEDIUM / PROHIBITED 关键词）判定
# ─────────────────────────────────────────────────────────────────────────────

def test_rare_disease_with_high_risk_keyword_still_high():
    """罕见病词 + 高风险词("还能活多久")：rare_disease=True 且 risk_level=high。"""
    query = "渐冻症患者还能活多久"
    result = parse_query(query)
    assert result["rare_disease"] is True
    assert result["risk_level"] == RiskLevel.HIGH.value


def test_severe_condition_with_high_risk_keyword_still_high():
    """重症词 + 高风险词："胰腺癌晚期还能活多久"：severe=True 且 risk_level=high。"""
    query = "胰腺癌晚期还能活多久"
    result = parse_query(query)
    assert result["severe_condition"] is True
    assert result["risk_level"] == RiskLevel.HIGH.value


def test_severe_condition_with_prohibited_keyword_still_prohibited():
    """重症词 + 禁止级词("处方")：severe=True 且 risk_level=prohibited。"""
    query = "晚期胰腺癌帮我开个处方"
    result = parse_query(query)
    assert result["severe_condition"] is True
    assert result["risk_level"] == RiskLevel.PROHIBITED.value


def test_rare_disease_low_risk_query_still_low():
    """只含罕见病词、无任何风险关键词的低风险查询：risk_level 仍为 low。"""
    query = "血友病是什么"
    result = parse_query(query)
    assert result["rare_disease"] is True
    assert result["risk_level"] == RiskLevel.LOW.value


def test_severe_condition_low_risk_query_still_low():
    """只含重症词、无风险关键词的查询：severe=True 但 risk_level 仍为 low。"""
    query = "淋巴瘤是什么意思"
    result = parse_query(query)
    assert result["severe_condition"] is True
    assert result["risk_level"] == RiskLevel.LOW.value


def test_flags_do_not_change_risk_compared_to_baseline():
    """
    对照实验：同一高风险词在「有/无」罕见病词两种 query 下，
    risk_level 判定结果应完全一致——证明标记未参与 risk_level 计算。
    """
    baseline = parse_query("还能活多久")           # 仅高风险词
    with_rare = parse_query("渐冻症还能活多久")      # 罕见病词 + 高风险词
    assert with_rare["rare_disease"] is True
    assert baseline["rare_disease"] is False
    assert with_rare["risk_level"] == baseline["risk_level"] == RiskLevel.HIGH.value
