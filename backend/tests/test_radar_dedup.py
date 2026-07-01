"""
甲方验收测试（任务 3.3）：去重幂等单元测试

站在需求方角度独立验证 `SQLiteSubscriptionStore` 的 Delivered_Log 去重逻辑：

- R5.3：is_delivered——已 mark 的 fingerprint 返回 True；未推过返回 False。
- R5.4：mark_delivered 幂等——同一 fingerprint 重复标记不报错、不重复写入。
- 组合场景：模拟"同一进展重复巡检"——由 progress_fingerprint 算出指纹，
  首次未推(False) → mark → 再次 is_delivered=True（不会重复推送）。

全部使用 tmp_path 临时库，绝不触碰真实库，测试结束由 pytest 自动清理。
"""

import sqlite3
from pathlib import Path

import pytest

from app.services.radar.fingerprint import progress_fingerprint
from app.services.radar.subscription_store import SQLiteSubscriptionStore


@pytest.fixture
def sub_store(tmp_path: Path) -> SQLiteSubscriptionStore:
    """基于临时库文件的订阅库，隔离且用后即弃。"""
    return SQLiteSubscriptionStore(db_path=tmp_path / "subscriptions.db")


# ─── R5.3：is_delivered 基本语义 ─────────────────────────────────────────────

class TestIsDelivered:
    def test_unmarked_fingerprint_is_not_delivered(self, sub_store):
        sub = sub_store.create("anon-1", "肺癌")
        assert sub_store.is_delivered(sub.id, "fp-never-pushed") is False

    def test_marked_fingerprint_is_delivered(self, sub_store):
        sub = sub_store.create("anon-1", "肺癌")
        sub_store.mark_delivered(sub.id, "fp-abc")
        assert sub_store.is_delivered(sub.id, "fp-abc") is True

    def test_is_delivered_is_scoped_per_subscription(self, sub_store):
        """同一 fingerprint 对不同订阅相互独立（不串台）。"""
        s1 = sub_store.create("anon-1", "肺癌")
        s2 = sub_store.create("anon-2", "胃癌")
        sub_store.mark_delivered(s1.id, "fp-shared")
        assert sub_store.is_delivered(s1.id, "fp-shared") is True
        assert sub_store.is_delivered(s2.id, "fp-shared") is False


# ─── R5.4：mark_delivered 幂等 ───────────────────────────────────────────────

class TestMarkDeliveredIdempotent:
    def test_repeated_mark_does_not_raise(self, sub_store):
        sub = sub_store.create("anon-1", "肺癌")
        # 重复标记同一指纹多次，不应抛错
        for _ in range(5):
            sub_store.mark_delivered(sub.id, "fp-dup")
        assert sub_store.is_delivered(sub.id, "fp-dup") is True

    def test_repeated_mark_does_not_create_duplicate_rows(self, sub_store, tmp_path):
        sub = sub_store.create("anon-1", "肺癌")
        sub_store.mark_delivered(sub.id, "fp-once")
        sub_store.mark_delivered(sub.id, "fp-once")
        sub_store.mark_delivered(sub.id, "fp-once")

        conn = sqlite3.connect(str(sub_store.db_path))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM delivered_log "
                "WHERE subscription_id=? AND fingerprint=?",
                (sub.id, "fp-once"),
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1, f"重复 mark 产生了 {count} 行，应恰好 1 行"


# ─── 组合场景：同一进展重复巡检不会重复推送 ─────────────────────────────────

class TestRepeatedPatrolNoDoubleDelivery:
    def test_same_progress_across_patrols_delivered_once(self, sub_store):
        """
        模拟"同一进展在两次巡检中都出现"：
        1) 由 evidence 算出 fingerprint；
        2) 首次巡检：is_delivered=False → 推送 → mark_delivered；
        3) 二次巡检：同一 evidence 算出相同 fingerprint → is_delivered=True → 跳过。
        """
        sub = sub_store.create("anon-patrol", "黑色素瘤")

        evidence = {
            "nct_id": "NCT12345678",
            "title": "新型免疫疗法 III 期临床试验",
            "source_type": "trial",
            "evidence_level": "high",
            "publish_date": "2024-06-10",
        }

        # 第一次巡检
        fp1 = progress_fingerprint(evidence)
        assert sub_store.is_delivered(sub.id, fp1) is False  # 首次未推
        sub_store.mark_delivered(sub.id, fp1)

        # 第二次巡检：同一进展，指纹稳定不变
        fp2 = progress_fingerprint(dict(evidence))
        assert fp2 == fp1
        assert sub_store.is_delivered(sub.id, fp2) is True  # 已推，跳过

    def test_only_one_delivered_row_after_repeated_patrols(self, sub_store):
        """多轮巡检对同一进展只应留下一条 delivered 记录。"""
        sub = sub_store.create("anon-patrol2", "肺腺癌")
        evidence = {"doi": "10.1000/j.abc.2024.06", "source_type": "guide", "evidence_level": "moderate"}

        fp = progress_fingerprint(evidence)
        # 模拟 3 轮巡检，每轮先判定再（幂等）标记
        for _ in range(3):
            if not sub_store.is_delivered(sub.id, fp):
                # 只有首轮会进这里执行"推送"
                pass
            sub_store.mark_delivered(sub.id, fp)

        conn = sqlite3.connect(str(sub_store.db_path))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM delivered_log WHERE subscription_id=?",
                (sub.id,),
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1

    def test_distinct_progress_tracked_separately(self, sub_store):
        """不同进展指纹各自独立去重，互不影响。"""
        sub = sub_store.create("anon-patrol3", "乳腺癌")
        ev_a = {"nct_id": "NCT-A"}
        ev_b = {"nct_id": "NCT-B"}
        fp_a = progress_fingerprint(ev_a)
        fp_b = progress_fingerprint(ev_b)

        sub_store.mark_delivered(sub.id, fp_a)
        assert sub_store.is_delivered(sub.id, fp_a) is True
        assert sub_store.is_delivered(sub.id, fp_b) is False  # B 尚未推送
