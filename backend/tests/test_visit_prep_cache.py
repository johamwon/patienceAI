"""
甲方验收测试：visit-prep 缓存命中与缓存键隔离（关联 R7.3 / R7.4）

验收意图（需求方视角）：
- R7.3：当同一查询的 Visit_Prep_Pack 已在缓存且未过期，服务 SHALL 返回缓存结果
  而不重新生成。
- R7.4：一次生成完成后，服务 SHALL 把结果写入缓存供后续复用。

本测试严格站在需求方角度验证"第二次确实没有重新生成"——不仅断言两次返回
相等（那无法区分是否真的走了缓存），更通过对生成器 generate_visit_prep 的
调用计数，证明第二次请求未触发任何重新生成 / 检索。

此外验证 `visitprep::` 前缀与 explain 缓存键的隔离：相同 query 字符串下，
visit-prep 的缓存不会命中、也不会污染 explain 的缓存（反之亦然）。

缓存副作用隔离（务必清理干净）：
- cache_service 是全局单例且会落盘 backend/app/cache/cache_db.json。
- autouse fixture 将其内部存储替换为临时空 dict，并把 _save_cache 替换为
  no-op，确保测试期间绝不触碰真实缓存文件；测试结束后恢复原状。
"""

import asyncio

import pytest

# 被测路由与依赖
from backend.app.api import visit_prep as visit_prep_module
from backend.app.api.visit_prep import visit_prep, _CACHE_PREFIX
from backend.app.services.cache_service import cache_service
from backend.app.models.schemas import VisitPrepRequest, VisitPrepResponse


# ─── 缓存隔离 fixture（autouse，避免污染 cache_db.json） ──────────────────────

@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    """把全局 cache_service 的存储替换为临时 dict，并禁止落盘。

    - 保存并清空内部 _cache，测试结束恢复。
    - _save_cache 替换为 no-op：测试期间任何 set/delete 都不会写磁盘，
      从根本上杜绝对真实 cache_db.json 的污染。
    """
    original_cache = cache_service._cache
    original_save = cache_service._save_cache

    cache_service._cache = {}
    monkeypatch.setattr(cache_service, "_save_cache", lambda: None)

    try:
        yield cache_service
    finally:
        # 恢复原始内存状态与保存方法（monkeypatch 也会自动还原 _save_cache）
        cache_service._cache = original_cache
        cache_service._save_cache = original_save


# ─── 可计数的 generate_visit_prep mock ───────────────────────────────────────

class CountingGenerator:
    """模拟 generate_visit_prep 的可计数异步生成器。

    记录调用次数与入参，返回一个合法的 VisitPrepPack dict。
    每次调用在 pack 内写入当前调用序号，便于验证"返回的是首次生成的结果"。
    """

    def __init__(self):
        self.call_count = 0
        self.calls: list[dict] = []

    async def __call__(self, query, evidences, emotion, llm_client):
        self.call_count += 1
        self.calls.append(
            {
                "query": query,
                "evidences": evidences,
                "emotion": emotion,
            }
        )
        return {
            "questions_for_doctor": [f"问题占位（第{self.call_count}次生成）"],
            "info_to_tell_doctor": ["请告知医生我的主要症状。"],
            "tests_to_request": ["可以问医生是否需要做进一步检查？"],
            "treatment_options_to_confirm": ["需要和医生确认后续随访计划。"],
            "positioning_note": "本清单用于辅助你和医生沟通，最终诊疗以医生判断为准。",
        }


@pytest.fixture
def patch_pipeline(monkeypatch):
    """替换 visit_prep 路由用到的生成器 + 检索，使其可计数且不触网。

    返回 (gen, search_counter) 便于断言调用次数。
    """
    gen = CountingGenerator()
    monkeypatch.setattr(visit_prep_module, "generate_visit_prep", gen)

    search_calls = {"count": 0}

    def fake_search_multi(query, sources, max_results_per_source=10):
        search_calls["count"] += 1
        # 返回一条 dict 证据，触发 evidence_based=True 路径
        return [
            {
                "id": "ev1",
                "title": "测试证据标题",
                "source_type": "paper_en",
                "abstract": "测试摘要内容。",
            }
        ]

    monkeypatch.setattr(
        visit_prep_module.knows_client, "search_multi", fake_search_multi
    )

    return gen, search_calls


# ─── 场景 1：同一 query 第二次请求走缓存，生成器不再被调用（R7.3 / R7.4） ────

