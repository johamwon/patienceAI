"""
pytest 共享配置与 fixtures

- 将项目根目录加入 sys.path，使测试可导入 `backend.app` 与 `agents` 包。
- 提供共用的 `mock_llm_client` fixture，模拟 `backend/app/services/llm_client.py`
  中 `LLMClient.chat(messages, ...)` 的同步接口，返回可配置的固定文本。
"""

import sys
from pathlib import Path

import pytest

# ─── sys.path 配置 ────────────────────────────────────────────────────────────
# conftest.py 位于 <root>/backend/tests/，项目根为其上三级目录。
# 后端以 `backend.app.main:app` 方式启动（命名空间包），智能体为 `agents` 包，
# 二者都要求项目根在 sys.path 上。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─── Mock LLM Client ──────────────────────────────────────────────────────────

class MockLLMClient:
    """
    模拟 LLMClient 的同步 chat 接口。

    用法：
        # 默认固定返回
        client = MockLLMClient()
        client.chat([{"role": "user", "content": "..."}])  # -> 固定文本

        # 自定义返回文本
        client = MockLLMClient(response="只输出枚举值: calm")

        # 动态返回（基于 messages 计算）
        client = MockLLMClient(responder=lambda messages, **kw: "...")

    调用记录保存在 `calls` 列表中，便于断言编排顺序与调用次数。
    """

    DEFAULT_RESPONSE = "这是一段用于测试的固定模型输出文本。"

    def __init__(self, response: str | None = None, responder=None):
        self._response = response if response is not None else self.DEFAULT_RESPONSE
        self._responder = responder
        self.calls: list[dict] = []

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        response_format: dict | None = None,
    ) -> str:
        """与 LLMClient.chat 同名同签名的同步方法，返回固定/可配置文本。"""
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format,
            }
        )
        if self._responder is not None:
            return self._responder(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        return self._response

    def close(self):
        pass


@pytest.fixture
def mock_llm_client():
    """返回固定文本的 mock LLM 客户端，模拟 LLMClient.chat 同步接口。"""
    return MockLLMClient()


@pytest.fixture
def make_mock_llm_client():
    """工厂 fixture：按需创建可配置返回文本/响应函数的 mock LLM 客户端。"""

    def _factory(response: str | None = None, responder=None) -> MockLLMClient:
        return MockLLMClient(response=response, responder=responder)

    return _factory
