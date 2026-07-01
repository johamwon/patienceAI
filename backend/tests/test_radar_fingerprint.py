"""
甲方验收测试（任务 3.2）：Progress_Fingerprint 属性测试 + is_new_progress 单元测试

站在需求方角度独立验证 `app.services.radar.fingerprint` 的纯逻辑是否满足：

- R5.2：Progress_Fingerprint 稳定去重键——同一 evidence 幂等；优先级
  nct_id > doi > pmid；三者都缺失回退 sha1(title|source_type|publish_date)。
- R5.1：is_new_progress 新进展判定——质量达标（evidence_level high/moderate
  或 source_type guide/trial/meeting）且新鲜（publish_date 落在近
  RADAR_FRESH_DAYS 天内）。
- R5.6：阈值参数（RADAR_FRESH_DAYS 等）可配置。

属性测试用 hypothesis；is_new_progress 用 now 参数注入固定"当前时间"做确定性断言。
"""

import hashlib
from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.radar.fingerprint import (
    RADAR_FRESH_DAYS,
    is_new_progress,
    progress_fingerprint,
)

# 固定注入的"当前时间"，让新鲜度断言完全确定。
NOW = datetime(2024, 6, 15, 12, 0, 0)


def _iso(d) -> str:
    return d.date().isoformat() if isinstance(d, datetime) else d.isoformat()


# 生成非空、去空白后仍非空的字符串（用作 nct/doi/pmid/title 等标识）。
_nonblank_text = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")


# ─── R5.2：progress_fingerprint 属性测试 ─────────────────────────────────────

class TestFingerprintProperties:
    @given(
        nct=st.one_of(st.none(), _nonblank_text),
        doi=st.one_of(st.none(), _nonblank_text),
        pmid=st.one_of(st.none(), _nonblank_text),
        title=st.text(max_size=40),
        source_type=st.text(max_size=20),
        publish_date=st.one_of(st.none(), _nonblank_text),
    )
    @settings(max_examples=200)
    def test_idempotent_same_evidence_same_key(
        self, nct, doi, pmid, title, source_type, publish_date
    ):
        """同一 evidence 多次调用 progress_fingerprint 返回相同键（幂等）。"""
        evidence = {
            "nct_id": nct,
            "doi": doi,
            "pmid": pmid,
            "title": title,
            "source_type": source_type,
            "publish_date": publish_date,
        }
        k1 = progress_fingerprint(evidence)
        k2 = progress_fingerprint(evidence)
        k3 = progress_fingerprint(dict(evidence))
        assert k1 == k2 == k3
        assert isinstance(k1, str) and k1 != ""

    @given(
        nct=_nonblank_text,
        doi=st.one_of(st.none(), _nonblank_text),
        pmid=st.one_of(st.none(), _nonblank_text),
        title=st.text(max_size=40),
        source_type=st.text(max_size=20),
        publish_date=st.one_of(st.none(), _nonblank_text),
    )
    @settings(max_examples=200)
    def test_nct_takes_priority_and_is_stable(
        self, nct, doi, pmid, title, source_type, publish_date
    ):
        """含 nct_id 时键以 nct 优先，且不受 doi/pmid/title/date 变化影响。"""
        base = {
            "nct_id": nct,
            "doi": doi,
            "pmid": pmid,
            "title": title,
            "source_type": source_type,
            "publish_date": publish_date,
        }
        assert progress_fingerprint(base) == f"nct:{nct.strip()}"

        # 变动 nct 以外的所有字段，键应保持不变（nct 主导）。
        mutated = {
            "nct_id": nct,
            "doi": (doi or "") + "-CHANGED",
            "pmid": (pmid or "") + "999",
            "title": title + "_x",
            "source_type": source_type + "_y",
            "publish_date": "2099-01-01",
        }
        assert progress_fingerprint(mutated) == f"nct:{nct.strip()}"

    @given(
        doi=_nonblank_text,
        pmid=st.one_of(st.none(), _nonblank_text),
        title=st.text(max_size=40),
        source_type=st.text(max_size=20),
    )
    @settings(max_examples=200)
    def test_doi_used_when_nct_missing(self, doi, pmid, title, source_type):
        """nct 缺失但有 doi 时用 doi（优先于 pmid 与回退指纹）。"""
        for missing_nct in (None, "", "   "):
            evidence = {
                "nct_id": missing_nct,
                "doi": doi,
                "pmid": pmid,
                "title": title,
                "source_type": source_type,
            }
            assert progress_fingerprint(evidence) == f"doi:{doi.strip()}"

    @given(
        pmid=_nonblank_text,
        title=st.text(max_size=40),
        source_type=st.text(max_size=20),
    )
    @settings(max_examples=100)
    def test_pmid_used_when_nct_and_doi_missing(self, pmid, title, source_type):
        """nct 与 doi 都缺失但有 pmid 时用 pmid。"""
        evidence = {
            "nct_id": None,
            "doi": "  ",
            "pmid": pmid,
            "title": title,
            "source_type": source_type,
        }
        assert progress_fingerprint(evidence) == f"pmid:{pmid.strip()}"

    @given(
        title=st.text(max_size=40),
        source_type=st.text(max_size=20),
        publish_date=st.one_of(st.none(), _nonblank_text),
    )
    @settings(max_examples=200)
    def test_fallback_sha1_when_all_ids_missing(self, title, source_type, publish_date):
        """nct/doi/pmid 都缺失时走 sha1(title|source_type|publish_date) 指纹。"""
        evidence = {
            "nct_id": None,
            "doi": None,
            "pmid": None,
            "title": title,
            "source_type": source_type,
            "publish_date": publish_date,
        }
        norm_date = publish_date.strip() if isinstance(publish_date, str) else ""
        raw = f"{title.strip()}|{source_type.strip()}|{norm_date}"
        expected = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        key = progress_fingerprint(evidence)
        assert key == expected
        # 回退键是 40 位 sha1 十六进制，且不带 nct/doi/pmid 前缀
        assert len(key) == 40
        assert ":" not in key


