"""
甲方验收测试：compliance_guard 合规兜底校验（关联 R13.1）

验收意图（需求方视角）：
R13.1 要求所有面向患者的新增输出中不得包含诊断结论、处方剂量或个体化治疗指令。
`compliance_guard` 是生成后兜底，需要满足：
  1. 诊断句被剥离/替换为中性提示，且命中项列表非空。
  2. 剂量/处方句被剥离/替换。
  3. 正常医学陈述（群体证据、引导就医）不被误伤，命中项列表为空。
  4. 命中项列表正确返回被触发的模式。
  5. 空字符串输入返回 ("", [])。
  6. 多句混合文本：仅替换违规句，正常句原样保留。

测试严格站在需求方角度：违规句必须真正从输出中消失（不能残留诊断/剂量原文），
正常句必须逐字保留。任何误伤或漏判都如实暴露，不放宽断言。
"""

from agents.prompts.persona import (
    DIAGNOSIS_PATTERNS,
    _SAFE_REPLACEMENT,
    compliance_guard,
)


# ─── 场景 1：诊断句被剥离/替换，命中项非空 ──────────────────────────────────

class TestDiagnosisSentencesStripped:
    """诊断结论句必须被替换为中性提示，原始诊断措辞不得残留。"""

    def test_你患了某病_被替换且命中非空(self):
        text = "你患了肺癌。"
        cleaned, violations = compliance_guard(text)

        assert violations, "诊断句应命中违规模式，命中项列表不应为空"
        assert _SAFE_REPLACEMENT in cleaned, "诊断句应被替换为中性提示"
        # 诊断核心措辞不得残留在输出中
        assert "你患了" not in cleaned, "诊断措辞'你患了'不得残留"
        assert "肺癌" not in cleaned, "被诊断的疾病名不得残留在违规句中"

    def test_确诊为晚期_被替换且命中非空(self):
        text = "确诊为晚期。"
        cleaned, violations = compliance_guard(text)

        assert violations, "确诊句应命中违规模式"
        assert _SAFE_REPLACEMENT in cleaned, "确诊句应被替换为中性提示"
        assert "确诊为" not in cleaned, "诊断措辞'确诊为'不得残留"
        assert "晚期" not in cleaned, "确诊结论'晚期'不得残留"

    def test_你得了某病_被替换(self):
        text = "你得了胃癌。"
        cleaned, violations = compliance_guard(text)

        assert violations, "'你得了'诊断句应命中违规模式"
        assert "你得了" not in cleaned
        assert _SAFE_REPLACEMENT in cleaned


# ─── 场景 2：剂量/处方句被剥离/替换 ─────────────────────────────────────────

class TestDosageAndPrescriptionStripped:
    """处方/剂量类个体化指令必须被替换，剂量数字与药名不得残留。"""

    def test_建议你服用_被替换(self):
        text = "建议你服用阿司匹林。"
        cleaned, violations = compliance_guard(text)

        assert violations, "处方句应命中违规模式"
        assert _SAFE_REPLACEMENT in cleaned, "处方句应被替换为中性提示"
        assert "建议你服用" not in cleaned, "处方措辞不得残留"
        assert "阿司匹林" not in cleaned, "被推荐药名不得残留在违规句中"

    def test_每日服用剂量_被替换(self):
        text = "每日服用50毫克。"
        cleaned, violations = compliance_guard(text)

        assert violations, "剂量句应命中违规模式"
        assert _SAFE_REPLACEMENT in cleaned, "剂量句应被替换为中性提示"
        assert "50毫克" not in cleaned, "具体剂量不得残留"
        assert "每日服用" not in cleaned, "剂量指令措辞不得残留"

    def test_每天剂量mg单位_被替换(self):
        text = "每天吃100mg。"
        cleaned, violations = compliance_guard(text)

        assert violations, "含 mg 单位的剂量句应命中违规模式"
        assert "100mg" not in cleaned, "具体剂量不得残留"


# ─── 场景 3：正常医学陈述不被误伤，命中项为空 ──────────────────────────────

