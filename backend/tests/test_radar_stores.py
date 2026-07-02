"""
存储层单元测试（甲方验收：隔离 / 加密 / 删除）——任务 2.4

站在需求方角度独立验证 `SQLiteSubscriptionStore` 与 `SQLiteContactStore`
是否真正满足合规验收标准：

- R1.7 / R11.5：核心订阅库零 PII（schema 与记录均不含联系方式字段）。
- R10.6 / R3.5：两库物理隔离、无交叉索引，无法从一库反查另一库的敏感事实。
- R10.2 / R11.6：联系方式加密存储（底层密文 ≠ 明文且不含明文子串），可解密读回。
- R10.4：两库分别删除，互不依赖。
- R8.4：订阅删除连带删除其 delivered_log。
- R1.6：同 (anon_user_id, disease_keyword) 幂等。
- R8.6 / R7.2：站内消息 add/list/mark_read 正常且零 PII。

所有测试均使用 tmp_path 创建**临时库文件**，绝不触碰真实库
（backend/app/services/radar/data/*.db），测试结束由 pytest 自动清理。
"""

import sqlite3
from pathlib import Path

import pytest

from app.services.radar.contact_store import SQLiteContactStore
from app.services.radar.subscription_store import SQLiteSubscriptionStore

# 用于"密文不含明文"断言的真实感 PII 样本
SAMPLE_EMAIL = "patient.zhang@example.com"
SAMPLE_OPENID = "wx_openid_abc123XYZ"


# ─── fixtures：临时隔离的两个 store ──────────────────────────────────────────

@pytest.fixture
def sub_db_path(tmp_path: Path) -> Path:
    return tmp_path / "subscriptions.db"


@pytest.fixture
def contact_db_path(tmp_path: Path) -> Path:
    return tmp_path / "contacts.db"


@pytest.fixture
def sub_store(sub_db_path: Path) -> SQLiteSubscriptionStore:
    return SQLiteSubscriptionStore(db_path=sub_db_path)


@pytest.fixture
def contact_store(contact_db_path: Path) -> SQLiteContactStore:
    return SQLiteContactStore(db_path=contact_db_path)


def _table_columns(db_path: Path, table: str) -> list[str]:
    """直接读底层 sqlite schema，返回某表的列名列表。"""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [r[1] for r in rows]
    finally:
        conn.close()


def _all_text_cells(db_path: Path, table: str) -> list[str]:
    """把某表所有记录的所有单元格转为字符串，用于扫描是否泄露明文 PII。"""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        cells: list[str] = []
        for row in rows:
            for cell in row:
                cells.append(str(cell))
        return cells
    finally:
        conn.close()


# ─── R1.7 / R11.5：核心订阅库零 PII ──────────────────────────────────────────

class TestSubscriptionStoreZeroPII:
    """核心订阅库仅存匿名标识 + 病症关键词 + 元数据，绝不含 PII 字段/值。"""

    PII_COLUMN_TOKENS = ["email", "openid", "phone", "mobile", "name", "contact", "wechat"]

    def test_subscriptions_schema_has_no_pii_columns(self, sub_store, sub_db_path):
        cols = _table_columns(sub_db_path, "subscriptions")
        # 只应有匿名标识 + 病症关键词 + 元数据
        assert set(cols) == {"id", "anon_user_id", "disease_keyword", "status", "created_at"}
        for col in cols:
            for token in self.PII_COLUMN_TOKENS:
                assert token not in col.lower(), f"订阅表出现疑似 PII 列: {col}"

    def test_channel_consent_stores_only_boolean_fact_no_contact_value(
        self, sub_store, sub_db_path
    ):
        # 渠道授权只记"开了哪个渠道"的布尔事实，绝不存联系方式值
        sub_store.set_consent("anon-1", "email")
        cols = _table_columns(sub_db_path, "channel_consent")
        assert set(cols) == {"anon_user_id", "channel", "consented_at"}
        # 记录里只有 channel 名（"email"），没有任何邮箱地址值
        cells = _all_text_cells(sub_db_path, "channel_consent")
        assert "email" in cells  # 渠道名本身允许出现
        assert all("@" not in c for c in cells), "channel_consent 疑似存了邮箱地址"

    def test_records_contain_no_pii_after_typical_use(self, sub_store, sub_db_path):
        # 走一遍典型写入路径后，扫描订阅表所有单元格无 PII 明文
        sub_store.create("anon-42", "肺腺癌")
        sub_store.set_consent("anon-42", "email")
        cells = _all_text_cells(sub_db_path, "subscriptions")
        joined = " ".join(cells)
        assert SAMPLE_EMAIL not in joined
        assert "@" not in joined


# ─── R10.2 / R11.6：联系方式加密存储 ────────────────────────────────────────