class TestSecondRequestServedFromCache:
    """第二次请求必须命中缓存：生成器与检索不得被再次调用。"""

    @pytest.mark.asyncio
    async def test_second_request_does_not_regenerate(self, patch_pipeline):
        gen, search_calls = patch_pipeline
        req = VisitPrepRequest(query="肺腺癌免疫治疗最新进展")

        # 首次请求：应触发一次生成 + 一次检索
        first = await visit_prep(req)
        assert isinstance(first, VisitPrepResponse)
        assert gen.call_count == 1, "首次请求应触发恰好一次生成"
        assert search_calls["count"] == 1, "首次请求应触发恰好一次检索"

        # 第二次同一 query：必须命中缓存，不得重新生成 / 重新检索
        second = await visit_prep(req)
        assert isinstance(second, VisitPrepResponse)
        assert gen.call_count == 1, (
            f"第二次请求不得重新生成，生成器调用次数应仍为 1，实际为 {gen.call_count}"
        )
        assert search_calls["count"] == 1, (
            f"第二次请求不得重新检索，检索调用次数应仍为 1，实际为 {search_calls['count']}"
        )

        # 返回结果与首次完全一致（缓存复用）
        assert second.model_dump() == first.model_dump(), "缓存返回结果应与首次一致"

    @pytest.mark.asyncio
    async def test_result_written_to_cache_under_prefixed_key(self, patch_pipeline):
        """R7.4：生成结果应写入带 visitprep:: 前缀的缓存键下。"""
        gen, _ = patch_pipeline
        query = "胰腺癌有哪些亚型"
        req = VisitPrepRequest(query=query)

        await visit_prep(req)

        # 直接用 visit-prep 前缀键命中
        prefixed_key = f"{_CACHE_PREFIX}{query}"
        cached = cache_service.get(prefixed_key)
        assert cached is not None, "生成结果应写入 visitprep:: 前缀缓存键"
        # 缓存内容可重建为合法响应
        VisitPrepResponse(**cached)

    @pytest.mark.asyncio
    async def test_different_query_triggers_new_generation(self, patch_pipeline):
        """不同 query 不应命中彼此缓存（防止断言假阳性：证明计数器确实会增长）。"""
        gen, _ = patch_pipeline

        await visit_prep(VisitPrepRequest(query="查询A"))
        assert gen.call_count == 1

        await visit_prep(VisitPrepRequest(query="查询B"))
        assert gen.call_count == 2, "不同 query 应各自触发生成"


# ─── 场景 2：visitprep:: 前缀与 explain 缓存键隔离（R7.3 / R7.4） ─────────────

class TestCacheKeyIsolationFromExplain:
    """相同 query 字符串下，visit-prep 与 explain 缓存互不命中、互不污染。

    explain.py 使用 `cache_service.get/set(req.query, max_results=5)`，
    visit_prep.py 使用 `cache_service.get/set("visitprep::" + req.query)`（默认 max_results=5）。
    两者底层 key 不同，应彼此隔离。
    """

    def test_key_strings_are_distinct(self):
        """底层缓存键应不同：visitprep:: 前缀产生不同的 md5。"""
        query = "相同的查询字符串"
        explain_key = cache_service._make_key(query, 5)
        visitprep_key = cache_service._make_key(f"{_CACHE_PREFIX}{query}", 5)
        assert explain_key != visitprep_key, "visit-prep 与 explain 的缓存键必须不同"

    @pytest.mark.asyncio
    async def test_explain_cache_does_not_satisfy_visit_prep(self, patch_pipeline):
        """预置 explain 缓存后，visit-prep 不得命中它，仍应重新生成。"""
        gen, search_calls = patch_pipeline
        query = "同名查询：免疫治疗"

        # 模拟 explain 已缓存该 query（与 explain.py 的写法一致）
        explain_payload = {"sentinel": "explain-data", "query": query}
        cache_service.set(query, explain_payload, max_results=5)

        # visit-prep 处理同一 query：不得命中 explain 缓存
        resp = await visit_prep(VisitPrepRequest(query=query))

        assert gen.call_count == 1, "visit-prep 不得命中 explain 缓存，应触发一次生成"
        # 返回的是 visit-prep 结果，而非 explain 数据
        assert isinstance(resp, VisitPrepResponse)

        # explain 缓存未被 visit-prep 污染/覆盖
        explain_cached = cache_service.get(query, max_results=5)
        assert explain_cached == explain_payload, "explain 缓存不应被 visit-prep 覆盖"

    @pytest.mark.asyncio
    async def test_visit_prep_cache_does_not_satisfy_explain(self, patch_pipeline):
        """visit-prep 写缓存后，explain 的 key 不应命中 visit-prep 的内容。"""
        gen, _ = patch_pipeline
        query = "同名查询：靶向药"

        # visit-prep 生成并写缓存
        await visit_prep(VisitPrepRequest(query=query))
        assert gen.call_count == 1

        # 用 explain 的取法（不带前缀）查询：应为 None（未命中 visit-prep 缓存）
        explain_view = cache_service.get(query, max_results=5)
        assert explain_view is None, "explain 用原始 query 取缓存不应命中 visit-prep 的结果"

        # 而 visit-prep 自己的前缀键应命中
        assert cache_service.get(f"{_CACHE_PREFIX}{query}") is not None