class TestNormalStatementsNotFlagged:
    """群体研究证据、引导就医等正常陈述必须逐字保留，不得误判。"""

    def test_群体研究证据陈述_不被误伤(self):
        text = "研究显示该药物可降低死亡风险约21%。"
        cleaned, violations = compliance_guard(text)

        assert violations == [], f"正常群体证据陈述不应被误判，却命中了 {violations}"
        assert cleaned == text, "正常陈述必须逐字保留，不得被替换"

    def test_引导就医陈述_不被误伤(self):
        text = "你可以和医生讨论治疗方案。"
        cleaned, violations = compliance_guard(text)

        assert violations == [], f"引导就医的正常陈述不应被误判，却命中了 {violations}"
        assert cleaned == text, "引导就医陈述必须逐字保留"

    def test_提及确诊但非诊断结论_不被误伤(self):
        # "确诊需要由医生判断"是引导就医，不是给出确诊结论
        text = "是否确诊需要由医生进一步判断。"
        cleaned, violations = compliance_guard(text)

        assert violations == [], f"非诊断性地提及'确诊'不应被误判，却命中了 {violations}"
        assert cleaned == text


# ─── 场景 4：命中项列表正确返回被触发的模式 ────────────────────────────────

class TestViolationListContents:
    """命中项列表应返回真实触发的正则模式，且都属于已定义的诊断/处方模式。"""

    def test_命中项为已定义模式(self):
        text = "你患了肺癌。"
        _, violations = compliance_guard(text)

        assert len(violations) == 1, "单条违规句应返回一条命中模式"
        assert violations[0] in DIAGNOSIS_PATTERNS, "命中项应来自已定义的禁用模式列表"

    def test_多条违规各自记录命中(self):
        text = "你患了肺癌。建议你服用阿司匹林。"
        _, violations = compliance_guard(text)

        assert len(violations) == 2, "两条违规句应分别记录两条命中模式"
        for v in violations:
            assert v in DIAGNOSIS_PATTERNS


# ─── 场景 5：空字符串输入 ───────────────────────────────────────────────────

class TestEmptyInput:
    def test_空字符串返回空文本与空列表(self):
        cleaned, violations = compliance_guard("")
        assert cleaned == ""
        assert violations == []


# ─── 场景 6：多句混合文本，仅替换违规句 ────────────────────────────────────

class TestMixedSentences:
    """混合文本中违规句被替换，正常句必须原样保留。"""

    def test_违规句替换正常句保留(self):
        text = "你患了肺癌。研究显示该药物可降低死亡风险约21%。"
        cleaned, violations = compliance_guard(text)

        assert len(violations) == 1, "仅一条违规句应被命中"
        # 违规句被剥离
        assert "你患了" not in cleaned
        assert "肺癌" not in cleaned
        assert _SAFE_REPLACEMENT in cleaned
        # 正常句逐字保留
        assert "研究显示该药物可降低死亡风险约21%。" in cleaned

    def test_正常句在前违规句在后(self):
        text = "你可以和医生讨论治疗方案。建议你服用阿司匹林。"
        cleaned, violations = compliance_guard(text)

        assert len(violations) == 1
        # 正常句保留
        assert "你可以和医生讨论治疗方案。" in cleaned
        # 违规句被替换
        assert "建议你服用" not in cleaned
        assert "阿司匹林" not in cleaned
        assert _SAFE_REPLACEMENT in cleaned

    def test_多正常句夹一违规句(self):
        text = (
            "研究显示该药物可降低死亡风险约21%。"
            "确诊为晚期。"
            "你可以和医生讨论治疗方案。"
        )
        cleaned, violations = compliance_guard(text)

        assert len(violations) == 1, "三句中仅中间一句违规"
        assert "研究显示该药物可降低死亡风险约21%。" in cleaned
        assert "你可以和医生讨论治疗方案。" in cleaned
        assert "确诊为" not in cleaned
        assert "晚期" not in cleaned
