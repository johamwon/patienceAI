"""
联系方式库（Contact_Store）——物理隔离 + 加密存储 PII。

生克隔离核心（对应需求 R3.5 / R10.2 / R10.6 / R11.6）：本库与订阅库
（`subscription_store` 的 subscriptions.db）**物理隔离**：
- 独立的 SQLite 文件 `contacts.db`、独立连接。
- 本模块**绝不 import subscription_store**，也**绝不做任何跨库 JOIN / 联合查询**。
- 即便同时拿到两库，也只能各自看到"某匿名用户开了邮件渠道"（订阅库的
  channel_consent 布尔事实）与"某加密联系方式"（本库），无法反查
  "某邮箱订阅了什么病"。

加密（R10.2 / R11.6）：`encrypted_value` 用 `cryptography` 的 Fernet 对称加密，
加解密逻辑集中在本模块。密钥来自环境变量 `RADAR_SECRET_KEY`；若未设置，
则从固定 salt 派生一个**开发默认密钥**并打印 warning——生产环境必须显式配置。

设计沿用 `subscription_store.py` 的风格：抽象基类（预留未来其他实现）+
标准库 sqlite3 + threading.Lock 并发保护 + 每次操作独立连接 + 全局单例。

- R3.5 / R10.6：与订阅库物理与代码双重隔离，禁止交叉索引。
- R8.5：关闭渠道时删除该渠道联系方式（delete_contact）。
- R8.6 / R10.4：按 anon_user_id 删除该用户全部联系方式（delete_by_user），
  两库分别删，删本库不依赖订阅库可用。
- R10.2 / R11.6：加密存储，明文仅在调用方本次投递时经 get_contact 解密取用。
"""

import base64
import hashlib
import logging
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# 默认库文件：backend/app/services/radar/data/contacts.db（与 subscriptions.db 同目录，
# 但为独立文件、独立连接——物理隔离）。目录自动创建。
DEFAULT_DB_PATH = Path(__file__).parent / "data" / "contacts.db"

# R10.3：数据保留期（天），可配置，默认 365 天（与订阅库保持一致的默认）。
RADAR_RETENTION_DAYS = int(os.getenv("RADAR_RETENTION_DAYS", "365"))

# 开发默认密钥派生用的固定 salt（仅用于未配置 RADAR_SECRET_KEY 的开发场景）。
_DEV_KEY_SALT = b"patienceai-radar-contact-store-dev-salt-v1"


def _load_fernet() -> Fernet:
    """构造 Fernet 加解密器。

    密钥来源优先级：
    1. 环境变量 `RADAR_SECRET_KEY`：既可以是标准的 44 字节 urlsafe-base64 Fernet
       密钥，也可以是任意口令（后者会经 SHA-256 派生为合法 Fernet 密钥）。
    2. 未设置时：从固定 salt 派生一个开发默认密钥，并打印 warning 提示生产必须配置。
    """
    secret = os.getenv("RADAR_SECRET_KEY")
    if secret:
        return Fernet(_derive_fernet_key(secret.encode("utf-8")))

    logger.warning(
        "RADAR_SECRET_KEY 未设置，Contact_Store 正在使用从固定 salt 派生的开发默认"
        "密钥。这仅适用于本地开发，生产环境必须显式配置 RADAR_SECRET_KEY 以保护 PII。"
    )
    return Fernet(_derive_fernet_key(_DEV_KEY_SALT))


def _derive_fernet_key(material: bytes) -> bytes:
    """把任意密钥材料经 SHA-256 派生为合法的 32 字节 urlsafe-base64 Fernet 密钥。"""
    digest = hashlib.sha256(material).digest()  # 32 bytes
    return base64.urlsafe_b64encode(digest)


