"""
订阅库（Subscription_Store）——核心订阅库，零 PII。

生克隔离核心（对应需求 R1.7 / R10.1 / R11.5）：本库仅存储
- Anonymous_User_Id（匿名标识，非实名）
- 病症关键词（disease_keyword）
- 订阅元数据（status / created_at）
- 去重记录（delivered_log）
- 渠道授权布尔事实（channel_consent，只记"开了哪个渠道"，不存联系方式）
- 站内消息（inapp_messages，零 PII）

**关键合规约束**：本库所有写入接口在类型层面绝不接受 email / openid / 手机号 /
真实姓名等任何 PII。联系方式一律只经物理隔离的 `contact_store`（contacts.db）。

设计沿用 `session_memory.py` 的抽象基类模式（便于未来换 Redis）与
`cache_service.py` 的路径 / threading.Lock 并发保护模式。

- OQ1 存储选型：SQLite（标准库 sqlite3），零外部依赖。
- R4.4：已撤销/已删除订阅（status != 'active'）不进入巡检（靠 list_all_active 过滤）。
- R5.3/R5.4：delivered_log 去重，幂等。
- R8.3：revoke -> status='revoked'。
- R8.4：delete -> 删订阅 + 连带删该订阅的 delivered_log。
- R10.3：purge_expired 按 created_at + 保留期清理。
"""

import os
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.models.schemas import Subscription

# 默认库文件：backend/app/services/radar/data/subscriptions.db（目录自动创建）
DEFAULT_DB_PATH = Path(__file__).parent / "data" / "subscriptions.db"

# R10.3：数据保留期（天），可配置，默认 365 天。
RADAR_RETENTION_DAYS = int(os.getenv("RADAR_RETENTION_DAYS", "365"))


class SubscriptionStore(ABC):
    """订阅库抽象基类。

    预留未来 Redis / 其他持久化实现的扩展点（沿用 session_memory 的抽象模式）。
    所有写入接口在类型层面仅接受匿名标识、病症关键词与渠道/摘要等非 PII 数据。
    """

    # ── 订阅生命周期 ──────────────────────────────────────────────
    @abstractmethod
    def create(self, anon_user_id: str, disease_keyword: str) -> Subscription:
        """创建订阅；(anon_user_id, disease_keyword) 幂等（R1.6）。

        若已存在同一匿名用户对同一病症的活跃订阅，返回现有订阅。
        """
        ...

    @abstractmethod
    def list_active(self, anon_user_id: str) -> list[Subscription]:
        """列出某匿名用户的所有活跃订阅（R8.1）。"""
        ...

    @abstractmethod
    def list_all_active(self) -> list[Subscription]:
        """列出全部活跃订阅（巡检用，R4.1/R4.4）。"""
        ...

    @abstractmethod
    def get(self, sub_id: str) -> Optional[Subscription]:
        """按订阅 id 获取，不存在返回 None。"""
        ...

    @abstractmethod
    def revoke(self, sub_id: str) -> None:
        """撤销订阅：status='revoked'（R8.3）。"""
        ...

    @abstractmethod
    def delete(self, sub_id: str) -> None:
        """删除订阅记录并连带删除其 delivered_log（R8.4）。"""
        ...

    # ── 去重（Delivered_Log，R5.3/R5.4） ─────────────────────────
    @abstractmethod
    def is_delivered(self, sub_id: str, fingerprint: str) -> bool:
        """判定某进展指纹是否已对该订阅推送过（R5.3）。"""
        ...

    @abstractmethod
    def mark_delivered(self, sub_id: str, fingerprint: str) -> None:
        """记录某进展指纹已推送（R5.4）；幂等。"""
        ...

    # ── 渠道授权（只记开关布尔事实，绝不存联系方式） ──────────────
    @abstractmethod
    def set_consent(self, anon_user_id: str, channel: str) -> None:
        """开启某渠道授权。"""
        ...

    @abstractmethod
    def unset_consent(self, anon_user_id: str, channel: str) -> None:
        """关闭某渠道授权（R8.5，联系方式的删除由 contact_store 负责）。"""
        ...

    @abstractmethod
    def list_consents(self, anon_user_id: str) -> list[str]:
        """列出某匿名用户已开启的渠道（R8.2）。"""
        ...

    # ── 站内消息（零 PII，R7.2） ─────────────────────────────────
    @abstractmethod
    def add_inapp_message(self, anon_user_id: str, digest_dict: dict) -> str:
        """写入一条站内消息，返回消息 id。"""
        ...

    @abstractmethod
    def list_inapp_messages(self, anon_user_id: str) -> list[dict]:
        """列出某匿名用户的站内消息（时间倒序）。"""
        ...

    @abstractmethod
    def mark_read(self, msg_id: str) -> None:
        """标记站内消息已读。"""
        ...

    # ── 删除与保留期（R8.6 / R10.3 / R10.4） ─────────────────────
    @abstractmethod
    def delete_by_user(self, anon_user_id: str) -> None:
        """删除某匿名用户在本库的全部数据（R8.6，两库分别删）。"""
        ...

    @abstractmethod
    def purge_expired(self, retention_days: int = RADAR_RETENTION_DAYS) -> int:
        """清理超过保留期的记录（R10.3），返回清理的订阅数。"""
        ...


