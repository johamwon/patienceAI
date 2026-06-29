"""
轻量会话记忆（Session Memory）

为每个 session_id 保留最近 N 轮查询上下文，供陪伴引擎在生成回答时参考。

设计要点（对应需求 R4）：
- R4.1：携带 session_id 的查询，将其查询文本与情绪状态追加到会话记录。
- R4.2：每个 session_id 保留最近 N 轮，N 可配置（环境变量 SESSION_MAX_TURNS，默认 5）。
- R4.5：MVP 仅进程内存存储，服务重启后清空（不持久化）。
- R4.6：超过 N 轮时丢弃最早的记录（由 deque(maxlen=N) 天然保证）。

开放问题 OQ1：未来可能引入持久化存储（如 Redis）。为此定义抽象基类
`SessionStore`，当前提供内存实现 `InMemorySessionStore`，未来可零成本新增
`RedisSessionStore` 等实现。
"""

import os
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

# R4.2：最近保留轮数，可配置，默认 5。
SESSION_MAX_TURNS = int(os.getenv("SESSION_MAX_TURNS", "5"))


@dataclass
class SessionTurn:
    """单轮会话记录（纯数据类，由调用方构造传入）。

    Attributes:
        query: 患者本轮查询文本。
        emotion: 本轮识别出的情绪状态（EmotionState 的字符串值）。
        timestamp: ISO 8601 时间戳字符串（建议 datetime.now().isoformat()），
            由调用方在构造时生成，便于测试时注入确定性的时间。
    """

    query: str
    emotion: str
    timestamp: str


class SessionStore(ABC):
    """会话记忆存储抽象基类。

    预留未来 Redis / 数据库等持久化实现的扩展点（OQ1）。
    """

    @abstractmethod
    def append(self, session_id: str, turn: SessionTurn) -> None:
        """将一轮记录追加到指定会话（R4.1）。

        当会话记录超过最大轮数时，应丢弃最早的记录（R4.6）。
        """
        ...

    @abstractmethod
    def recent(self, session_id: str, n: int) -> list[SessionTurn]:
        """返回指定会话最近的 n 轮记录。

        约定：返回顺序为时间顺序（最早 → 最新）。返回数量为
        min(n, 已存储轮数, max_turns)。对不存在的 session_id 返回空列表。
        """
        ...


class InMemorySessionStore(SessionStore):
    """进程内存会话记忆实现。

    使用 ``dict[session_id -> collections.deque(maxlen=max_turns)]`` 存储，
    通过 ``threading.Lock`` 保护并发的 append/recent 操作。

    存储于进程内存中，服务重启后即清空（R4.5）。每个会话最多保留
    ``max_turns`` 轮，deque 的 ``maxlen`` 在超出时自动丢弃最早的记录（R4.6）。

    返回顺序：``recent`` 按时间顺序返回（最早 → 最新）。
    """

    def __init__(self, max_turns: int = SESSION_MAX_TURNS):
        """构造会话记忆存储。

        Args:
            max_turns: 每个会话保留的最大轮数，默认取全局 SESSION_MAX_TURNS。
                显式传参便于测试时使用不同 N 实例化。
        """
        self.max_turns = max_turns
        self._sessions: dict[str, deque[SessionTurn]] = {}
        self._lock = threading.Lock()

    def append(self, session_id: str, turn: SessionTurn) -> None:
        """追加一轮记录（R4.1）；超过 max_turns 时自动丢弃最早记录（R4.6）。"""
        with self._lock:
            bucket = self._sessions.get(session_id)
            if bucket is None:
                bucket = deque(maxlen=self.max_turns)
                self._sessions[session_id] = bucket
            bucket.append(turn)

    def recent(self, session_id: str, n: int) -> list[SessionTurn]:
        """返回最近 n 轮记录，按时间顺序（最早 → 最新）。

        - 对不存在的 session_id 返回空列表，不抛异常。
        - n <= 0 时返回空列表。
        - 实际返回数量为 min(n, 已存储轮数)。
        """
        if n <= 0:
            return []
        with self._lock:
            bucket = self._sessions.get(session_id)
            if not bucket:
                return []
            turns = list(bucket)
            return turns[-n:]


# ─── 全局单例 ───────────────────────────────────────────────────────────────

session_store = InMemorySessionStore()
