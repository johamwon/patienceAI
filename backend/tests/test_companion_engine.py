"""
甲方验收测试：companion_engine 编排契约（关联 R3.3 / R3.7 / R13.5）

验收意图（需求方视角）：
本测试只验证"编排契约"，不验证 LLM 生成质量。用 mock LLM 把模型输出固定为
可控文本，断言 generate_companion_message 的编排行为满足以下硬性要求：

R3.7 / R13.5：风险升级（high / prohibited）时，最终输出必含就医引导——
  即使 LLM 自己没给（实现有 _mentions_seek_care 兜底强制拼接）。
R13.5：共情不能替代风险提示——high 风险下，LLM 的共情内容仍在，同时被补上
  就医引导（两者共存，不是用共情替换风险提示）。
降级永不阻塞：LLM 抛异常 / 返回空 / llm_client=None 时，不抛异常、返回非空
  安全模板；且 high/prohibited 回退模板也含就医引导。
R13.1（在 companion 输出的体现）：compliance_guard 集成——LLM 返回含诊断句
  的文本时，诊断措辞被剥离/替换，输出不残留"你患了"。
各 EmotionState 回退模板都能正常产出非空文本。

测试严格站在需求方角度：风险升级时就医引导"一定在"，哪怕 LLM 没给；任何漏判
都如实暴露，不放宽断言。
"""

import asyncio

import pytest

from backend.app.models.schemas import EmotionState
from backend.app.services.companion_engine import generate_companion_message


# ─── 就医引导词检测（与实现 _mentions_seek_care 同义，独立复刻避免耦合内部） ──

SEEK_CARE_KEYWORDS = ["就医", "医生", "医院", "医疗机构", "就诊", "门诊", "急诊"]


def mentions_seek_care(text: str) -> bool:
    """最终输出是否包含任一就医引导词。"""
    return any(kw in text for kw in SEEK_CARE_KEYWORDS)


def raising_responder(messages, **kwargs):
    """模拟 LLM 调用失败：chat 抛异常。"""
    raise RuntimeError("simulated LLM failure")


async def call_engine(
    *,
    query="我最近总是咳嗽，会不会很严重？",
    emotion=EmotionState.ANXIETY,
    evidences=None,
    risk_level="low",
    risk_message=None,
    history=None,
    llm_client,
):
    """薄包装，统一参数顺序，便于各用例复用。"""
    return await generate_companion_message(
        query,
        emotion,
        evidences,
        risk_level,
        risk_message,
        history,
        llm_client,
    )


# ─── 场景 1：high/prohibited 风险时输出必含就医引导（即使 LLM 没给） ──────────

class TestEscalatedRiskAlwaysSeekCare:
    """R3.7 / R13.5：风险升级时，最终输出一定包含就医引导。"""

    # 一段刻意不含任何就医引导词的暖场白（共情句，可被识别）。
    WARM_NO_SEEK_CARE = "我理解你的担心，这种忐忑的心情很正常，我们慢慢一起把它看清楚。"

    @pytest.mark.parametrize("risk_level", ["high", "prohibited"])
    async def test_llm未给就医引导时被强制补上(self, make_mock_llm_client, risk_level):
        # 前置自检：mock 文本本身确实不含就医引导词，确保测的是兜底而非巧合。
        assert not mentions_seek_care(self.WARM_NO_SEEK_CARE)

        client = make_mock_llm_client(response=self.WARM_NO_SEEK_CARE)
        out = await call_engine(
            emotion=EmotionState.PANIC,
            risk_level=risk_level,
            risk_message="您的描述可能涉及紧急情况。",
            llm_client=client,
        )

        assert out and out.strip(), "风险升级时输出不应为空"
        assert mentions_seek_care(out), (
            f"风险等级 {risk_level} 时最终输出必须包含就医引导，"
            f"即使 LLM 未给。实际输出：{out!r}"
        )

    @pytest.mark.parametrize("risk_level", ["low", "medium"])
    async def test_非升级风险不强制拼接(self, make_mock_llm_client, risk_level):
        """对照组：非升级风险下不强制要求就医引导（验证兜底确由风险触发）。"""
        client = make_mock_llm_client(response=self.WARM_NO_SEEK_CARE)
        out = await call_engine(
            emotion=EmotionState.ANXIETY,
            risk_level=risk_level,
            llm_client=client,
        )
        # 低风险下，LLM 文本不含就医引导，实现不应额外拼接。
        assert not mentions_seek_care(out), (
            f"非升级风险 {risk_level} 下不应强制拼接就医引导，输出：{out!r}"
        )


# ─── 场景 2：共情不替代风险提示——两者共存（R13.5） ──────────────────────────