class SQLiteSubscriptionStore(SubscriptionStore):
    """基于标准库 sqlite3 的订阅库实现（零 PII）。

    - 单文件 SQLite（默认 subscriptions.db），目录自动创建。
    - threading.Lock 保护并发（沿用 cache_service 模式）。
    - 每次操作使用独立连接，避免跨线程共享连接的问题。
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        """构造订阅库。

        Args:
            db_path: 库文件路径；默认 subscriptions.db。测试可传临时库路径。
        """
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """建表（若不存在）。"""
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id              TEXT PRIMARY KEY,
                        anon_user_id    TEXT NOT NULL,
                        disease_keyword TEXT NOT NULL,
                        status          TEXT NOT NULL DEFAULT 'active',
                        created_at      TEXT NOT NULL,
                        UNIQUE(anon_user_id, disease_keyword)
                    );
                    CREATE TABLE IF NOT EXISTS delivered_log (
                        subscription_id TEXT NOT NULL,
                        fingerprint     TEXT NOT NULL,
                        delivered_at    TEXT NOT NULL,
                        PRIMARY KEY (subscription_id, fingerprint)
                    );
                    CREATE TABLE IF NOT EXISTS channel_consent (
                        anon_user_id TEXT NOT NULL,
                        channel      TEXT NOT NULL,
                        consented_at TEXT NOT NULL,
                        PRIMARY KEY (anon_user_id, channel)
                    );
                    CREATE TABLE IF NOT EXISTS inapp_messages (
                        id           TEXT PRIMARY KEY,
                        anon_user_id TEXT NOT NULL,
                        digest_json  TEXT NOT NULL,
                        created_at   TEXT NOT NULL,
                        read         INTEGER NOT NULL DEFAULT 0
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _row_to_subscription(row: sqlite3.Row) -> Subscription:
        return Subscription(
            id=row["id"],
            anon_user_id=row["anon_user_id"],
            disease_keyword=row["disease_keyword"],
            status=row["status"],
            created_at=row["created_at"],
        )

    # ── 订阅生命周期 ──────────────────────────────────────────────
    def create(self, anon_user_id: str, disease_keyword: str) -> Subscription:
        with self._lock:
            conn = self._connect()
            try:
                # R1.6 幂等：先查已存在的活跃订阅
                existing = conn.execute(
                    "SELECT * FROM subscriptions "
                    "WHERE anon_user_id = ? AND disease_keyword = ? AND status = 'active'",
                    (anon_user_id, disease_keyword),
                ).fetchone()
                if existing is not None:
                    return self._row_to_subscription(existing)

                sub_id = str(uuid.uuid4())
                created_at = datetime.now().isoformat()
                try:
                    conn.execute(
                        "INSERT INTO subscriptions "
                        "(id, anon_user_id, disease_keyword, status, created_at) "
                        "VALUES (?, ?, ?, 'active', ?)",
                        (sub_id, anon_user_id, disease_keyword, created_at),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    # UNIQUE 冲突：可能存在一条非活跃（revoked）的历史记录，
                    # 复用它并重新激活，保证 (user, disease) 幂等唯一。
                    conn.rollback()
                    row = conn.execute(
                        "SELECT * FROM subscriptions "
                        "WHERE anon_user_id = ? AND disease_keyword = ?",
                        (anon_user_id, disease_keyword),
                    ).fetchone()
                    if row is not None:
                        conn.execute(
                            "UPDATE subscriptions SET status = 'active' WHERE id = ?",
                            (row["id"],),
                        )
                        conn.commit()
                        refreshed = conn.execute(
                            "SELECT * FROM subscriptions WHERE id = ?", (row["id"],)
                        ).fetchone()
                        return self._row_to_subscription(refreshed)
                    raise

                row = conn.execute(
                    "SELECT * FROM subscriptions WHERE id = ?", (sub_id,)
                ).fetchone()
                return self._row_to_subscription(row)
            finally:
                conn.close()

    def list_active(self, anon_user_id: str) -> list[Subscription]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM subscriptions "
                    "WHERE anon_user_id = ? AND status = 'active' "
                    "ORDER BY created_at",
                    (anon_user_id,),
                ).fetchall()
                return [self._row_to_subscription(r) for r in rows]
            finally:
                conn.close()

    def list_all_active(self) -> list[Subscription]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM subscriptions WHERE status = 'active' ORDER BY created_at"
                ).fetchall()
                return [self._row_to_subscription(r) for r in rows]
            finally:
                conn.close()

    def get(self, sub_id: str) -> Optional[Subscription]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM subscriptions WHERE id = ?", (sub_id,)
                ).fetchone()
                return self._row_to_subscription(row) if row is not None else None
            finally:
                conn.close()

    def revoke(self, sub_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE subscriptions SET status = 'revoked' WHERE id = ?",
                    (sub_id,),
                )
                conn.commit()
            finally:
                conn.close()

    def delete(self, sub_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
                # R8.4：连带删除该订阅的 delivered_log
                conn.execute(
                    "DELETE FROM delivered_log WHERE subscription_id = ?", (sub_id,)
                )
                conn.commit()
            finally:
                conn.close()

    # ── 去重（Delivered_Log） ────────────────────────────────────
    def is_delivered(self, sub_id: str, fingerprint: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM delivered_log "
                    "WHERE subscription_id = ? AND fingerprint = ?",
                    (sub_id, fingerprint),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def mark_delivered(self, sub_id: str, fingerprint: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                # INSERT OR IGNORE 保证幂等（同一进展重复标记不报错）
                conn.execute(
                    "INSERT OR IGNORE INTO delivered_log "
                    "(subscription_id, fingerprint, delivered_at) VALUES (?, ?, ?)",
                    (sub_id, fingerprint, datetime.now().isoformat()),
                )
                conn.commit()
            finally:
                conn.close()

    # ── 渠道授权 ──────────────────────────────────────────────────
    def set_consent(self, anon_user_id: str, channel: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO channel_consent "
                    "(anon_user_id, channel, consented_at) VALUES (?, ?, ?)",
                    (anon_user_id, channel, datetime.now().isoformat()),
                )
                conn.commit()
            finally:
                conn.close()

    def unset_consent(self, anon_user_id: str, channel: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM channel_consent WHERE anon_user_id = ? AND channel = ?",
                    (anon_user_id, channel),
                )
                conn.commit()
            finally:
                conn.close()

    def list_consents(self, anon_user_id: str) -> list[str]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT channel FROM channel_consent "
                    "WHERE anon_user_id = ? ORDER BY channel",
                    (anon_user_id,),
                ).fetchall()
                return [r["channel"] for r in rows]
            finally:
                conn.close()

    # ── 站内消息 ──────────────────────────────────────────────────
    def add_inapp_message(self, anon_user_id: str, digest_dict: dict) -> str:
        import json

        msg_id = str(uuid.uuid4())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO inapp_messages "
                    "(id, anon_user_id, digest_json, created_at, read) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (
                        msg_id,
                        anon_user_id,
                        json.dumps(digest_dict, ensure_ascii=False),
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return msg_id

    def list_inapp_messages(self, anon_user_id: str) -> list[dict]:
        import json

        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM inapp_messages "
                    "WHERE anon_user_id = ? ORDER BY created_at DESC",
                    (anon_user_id,),
                ).fetchall()
                messages = []
                for r in rows:
                    messages.append(
                        {
                            "id": r["id"],
                            "digest": json.loads(r["digest_json"]),
                            "created_at": r["created_at"],
                            "read": bool(r["read"]),
                        }
                    )
                return messages
            finally:
                conn.close()

    def mark_read(self, msg_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE inapp_messages SET read = 1 WHERE id = ?", (msg_id,)
                )
                conn.commit()
            finally:
                conn.close()

    # ── 删除与保留期 ──────────────────────────────────────────────
    def delete_by_user(self, anon_user_id: str) -> None:
        """删除某匿名用户在本库的全部数据（R8.6）。

        含 subscriptions（及其 delivered_log）、channel_consent、inapp_messages。
        本库删除不依赖 contact_store（R10.4）。
        """
        with self._lock:
            conn = self._connect()
            try:
                # 先取该用户的订阅 id，用于连带删 delivered_log
                sub_ids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM subscriptions WHERE anon_user_id = ?",
                        (anon_user_id,),
                    ).fetchall()
                ]
                for sid in sub_ids:
                    conn.execute(
                        "DELETE FROM delivered_log WHERE subscription_id = ?", (sid,)
                    )
                conn.execute(
                    "DELETE FROM subscriptions WHERE anon_user_id = ?", (anon_user_id,)
                )
                conn.execute(
                    "DELETE FROM channel_consent WHERE anon_user_id = ?", (anon_user_id,)
                )
                conn.execute(
                    "DELETE FROM inapp_messages WHERE anon_user_id = ?", (anon_user_id,)
                )
                conn.commit()
            finally:
                conn.close()

    def purge_expired(self, retention_days: int = RADAR_RETENTION_DAYS) -> int:
        """清理创建时间超过保留期的订阅及其 delivered_log（R10.3）。

        Returns:
            被清理的订阅数量。
        """
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                expired_ids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM subscriptions WHERE created_at < ?", (cutoff,)
                    ).fetchall()
                ]
                for sid in expired_ids:
                    conn.execute(
                        "DELETE FROM delivered_log WHERE subscription_id = ?", (sid,)
                    )
                conn.execute(
                    "DELETE FROM subscriptions WHERE created_at < ?", (cutoff,)
                )
                # 过期站内消息一并清理
                conn.execute(
                    "DELETE FROM inapp_messages WHERE created_at < ?", (cutoff,)
                )
                conn.commit()
                return len(expired_ids)
            finally:
                conn.close()


# ─── 全局单例 ───────────────────────────────────────────────────────────────

subscription_store = SQLiteSubscriptionStore()