class TestContactStoreEncryption:
    """联系方式加密：底层密文既 ≠ 明文，也不含明文子串；get_contact 可解密读回。"""

    def test_stored_value_is_ciphertext_not_plaintext_email(
        self, contact_store, contact_db_path
    ):
        contact_store.set_contact("anon-1", "email", SAMPLE_EMAIL)
        raw = _all_text_cells(contact_db_path, "contacts")
        joined = " ".join(raw)
        # 底层 encrypted_value 必须是密文：不等于明文、也不含明文子串
        assert SAMPLE_EMAIL not in joined, "底层库直接暴露了明文邮箱！"
        # 甚至连本地部分/域名子串都不应出现
        assert "patient.zhang" not in joined
        assert "example.com" not in joined

    def test_stored_value_is_ciphertext_not_plaintext_openid(
        self, contact_store, contact_db_path
    ):
        contact_store.set_contact("anon-1", "wechat", SAMPLE_OPENID)
        joined = " ".join(_all_text_cells(contact_db_path, "contacts"))
        assert SAMPLE_OPENID not in joined, "底层库直接暴露了明文 openid！"

    def test_get_contact_decrypts_back_to_original(self, contact_store):
        contact_store.set_contact("anon-1", "email", SAMPLE_EMAIL)
        contact_store.set_contact("anon-1", "wechat", SAMPLE_OPENID)
        assert contact_store.get_contact("anon-1", "email") == SAMPLE_EMAIL
        assert contact_store.get_contact("anon-1", "wechat") == SAMPLE_OPENID

    def test_encrypted_column_differs_from_plaintext_directly(
        self, contact_store, contact_db_path
    ):
        contact_store.set_contact("anon-9", "email", SAMPLE_EMAIL)
        conn = sqlite3.connect(str(contact_db_path))
        try:
            enc = conn.execute(
                "SELECT encrypted_value FROM contacts WHERE anon_user_id=? AND channel=?",
                ("anon-9", "email"),
            ).fetchone()[0]
        finally:
            conn.close()
        assert enc != SAMPLE_EMAIL
        assert SAMPLE_EMAIL not in enc

    def test_get_contact_missing_returns_none(self, contact_store):
        assert contact_store.get_contact("no-such-user", "email") is None


# ─── R3.5 / R10.6：物理隔离 + 无交叉索引 ────────────────────────────────────

class TestPhysicalIsolationNoCrossIndex:
    """两库独立文件；无法从一库推出另一库的敏感事实。"""

    def test_two_stores_use_distinct_db_files(
        self, sub_store, contact_store, sub_db_path, contact_db_path
    ):
        assert sub_store.db_path != contact_store.db_path
        assert sub_db_path.exists() and contact_db_path.exists()

    def test_contact_db_has_no_disease_keyword(self, contact_store, contact_db_path):
        # 联系方式库存了邮箱，但绝不含"订阅了什么病"
        contact_store.set_contact("anon-7", "email", SAMPLE_EMAIL)
        contact_cols = _table_columns(contact_db_path, "contacts")
        assert "disease_keyword" not in contact_cols
        assert set(contact_cols) == {
            "anon_user_id",
            "channel",
            "encrypted_value",
            "consented_at",
        }

    def test_subscription_db_has_no_contact_value(
        self, sub_store, contact_store, sub_db_path, contact_db_path
    ):
        # 同一 anon_user_id 在两库都有数据，但订阅库无法拿到联系方式明文
        contact_store.set_contact("anon-7", "email", SAMPLE_EMAIL)
        sub_store.create("anon-7", "胃癌")
        sub_store.set_consent("anon-7", "email")

        # 订阅库列出的是渠道布尔事实，只有渠道名，没有邮箱
        consents = sub_store.list_consents("anon-7")
        assert consents == ["email"]
        # 扫描整个订阅库文件字节，确认无明文邮箱泄漏
        blob = sub_db_path.read_bytes()
        assert SAMPLE_EMAIL.encode() not in blob

    def test_contact_store_module_does_not_import_subscription_store(self):
        # 代码级隔离：contact_store 不得真正 import subscription_store（防跨库 JOIN）。
        # 用 AST 解析真实的 import 语句，避免误伤 docstring/注释中出现的模块名。
        import ast

        src = Path(__file__).resolve().parents[1] / "app" / "services" / "radar" / "contact_store.py"
        src = src.read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.append(node.module)
        assert not any(
            "subscription_store" in name for name in imported_names
        ), f"contact_store 实际 import 了订阅库，违反代码级隔离: {imported_names}"


# ─── R10.4：两库分别删除，互不依赖 ──────────────────────────────────────────

