"""
任务 5.4：select_sources / sort_evidences 单元测试

从需求方（甲方）视角验收 Requirement 10 的以下验收标准（纯函数层）：
- R10.1: rare_disease 或 severe_condition 为 True 时，优先选择 trial、meeting、paper_en 源。
- R10.2: 罕见病/重症查询的结果按发表时间降序排序，最新在前；缺失日期排最后。
- R10.3: 罕见病/重症检索策略生效时，源集合保留至少一类指南/权威源（guide）做交叉佐证。
- R10.4: 罕见病/重症专门源无结果时回退默认源（发生在路由内部，依赖 knows_client；
         纯函数层难以直接覆盖，见文件末尾说明，由集成测试覆盖）。

只验证现有实现行为，不修改实现。
select_sources / sort_evidences 均为纯函数，直接 import 测试。
"""

from datetime import date

import pytest

from backend.app.api.search import (
    select_sources,
    sort_evidences,
    _publish_date_sort_key,
    DEFAULT_SOURCES,
    INTENT_TO_SOURCES,
    LATEST_RESEARCH_SOURCES,
    RARE_SEVERE_SOURCES,
)
from backend.app.services.answer_alignment import analyze_query_focus
from backend.app.models.schemas import Evidence


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：构造 parsed dict（intent_classifier.parse_query 的简化形态）
# ─────────────────────────────────────────────────────────────────────────────

def make_parsed(*, rare=False, severe=False, intent="unknown"):
    return {"rare_disease": rare, "severe_condition": severe, "intent": intent}


def make_dict_evidence(eid, publish_date):
    return {"id": eid, "title": f"标题-{eid}", "publish_date": publish_date}


def make_obj_evidence(eid, publish_date):
    return Evidence(
        id=eid,
        title=f"标题-{eid}",
        source_type="paper_en",
        publish_date=publish_date,
    )


# ═════════════════════════════════════════════════════════════════════════════
# R10.1 / R10.3  select_sources：罕见病/重症时含前沿源 + 交叉佐证源
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "parsed",
    [
        make_parsed(rare=True),
        make_parsed(severe=True),
        make_parsed(rare=True, severe=True),
        # 即便 intent 是普通意图，rare/severe 也应覆盖意图选源
        make_parsed(rare=True, intent="disease_understanding"),
        make_parsed(severe=True, intent="drug_info"),
    ],
)
def test_select_sources_rare_severe_includes_frontier_and_guide(parsed):
    sources = select_sources(parsed)
    # R10.1：优先前沿源 —— trial、meeting、paper_en 三类都应在内
    assert "trial" in sources, f"R10.1 应包含临床试验源 trial: {sources}"
    assert "meeting" in sources, f"R10.1 应包含医学会议源 meeting: {sources}"
    assert "paper_en" in sources, f"R10.1 应包含英文论文源 paper_en: {sources}"
    # R10.3：保留至少一类指南/权威源用于交叉佐证
    assert "guide" in sources, f"R10.3 应保留指南源 guide 做交叉佐证: {sources}"


def test_select_sources_rare_severe_matches_declared_set():
    """罕见病/重症选源应与声明的 RARE_SEVERE_SOURCES 一致。"""
    assert select_sources(make_parsed(rare=True)) == list(RARE_SEVERE_SOURCES)
    assert select_sources(make_parsed(severe=True)) == list(RARE_SEVERE_SOURCES)


def test_select_sources_rare_severe_returns_copy_not_shared_ref():
    """返回的应是副本，调用方修改不应污染模块级常量。"""
    sources = select_sources(make_parsed(rare=True))
    sources.append("__mutated__")
    assert "__mutated__" not in RARE_SEVERE_SOURCES


def test_select_sources_latest_treatment_uses_latest_research_sources():
    parsed = make_parsed(intent="treatment_progress")
    focus = analyze_query_focus("朋友父亲得了阿尔兹海默症，有没有最新的治疗方案")
    assert select_sources(parsed, focus) == list(LATEST_RESEARCH_SOURCES)


