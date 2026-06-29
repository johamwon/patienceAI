"""
任务 6.4：InMemorySessionStore 属性测试（甲方独立验收）

从需求方视角验证 Requirement 4 的以下验收标准对应的不变量：
- R4.2: 每个 session_id 保留最近 N 轮，N 可配置，默认值 5。
- R4.6: 超过 N 轮时丢弃最早的记录，最多保留 N 轮。

并验证 SessionStore.recent 的契约（见 session_memory.py docstring）：
- recent(session_id, n) 返回顺序为时间顺序（最早 → 最新）。
- 返回数量为 min(n, 已存储轮数, max_turns)。
- 对不存在的 session_id 返回空列表。

测试只验证现有实现行为，不修改实现。每个用例使用独立的
InMemorySessionStore(max_turns=N) 实例与独立 session_id，避免全局单例
session_store 的状态串扰。
"""

from hypothesis import given, settings, strategies as st

from backend.app.services.session_memory import (
    InMemorySessionStore,
    SessionTurn,
    SESSION_MAX_TURNS,
)


def _make_turns(queries):
    """根据 query 列表构造可区分的 SessionTurn 序列（带序号确定值）。"""
    return [
        SessionTurn(
            query=f"{i:04d}::{q}",
            emotion=f"emotion-{i % 5}",
            timestamp=f"2024-01-01T00:00:{i % 60:02d}",
        )
        for i, q in enumerate(queries)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 属性 1：recent 长度 == min(n, 已追加条数, N)；内容/顺序为"最近 N 轮内的最近 n 条"
# ─────────────────────────────────────────────────────────────────────────────

@given(
    max_turns=st.integers(min_value=1, max_value=10),
    queries=st.lists(st.text(), max_size=30),
    n=st.integers(min_value=1, max_value=40),
)
@settings(max_examples=300)
def test_recent_length_content_and_order(max_turns, queries, n):
    """对任意 N、追加序列、正整数 n：长度、内容、顺序均符合契约（R4.2, R4.6）。"""
    store = InMemorySessionStore(max_turns=max_turns)
    session_id = "sess-prop-1"

    turns = _make_turns(queries)
    for t in turns:
        store.append(session_id, t)

    result = store.recent(session_id, n)

    appended = len(turns)
    # 长度不变量：min(n, 已追加条数, N)
    expected_len = min(n, appended, max_turns)
    assert len(result) == expected_len

    # 内容/顺序不变量：先按 R4.6 保留最近 N 轮（最早→最新），再取最近 n 条。
    kept = turns[-max_turns:] if max_turns < appended else list(turns)
    expected = kept[-n:] if n < len(kept) else kept
    assert result == expected
    # 显式核对顺序：与追加顺序一致（最早 → 最新）。
    assert [r.query for r in result] == [e.query for e in expected]


# ─────────────────────────────────────────────────────────────────────────────
# 属性 2：当追加条数 > N，最早的记录被丢弃，只保留最近 N 条（R4.6）
# ─────────────────────────────────────────────────────────────────────────────

@given(
    max_turns=st.integers(min_value=1, max_value=10),
    extra=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=200)
def test_oldest_discarded_when_over_capacity(max_turns, extra):
    """追加 N+extra 条后，recent(大n) 恰为最近 N 条且顺序正确（R4.6）。"""
    store = InMemorySessionStore(max_turns=max_turns)
    session_id = "sess-prop-2"

    total = max_turns + extra
    turns = _make_turns([f"q{i}" for i in range(total)])
    for t in turns:
        store.append(session_id, t)

    # 请求一个足够大的 n，应只拿到最近 max_turns 条。
    result = store.recent(session_id, total + 5)
    assert len(result) == max_turns
    # 恰为最近 N 条（丢弃了最早的 extra 条），顺序最早→最新。
    assert result == turns[-max_turns:]
    assert [r.query for r in result] == [t.query for t in turns[-max_turns:]]


# ─────────────────────────────────────────────────────────────────────────────
# 属性 3：n <= 0 返回空列表；不存在的 session_id 返回空列表
# ─────────────────────────────────────────────────────────────────────────────

@given(
    max_turns=st.integers(min_value=1, max_value=10),
    queries=st.lists(st.text(), min_size=1, max_size=15),
)
@settings(max_examples=100)
def test_unknown_session_returns_empty(max_turns, queries):
    """不存在的 session_id → recent 返回空列表（不抛异常）。"""
    store = InMemorySessionStore(max_turns=max_turns)
    for t in _make_turns(queries):
        store.append("known-session", t)

    assert store.recent("does-not-exist", 5) == []
    assert store.recent("does-not-exist", 1) == []


# ─────────────────────────────────────────────────────────────────────────────
# 例子型断言（明确数值边界）
# ─────────────────────────────────────────────────────────────────────────────

def test_default_max_turns_is_5():
    """R4.2：默认 N 为 5。"""
    assert SESSION_MAX_TURNS == 5
    assert InMemorySessionStore().max_turns == 5


def test_append_7_recent_10_keeps_latest_5_in_order():
    """N=5 默认值：追加 7 条后 recent(10) 只返回最近 5 条且顺序正确（R4.2, R4.6）。"""
    store = InMemorySessionStore()  # 默认 max_turns=5
    session_id = "sess-example"

    turns = _make_turns([f"q{i}" for i in range(7)])  # q0..q6
    for t in turns:
        store.append(session_id, t)

    result = store.recent(session_id, 10)
    assert len(result) == 5
    # 最早两条 (q0, q1) 被丢弃，保留 q2..q6，顺序最早→最新。
    assert [r.query for r in result] == [turns[i].query for i in range(2, 7)]
    assert result == turns[2:7]


def test_recent_subset_smaller_than_stored():
    """recent(n) 在 n < 已存储条数时，取最近 n 条（最早→最新）。"""
    store = InMemorySessionStore(max_turns=5)
    turns = _make_turns([f"q{i}" for i in range(5)])  # q0..q4
    for t in turns:
        store.append("s", t)

    result = store.recent("s", 3)
    assert [r.query for r in result] == [turns[2].query, turns[3].query, turns[4].query]


def test_unknown_session_empty_example():
    """不存在的 session_id → 空列表。"""
    store = InMemorySessionStore(max_turns=5)
    assert store.recent("nope", 5) == []