class ContactStore(ABC):
    """联系方式库抽象基类。

    预留未来其他持久化实现的扩展点（沿用 subscription_store 的抽象模式）。
    所有存储的联系方式一律加密；读取接口返回解密后的明文，仅供调用方本次投递使用。
    """

    @abstractmethod
    def set_contact(self, anon_user_id: str, channel: str, plain_value: str) -> None:
        """加密并 upsert 某匿名用户某渠道的联系方式（R3.3/R3.4/R10.2）。"""
        ...

    @abstractmethod
    def get_contact(self, anon_user_id: str, channel: str) -> Optional[str]:
        """解密返回联系方式明文（仅本次投递用，R7.3）；不存在或解密失败返回 None。"""
        ...

    @abstractmethod
    def delete_contact(self, anon_user_id: str, channel: str) -> None:
        """删除某匿名用户某渠道的联系方式（R8.5，关闭渠道时调用）。"""
        ...

    @abstractmethod
    def delete_by_user(self, anon_user_id: str) -> None:
        """删除某匿名用户在本库的全部联系方式（R8.6/R10.4）。"""
        ...

    @abstractmethod
    def purge_expired(self, retention_days: int = RADAR_RETENTION_DAYS) -> int:
        """清理超过保留期的联系方式（R10.3），返回清理条数。"""
        ...


class SQLiteContactStore(ContactStore):
    """基于标准库 sqlite3 的联系方式库实现（隔离 + Fernet 加密）。

    - 独立单文件 SQLite（默认 contacts.db），与 subscriptions.db 物理隔离。
    - threading.Lock 保护并发（沿用 subscription_store 模式）。
    - 每次操作使用独立连接，避免跨线程共享连接的问题。
    - 加解密逻辑集中在本类，密钥经 `_load_fernet` 加载。
    """

    def __init__(self, db_path: Optional[Path | str] = None):
        """构造联系方式库。

        Args:
            db_path: 库文件路径；默认 contacts.db。测试可传临时库路径。
        """
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self._lock = threading.Lock()
        self._fernet = _load_fernet()
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
                    CREATE TABLE IF NOT EXISTS contacts (
                        anon_user_id    TEXT NOT NULL,
                        channel         TEXT NOT NULL,
                        encrypted_value TEXT NOT NULL,
                        consented_at    TEXT NOT NULL,
                        PRIMARY KEY (anon_user_id, channel)
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

    # ── 加解密（集中在本模块，R10.2/R11.6） ──────────────────────
    def _encrypt(self, plain_value: str) -> str:
        token = self._fernet.encrypt(plain_value.encode("utf-8"))
        return token.decode("utf-8")

    def _decrypt(self, encrypted_value: str) -> Optional[str]:
        """解密；失败安全处理（返回 None + 记录，不抛崩）。"""
        try:
            return self._fernet.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            # 密钥轮换 / 数据损坏 / 密钥不匹配等：安全降级为 None，交由上层跳过该渠道。
            logger.warning("Contact_Store 解密失败，跳过该联系方式：%s", type(exc).__name__)
            return None

    # ── 写入 / 读取 / 删除 ────────────────────────────────────────
    def set_contact(self, anon_user_id: str, channel: str, plain_value: str) -> None:
        encrypted = self._encrypt(plain_value)
        with self._lock:
            conn = self._connect()
            try:
                # upsert：同一 (user, channel) 覆盖为最新加密值与授权时间。
                conn.execute(
                    "INSERT INTO contacts "
                    "(anon_user_id, channel, encrypted_value, consented_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(anon_user_id, channel) DO UPDATE SET "
                    "encrypted_value = excluded.encrypted_value, "
                    "consented_at = excluded.consented_at",
                    (anon_user_id, channel, encrypted, datetime.now().isoformat()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_contact(self, anon_user_id: str, channel: str) -> Optional[str]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT encrypted_value FROM contacts "
                    "WHERE anon_user_id = ? AND channel = ?",
                    (anon_user_id, channel),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        return self._decrypt(row["encrypted_value"])

    def delete_contact(self, anon_user_id: str, channel: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM contacts WHERE anon_user_id = ? AND channel = ?",
                    (anon_user_id, channel),
                )
                conn.commit()
            finally:
                conn.close()

    def delete_by_user(self, anon_user_id: str) -> None:
        """删除某匿名用户在本库的全部联系方式（R8.6/R10.4）。

        本库删除不依赖 subscription_store 的可用性——两库物理与代码双重隔离。
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM contacts WHERE anon_user_id = ?", (anon_user_id,)
                )
                conn.commit()
            finally:
                conn.close()

    def purge_expired(self, retention_days: int = RADAR_RETENTION_DAYS) -> int:
        """清理授权时间超过保留期的联系方式（R10.3），返回清理条数。"""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM contacts WHERE consented_at < ?", (cutoff,)
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()


# ─── 全局单例 ───────────────────────────────────────────────────────────────

contact_store = SQLiteContactStore()