# ═════════════════════════════════════════════════════════════════════════════
# select_sources：非 rare/severe 时按 intent 选源，未知意图回退默认源
# ═════════════════════════════════════════════════════════════════════════════

def test_select_sources_disease_understanding_uses_intent_sources():
    parsed = make_parsed(intent="disease_understanding")
    assert select_sources(parsed) == INTENT_TO_SOURCES["disease_understanding"]


@pytest.mark.parametrize("intent", list(INTENT_TO_SOURCES.keys()))
def test_select_sources_each_intent_when_not_rare_severe(intent):
    parsed = make_parsed(intent=intent)
    assert select_sources(parsed) == INTENT_TO_SOURCES[intent]


def test_select_sources_unknown_intent_falls_back_to_default():
    parsed = make_parsed(intent="some_intent_that_does_not_exist")
    assert select_sources(parsed) == DEFAULT_SOURCES


def test_select_sources_missing_intent_key_falls_back_to_default():
    """parsed 缺少 intent 键时，应回退默认源而不抛异常。"""
    assert select_sources({"rare_disease": False, "severe_condition": False}) == DEFAULT_SOURCES


# ═════════════════════════════════════════════════════════════════════════════
# R10.2  sort_evidences：罕见病/重症时按 publish_date 降序，缺失排最后
# ═════════════════════════════════════════════════════════════════════════════

def test_sort_evidences_rare_desc_by_date_dicts():
    """dict 证据 + date 对象，rare=True 应按日期降序，最新在前。"""
    ev_old = make_dict_evidence("old", date(2018, 5, 1))
    ev_mid = make_dict_evidence("mid", date(2021, 3, 10))
    ev_new = make_dict_evidence("new", date(2024, 1, 15))
    result = sort_evidences([ev_old, ev_new, ev_mid], make_parsed(rare=True))
    assert [e["id"] for e in result] == ["new", "mid", "old"]


def test_sort_evidences_severe_desc_with_none_last():
    """severe=True：None 日期排最后，其余按降序。"""
    ev_none = make_dict_evidence("none", None)
    ev_2020 = make_dict_evidence("y2020", date(2020, 6, 1))
    ev_2023 = make_dict_evidence("y2023", date(2023, 6, 1))
    result = sort_evidences([ev_none, ev_2020, ev_2023], make_parsed(severe=True))
    assert [e["id"] for e in result] == ["y2023", "y2020", "none"]


def test_sort_evidences_mixed_date_formats():
    """
    publish_date 混合形态：date 对象 / ISO 字符串 / 仅年份字符串 / None。
    rare=True 应统一解析并降序，None 与无法解析者排最后。
    """
    ev_date = make_dict_evidence("date_2022", date(2022, 7, 1))
    ev_iso = make_dict_evidence("iso_2025", "2025-03-20")
    ev_year = make_dict_evidence("year_2019", "2019")
    ev_none = make_dict_evidence("none", None)
    items = [ev_year, ev_none, ev_iso, ev_date]
    result = sort_evidences(items, make_parsed(rare=True))
    # 2025 > 2022 > 2019 > None
    assert [e["id"] for e in result] == ["iso_2025", "date_2022", "year_2019", "none"]


def test_sort_evidences_rare_desc_with_evidence_objects():
    """Evidence pydantic 对象形态，rare=True 应按 publish_date 降序（含 None 在最后）。"""
    ev_old = make_obj_evidence("o", date(2017, 1, 1))
    ev_new = make_obj_evidence("n", date(2023, 12, 31))
    ev_mid = make_obj_evidence("m", date(2020, 6, 15))
    ev_none = make_obj_evidence("x", None)
    result = sort_evidences([ev_old, ev_none, ev_new, ev_mid], make_parsed(severe=True))
    assert [e.id for e in result] == ["n", "m", "o", "x"]


def test_sort_evidences_mixed_object_and_dict():
    """混合 Evidence 对象与 dict，排序仍稳健。"""
    d_2024 = make_dict_evidence("dict_2024", "2024-01-01")
    o_2022 = make_obj_evidence("obj_2022", date(2022, 1, 1))
    d_none = make_dict_evidence("dict_none", None)
    result = sort_evidences([o_2022, d_none, d_2024], make_parsed(rare=True))
    ids = [e["id"] if isinstance(e, dict) else e.id for e in result]
    assert ids == ["dict_2024", "obj_2022", "dict_none"]