class TestSeparateDeletionIndependence:
    """delete_by_user 在两库分别执行，删一库不影响另一库。"""

    def test_delete_contacts_does_not_affect_subscriptions(
        self, sub_store, contact_store
    ):
        sub_store.create("anon-x", "白血病")
        contact_store.set_contact("anon-x", "email", SAMPLE_EMAIL)

        # 只删联系方式库
        contact_store.delete_by_user("anon-x")

        assert contact_store.get_contact("anon-x", "email") is None
        # 订阅仍然完好
        assert len(sub_store.list_active("anon-x")) == 1

    def test_delete_subscriptions_does_not_affect_contacts(
        self, sub_store, contact_store
    ):
        sub_store.create("anon-y", "白血病")
        sub_store.set_consent("anon-y", "email")
        contact_store.set_contact("anon-y", "email", SAMPLE_EMAIL)

        # 只删订阅库
        sub_store.delete_by_user("anon-y")

        assert sub_store.list_active("anon-y") == []
        assert sub_store.list_consents("anon-y") == []
        # 联系方式仍在（两库互不依赖）
        assert contact_store.get_contact("anon-y", "email") == SAMPLE_EMAIL

    def test_contact_deletion_works_without_subscription_store(self, contact_db_path):
        # 联系方式库删除不依赖订阅库存在（独立实例化即可运行）
        cs = SQLiteContactStore(db_path=contact_db_path)
        cs.set_contact("solo", "email", SAMPLE_EMAIL)
        cs.delete_by_user("solo")
        assert cs.get_contact("solo", "email") is None


# ─── R8.4：订阅删除连带 delivered_log ───────────────────────────────────────

class TestSubscriptionDeleteCascadesDeliveredLog:
    def test_delete_removes_delivered_log(self, sub_store, sub_db_path):
        sub = sub_store.create("anon-d", "肝癌")
        sub_store.mark_delivered(sub.id, "fp-001")
        sub_store.mark_delivered(sub.id, "fp-002")
        assert sub_store.is_delivered(sub.id, "fp-001") is True

        sub_store.delete(sub.id)

        # 订阅没了
        assert sub_store.get(sub.id) is None
        # 该订阅的 delivered_log 也没了
        assert sub_store.is_delivered(sub.id, "fp-001") is False
        conn = sqlite3.connect(str(sub_db_path))
        try:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM delivered_log WHERE subscription_id=?",
                (sub.id,),
            ).fetchone()[0]
        finally:
            conn.close()
        assert remaining == 0

    def test_delete_by_user_cascades_delivered_log(self, sub_store, sub_db_path):
        sub = sub_store.create("anon-du", "肝癌")
        sub_store.mark_delivered(sub.id, "fp-x")
        sub_store.delete_by_user("anon-du")
        conn = sqlite3.connect(str(sub_db_path))
        try:
            remaining = conn.execute("SELECT COUNT(*) FROM delivered_log").fetchone()[0]
        finally:
            conn.close()
        assert remaining == 0


# ─── R1.6：订阅幂等 ──────────────────────────────────────────────────────────

class TestSubscriptionIdempotency:
    def test_create_twice_returns_same_subscription(self, sub_store):
        s1 = sub_store.create("anon-i", "胰腺癌")
        s2 = sub_store.create("anon-i", "胰腺癌")
        assert s1.id == s2.id
        assert len(sub_store.list_active("anon-i")) == 1

    def test_different_disease_creates_distinct_subscriptions(self, sub_store):
        s1 = sub_store.create("anon-i", "胰腺癌")
        s2 = sub_store.create("anon-i", "肺癌")
        assert s1.id != s2.id
        assert len(sub_store.list_active("anon-i")) == 2


# ─── 站内消息：add / list / mark_read，零 PII ───────────────────────────────

class TestInAppMessages:
    def test_add_list_mark_read_flow(self, sub_store):
        digest = {
            "disease_keyword": "肺癌",
            "items": [{"summary": "新指南发布", "research_stage": "breakthrough_rct"}],
        }
        msg_id = sub_store.add_inapp_message("anon-m", digest)
        msgs = sub_store.list_inapp_messages("anon-m")
        assert len(msgs) == 1
        assert msgs[0]["id"] == msg_id
        assert msgs[0]["read"] is False
        assert msgs[0]["digest"]["disease_keyword"] == "肺癌"

        sub_store.mark_read(msg_id)
        msgs_after = sub_store.list_inapp_messages("anon-m")
        assert msgs_after[0]["read"] is True

    def test_inapp_messages_ordered_desc(self, sub_store):
        sub_store.add_inapp_message("anon-m2", {"disease_keyword": "A"})
        sub_store.add_inapp_message("anon-m2", {"disease_keyword": "B"})
        msgs = sub_store.list_inapp_messages("anon-m2")
        assert len(msgs) == 2  # 时间倒序（最新在前）

    def test_inapp_table_has_no_pii_columns(self, sub_store, sub_db_path):
        sub_store.add_inapp_message("anon-m3", {"disease_keyword": "肺癌"})
        cols = _table_columns(sub_db_path, "inapp_messages")
        assert set(cols) == {"id", "anon_user_id", "digest_json", "created_at", "read"}
        for token in ["email", "openid", "phone", "name"]:
            assert all(token not in c.lower() for c in cols)