class TestEmpathyCoexistsWithSeekCare:
    """R13.5：high 风险下，共情内容与就医引导同时存在，不是替代关系。"""

    EMPATHY_LINE = "我理解你现在的担心"

    async def test_high风险下共情与就医引导共存(self, make_mock_llm_client):
        warm = f"{self.EMPATHY_LINE}，这种感觉真的不好受，我会陪你一起面对。"
        assert not mentions_seek_care(warm)  # mock 不含就医引导，靠兜底补

        client = make_mock_llm_client(response=warm)
        out = await call_engine(
            emotion=EmotionState.DESPAIR,
            risk_level="high",
            llm_client=client,
        )

        # 共情内容仍在（没有被风险提示替换掉）。
        assert self.EMPATHY_LINE in out, (
            f"LLM 的共情内容应保留在最终输出中，输出：{out!r}"
        )
        # 就医引导同时存在。
        assert mentions_seek_care(out), (
            f"共情之外还须并存就医引导（不得替代），输出：{out!r}"
        )


# ─── 场景 3：LLM 失败回退安全模板（不抛异常、非空） ──────────────────────────

class TestLLMFailureFallback:
    """LLM 抛异常时回退安全模板，不阻塞主流程。"""

    async def test_llm抛异常不抛出且返回非空(self, make_mock_llm_client):
        client = make_mock_llm_client(responder=raising_responder)
        out = await call_engine(
            emotion=EmotionState.ANXIETY,
            risk_level="low",
            llm_client=client,
        )
        assert isinstance(out, str) and out.strip(), "回退模板应为非空文本"

    @pytest.mark.parametrize("risk_level", ["high", "prohibited"])
    async def test_llm抛异常时升级风险回退模板含就医引导(
        self, make_mock_llm_client, risk_level
    ):
        client = make_mock_llm_client(responder=raising_responder)
        out = await call_engine(
            emotion=EmotionState.PANIC,
            risk_level=risk_level,
            llm_client=client,
        )
        assert out and out.strip()
        assert mentions_seek_care(out), (
            f"LLM 失败回退路径下，风险等级 {risk_level} 的模板也必须含就医引导，"
            f"输出：{out!r}"
        )

    async def test_llm返回空字符串时回退非空(self, make_mock_llm_client):
        client = make_mock_llm_client(response="   ")
        out = await call_engine(
            emotion=EmotionState.CALM,
            risk_level="low",
            llm_client=client,
        )
        assert out and out.strip(), "LLM 返回空白时应回退到非空安全模板"


# ─── 场景 4：llm_client=None 返回安全模板 ────────────────────────────────────

class TestNoneClientFallback:
    async def test_client为None返回非空模板(self):
        out = await call_engine(
            emotion=EmotionState.ANXIETY,
            risk_level="low",
            llm_client=None,
        )
        assert isinstance(out, str) and out.strip(), "llm_client=None 应返回非空安全模板"

    @pytest.mark.parametrize("risk_level", ["high", "prohibited"])
    async def test_client为None升级风险含就医引导(self, risk_level):
        out = await call_engine(
            emotion=EmotionState.URGENT,
            risk_level=risk_level,
            llm_client=None,
        )
        assert mentions_seek_care(out), (
            f"llm_client=None 且风险等级 {risk_level} 时模板应含就医引导，输出：{out!r}"
        )


# ─── 场景 5：compliance_guard 集成——诊断措辞被剥离（R13.1 体现） ─────────────

class TestComplianceGuardIntegration:
    async def test_诊断句被剥离不残留你患了(self, make_mock_llm_client):
        # LLM 返回含诊断结论的文本。
        diagnostic = "根据你的描述，你患了肺癌，但别太担心，我们一起想办法。"
        client = make_mock_llm_client(response=diagnostic)
        out = await call_engine(
            emotion=EmotionState.ANXIETY,
            risk_level="low",
            llm_client=client,
        )
        assert out and out.strip()
        assert "你患了" not in out, (
            f"诊断措辞应被 compliance_guard 剥离/替换，不得残留，输出：{out!r}"
        )
        assert "肺癌" not in out, (
            f"诊断结论整句应被替换，'肺癌' 不应残留，输出：{out!r}"
        )


# ─── 场景 6：各 EmotionState 回退模板都能产出非空文本 ────────────────────────

class TestAllEmotionStatesFallback:
    @pytest.mark.parametrize(
        "emotion",
        [
            EmotionState.PANIC,
            EmotionState.ANXIETY,
            EmotionState.DESPAIR,
            EmotionState.URGENT,
            EmotionState.CALM,
        ],
    )
    async def test_每个情绪回退模板非空(self, emotion):
        # 用 llm_client=None 走纯模板路径，低风险不拼接就医引导。
        out = await call_engine(
            emotion=emotion,
            risk_level="low",
            llm_client=None,
        )
        assert isinstance(out, str) and out.strip(), (
            f"情绪 {emotion.value} 的回退模板应为非空文本"
        )
