"""
任务 6.2：detect_emotion 回退单元测试

从需求方（甲方）视角验收 Requirement 2 的以下验收标准：
- R2.2: 采用规则匹配 + LLM 判定的混合策略产出情绪状态分类。
- R2.3: LLM 不可用 / 调用失败 / 返回无法识别 → 回退规则匹配结果。
- R2.6: 无法匹配任何情绪信号 → 默认返回"平静求知"（CALM）。

并重点验证（关系 R2.4 急症联动不漏的前提）：
- 高危情绪（URGENT、DESPAIR）规则先行命中，即使传入 llm_client 也不被 LLM 覆盖/降级。

测试只验证现有实现行为，不修改实现。pytest 同步调用 detect_emotion。
"""

import pytest

from backend.app.services.emotion_detector import detect_emotion
from backend.app.models.schemas import EmotionState


# ─────────────────────────────────────────────────────────────────────────────
# 高危情绪规则先行：URGENT / DESPAIR 关键词命中（llm_client=None 也命中）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    ["我快死了", "突然喘不过气", "救命啊", "在大出血", "突然晕倒了", "好急"],
)
def test_urgent_keywords_match_without_llm(query):
    """R2.1/R2.6 规则路径：urgent 关键词 → URGENT。"""
    assert detect_emotion(query, llm_client=None) == EmotionState.URGENT


@pytest.mark.parametrize(
    "query",
    ["我不想活了", "感觉没救了", "我想放弃了", "真的好绝望", "只能等死"],
)
def test_despair_keywords_match_without_llm(query):
    """R2.1/R2.6 规则路径：despair 关键词 → DESPAIR。"""
    assert detect_emotion(query, llm_client=None) == EmotionState.DESPAIR


# ─────────────────────────────────────────────────────────────────────────────
# 关键断言：高危情绪即使传入 LLM 也走规则先行，不被 LLM 降级（R2.4 联动不漏前提）
# 构造一个会返回 "calm" 的 mock llm_client，含 urgent/despair 关键词的 query
# 仍必须为 URGENT / DESPAIR。
# ─────────────────────────────────────────────────────────────────────────────

def test_urgent_not_overridden_by_llm(make_mock_llm_client):
    """高危 URGENT 规则先行，LLM 返回 calm 也不得降级。"""
    llm = make_mock_llm_client(response="calm")
    result = detect_emotion("我快喘不过气了，救命", llm_client=llm)
    assert result == EmotionState.URGENT
    # 规则先行命中后应直接返回，不应调用 LLM。
    assert llm.calls == []


def test_despair_not_overridden_by_llm(make_mock_llm_client):
    """高危 DESPAIR 规则先行，LLM 返回 calm 也不得降级。"""
    llm = make_mock_llm_client(response="calm")
    result = detect_emotion("我不想活了，没救了", llm_client=llm)
    assert result == EmotionState.DESPAIR
    assert llm.calls == []


# ─────────────────────────────────────────────────────────────────────────────
# llm_client=None 纯规则路径：panic / anxiety 命中；无关键词 → CALM（R2.6）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    ["我好怕", "吓死我了", "这可怎么办啊", "我快崩溃了", "实在扛不住了"],
)
def test_panic_keywords_match_without_llm(query):
    assert detect_emotion(query, llm_client=None) == EmotionState.PANIC


@pytest.mark.parametrize(
    "query",
    ["我很担心", "最近很焦虑", "晚上睡不着", "是不是很严重", "会不会扩散"],
)
def test_anxiety_keywords_match_without_llm(query):
    assert detect_emotion(query, llm_client=None) == EmotionState.ANXIETY


@pytest.mark.parametrize(
    "query",
    ["这个药的作用机制是什么", "想了解一下这种治疗方法", "请介绍下相关研究"],
)
def test_no_keyword_returns_calm_without_llm(query):
    """R2.6：无任何情绪信号 → 默认 CALM。"""
    assert detect_emotion(query, llm_client=None) == EmotionState.CALM


# ─────────────────────────────────────────────────────────────────────────────
# LLM 路径（非高危查询）：采用 LLM 结果 / 无法识别回退 / 抛异常回退（R2.2, R2.3）
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_result_adopted_for_non_high_risk(make_mock_llm_client):
    """R2.2：非高危、无规则命中的中性查询，应采用 LLM 返回的情绪。"""
    llm = make_mock_llm_client(response="anxiety")
    # 该查询不含任何规则关键词，规则结果为 None → 走 LLM。
    result = detect_emotion("这种情况我该如何应对", llm_client=llm)
    assert result == EmotionState.ANXIETY
    assert len(llm.calls) == 1  # 确实调用了 LLM


def test_llm_result_overrides_rule_for_non_high_risk(make_mock_llm_client):
    """非高危规则命中（anxiety）时，LLM 给出更精的 panic 应被采用。"""
    llm = make_mock_llm_client(response="panic")
    # "担心" 命中 ANXIETY 规则（非高危），LLM 精判为 panic。
    result = detect_emotion("我有点担心", llm_client=llm)
    assert result == EmotionState.PANIC
    assert len(llm.calls) == 1


def test_llm_unrecognized_falls_back_to_rule(make_mock_llm_client):
    """R2.3：LLM 返回无法识别文本 → 回退规则结果。"""
    llm = make_mock_llm_client(response="这是一段无法识别的垃圾文本！@#￥%")
    result = detect_emotion("我很担心", llm_client=llm)
    assert result == EmotionState.ANXIETY  # 规则结果
    assert len(llm.calls) == 1


def test_llm_unrecognized_falls_back_to_calm_when_no_rule(make_mock_llm_client):
    """R2.3 + R2.6：LLM 无法识别且无规则命中 → CALM。"""
    llm = make_mock_llm_client(response="完全无关的输出")
    result = detect_emotion("介绍下这种疗法的原理", llm_client=llm)
    assert result == EmotionState.CALM


def test_llm_exception_falls_back_to_rule(make_mock_llm_client):
    """R2.3：LLM 调用抛异常 → 回退规则结果。"""

    def _boom(messages, **kwargs):
        raise RuntimeError("LLM service down")

    llm = make_mock_llm_client(responder=_boom)
    result = detect_emotion("我很担心", llm_client=llm)
    assert result == EmotionState.ANXIETY  # 规则结果
    assert len(llm.calls) == 1


def test_llm_exception_falls_back_to_calm_when_no_rule(make_mock_llm_client):
    """R2.3 + R2.6：LLM 抛异常且无规则命中 → CALM，不抛异常。"""

    def _boom(messages, **kwargs):
        raise RuntimeError("LLM service down")

    llm = make_mock_llm_client(responder=_boom)
    result = detect_emotion("想了解相关研究进展", llm_client=llm)
    assert result == EmotionState.CALM


# ─────────────────────────────────────────────────────────────────────────────
# 空 / None 输入 → CALM，不抛异常
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", ["", None])
def test_empty_or_none_input_returns_calm(query):
    assert detect_emotion(query, llm_client=None) == EmotionState.CALM


@pytest.mark.parametrize("query", ["", None])
def test_empty_or_none_input_returns_calm_even_with_llm(query, make_mock_llm_client):
    """空/None 输入直接 CALM，不应触发 LLM 调用。"""
    llm = make_mock_llm_client(response="panic")
    assert detect_emotion(query, llm_client=llm) == EmotionState.CALM
    assert llm.calls == []