class TestFingerprintRobustness:
    def test_non_dict_input_does_not_raise(self):
        """非 dict 输入安全处理，不抛异常。"""
        for bad in (None, "x", 123, [], object()):
            key = progress_fingerprint(bad)
            assert isinstance(key, str) and key != ""

    def test_exact_priority_order_nct_over_doi_over_pmid(self):
        """三者齐备时严格 nct > doi > pmid。"""
        ev = {"nct_id": "NCT01", "doi": "10.1/x", "pmid": "123"}
        assert progress_fingerprint(ev) == "nct:NCT01"
        assert progress_fingerprint({"doi": "10.1/x", "pmid": "123"}) == "doi:10.1/x"
        assert progress_fingerprint({"pmid": "123"}) == "pmid:123"


# ─── R5.1 / R5.6：is_new_progress 单元测试（注入固定 now） ────────────────────

def _fresh_date_str(days_ago: int) -> str:
    return _iso(NOW - timedelta(days=days_ago))


class TestIsNewProgressQuality:
    def test_high_level_and_fresh_is_true(self):
        ev = {"evidence_level": "high", "source_type": "journal", "publish_date": _fresh_date_str(1)}
        assert is_new_progress(ev, now=NOW) is True

    def test_moderate_level_and_fresh_is_true(self):
        ev = {"evidence_level": "moderate", "source_type": "journal", "publish_date": _fresh_date_str(5)}
        assert is_new_progress(ev, now=NOW) is True

    def test_guide_source_and_fresh_is_true(self):
        ev = {"evidence_level": "low", "source_type": "guide", "publish_date": _fresh_date_str(2)}
        assert is_new_progress(ev, now=NOW) is True

    def test_trial_source_and_fresh_is_true(self):
        ev = {"evidence_level": "very_low", "source_type": "trial", "publish_date": _fresh_date_str(2)}
        assert is_new_progress(ev, now=NOW) is True

    def test_meeting_source_and_fresh_is_true(self):
        ev = {"evidence_level": "low", "source_type": "meeting", "publish_date": _fresh_date_str(3)}
        assert is_new_progress(ev, now=NOW) is True

    def test_low_level_and_non_fresh_source_is_false(self):
        ev = {"evidence_level": "low", "source_type": "journal", "publish_date": _fresh_date_str(1)}
        assert is_new_progress(ev, now=NOW) is False

    def test_very_low_level_and_non_fresh_source_is_false(self):
        ev = {"evidence_level": "very_low", "source_type": "blog", "publish_date": _fresh_date_str(1)}
        assert is_new_progress(ev, now=NOW) is False


class TestIsNewProgressFreshness:
    def test_older_than_fresh_window_is_false(self):
        """publish_date 超过 RADAR_FRESH_DAYS 天 → False，即使质量达标。"""
        ev = {
            "evidence_level": "high",
            "source_type": "guide",
            "publish_date": _fresh_date_str(RADAR_FRESH_DAYS + 1),
        }
        assert is_new_progress(ev, now=NOW) is False

    def test_exactly_on_window_boundary_is_true(self):
        """恰好第 RADAR_FRESH_DAYS 天仍视为新鲜（边界包含）。"""
        ev = {
            "evidence_level": "high",
            "source_type": "guide",
            "publish_date": _fresh_date_str(RADAR_FRESH_DAYS),
        }
        assert is_new_progress(ev, now=NOW) is True

    def test_missing_publish_date_is_false(self):
        """无 publish_date → 不新鲜 → False。"""
        ev = {"evidence_level": "high", "source_type": "guide"}
        assert is_new_progress(ev, now=NOW) is False
        ev_none = {"evidence_level": "high", "source_type": "guide", "publish_date": None}
        assert is_new_progress(ev_none, now=NOW) is False

    def test_unparseable_publish_date_is_false(self):
        ev = {"evidence_level": "high", "source_type": "guide", "publish_date": "not-a-date"}
        assert is_new_progress(ev, now=NOW) is False


class TestIsNewProgressRobustness:
    def test_non_dict_input_is_false(self):
        for bad in (None, "x", 123, []):
            assert is_new_progress(bad, now=NOW) is False

    def test_empty_dict_is_false(self):
        assert is_new_progress({}, now=NOW) is False