# ═════════════════════════════════════════════════════════════════════════════
# R10.2  sort_evidences：非 rare/severe 时保持原顺序不变
# ═════════════════════════════════════════════════════════════════════════════

def test_sort_evidences_non_rare_severe_preserves_order_identity():
    """非 rare/severe：返回的应是同一对象（未排序），且元素顺序逐一相同。"""
    ev_a = make_dict_evidence("a", date(2010, 1, 1))
    ev_b = make_dict_evidence("b", date(2025, 1, 1))
    ev_c = make_dict_evidence("c", None)
    ev_d = make_dict_evidence("d", date(2015, 1, 1))
    original = [ev_a, ev_b, ev_c, ev_d]  # 故意乱序
    result = sort_evidences(original, make_parsed(intent="disease_understanding"))
    # 返回的就是同一个列表对象（实现直接 return evidences）
    assert result is original
    # 逐元素同一对象，顺序完全一致
    assert all(r is o for r, o in zip(result, original))
    assert [e["id"] for e in result] == ["a", "b", "c", "d"]


def test_sort_evidences_unknown_intent_preserves_order():
    ev_x = make_dict_evidence("x", date(2000, 1, 1))
    ev_y = make_dict_evidence("y", date(2030, 1, 1))
    original = [ev_y, ev_x]  # 乱序：较新的在前
    result = sort_evidences(original, make_parsed(intent="unknown"))
    assert [e["id"] for e in result] == ["y", "x"]


def test_sort_evidences_empty_list():
    """空列表两种分支都应安全返回空。"""
    assert sort_evidences([], make_parsed(rare=True)) == []
    assert sort_evidences([], make_parsed(intent="disease_understanding")) == []


# ═════════════════════════════════════════════════════════════════════════════
# _publish_date_sort_key：底层键提取的细粒度验证（has_date 标志 + 年月日）
# ═════════════════════════════════════════════════════════════════════════════

def test_publish_date_sort_key_none_is_lowest():
    assert _publish_date_sort_key({"publish_date": None}) == (0, 0, 0, 0)


def test_publish_date_sort_key_date_object():
    assert _publish_date_sort_key({"publish_date": date(2024, 3, 5)}) == (1, 2024, 3, 5)


def test_publish_date_sort_key_iso_string():
    assert _publish_date_sort_key({"publish_date": "2023-11-02"}) == (1, 2023, 11, 2)


def test_publish_date_sort_key_year_only_string():
    assert _publish_date_sort_key({"publish_date": "2019"}) == (1, 2019, 0, 0)


def test_publish_date_sort_key_empty_string_is_lowest():
    assert _publish_date_sort_key({"publish_date": "   "}) == (0, 0, 0, 0)


def test_publish_date_sort_key_unparseable_string_is_lowest():
    assert _publish_date_sort_key({"publish_date": "去年"}) == (0, 0, 0, 0)


def test_publish_date_sort_key_object_form():
    ev = make_obj_evidence("e", date(2022, 8, 9))
    assert _publish_date_sort_key(ev) == (1, 2022, 8, 9)


# ─────────────────────────────────────────────────────────────────────────────
# R10.4 覆盖说明：
#   "罕见病/重症专门源无结果 → 回退默认源" 的逻辑位于路由函数 search_evidence
#   内部，依赖 knows_client.search_multi 的真实返回，属于 I/O 编排而非纯函数。
#   纯函数层（select_sources / sort_evidences）无法直接触发该回退分支，
#   故 R10.4 由集成测试（mock knows_client.search_multi 首次返回空、二次返回数据，
#   断言最终用 DEFAULT_SOURCES 拿到结果）覆盖。本文件聚焦 R10.1/R10.2/R10.3 严格单测。
# ─────────────────────────────────────────────────────────────────────────────
