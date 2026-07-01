"""
KnowS AI 结构化医学证据检索客户端

封装 6 类医学证据检索端点：
  - paper_en: 英文论文检索
  - paper_cn: 中文论文检索
  - guide: 临床指南检索
  - trial: 临床试验检索
  - meeting: 医学会议检索
  - package_insert: 药品说明书检索
"""

import os
import httpx
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models.schemas import Evidence

KNOWS_BASE_URL = os.getenv("KNOWS_BASE_URL", "https://api.nullht.com/v1")
KNOWS_API_KEY = os.getenv("KNOWS_API_KEY", "")

ENDPOINTS = {
    "paper_en": "/evidences/ai_search_paper_en",
    "paper_cn": "/evidences/ai_search_paper_cn",
    "guide": "/evidences/ai_search_guide",
    "trial": "/evidences/ai_search_trial",
    "meeting": "/evidences/ai_search_meeting",
    "package_insert": "/evidences/ai_search_package_insert",
}

SOURCE_TYPE_MAP = {
    "paper_en": "paper_en",
    "paper_cn": "paper_cn",
    "guide": "guide",
    "trial": "trial",
    "meeting": "meeting",
    "package_insert": "package_insert",
}


class KnowsClient:
    """KnowS AI 证据检索客户端"""

    def __init__(self, base_url: str = KNOWS_BASE_URL, api_key: str = KNOWS_API_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def search(
        self,
        source: str,
        query: str,
        max_results: int = 20,
    ) -> list[Evidence]:
        """
        调用单个 KnowS AI 端点检索证据

        Args:
            source: 证据类型 (paper_en / paper_cn / guide / trial / meeting / package_insert)
            query: 检索查询
            max_results: 最多返回条数

        Returns:
            Evidence 列表
        """
        if source not in ENDPOINTS:
            raise ValueError(f"Unknown source: {source}. Available: {list(ENDPOINTS.keys())}")

        endpoint = ENDPOINTS[source]
        url = f"{self.base_url}{endpoint}"

        payload = {"query": query}
        if max_results:
            payload["max_results"] = min(max_results, 40)

        resp = self._client.post(url, json=payload, headers=self._headers())
        resp.raise_for_status()

        raw_data = resp.json()
        return self._normalize(raw_data, source)

    def search_multi(
        self,
        query: str,
        sources: list[str],
        max_results_per_source: int = 10,
    ) -> list[Evidence]:
        """
        并行调用多个端点，去重后返回（所有源使用同一 query）

        Args:
            query: 检索查询
            sources: 证据类型列表
            max_results_per_source: 每个源最多返回条数

        Returns:
            去重后的 Evidence 列表（保持 sources 的顺序，避免结果抖动）
        """
        # 所有源共用同一 query，转为 (source, query) 列表复用并行实现
        valid_sources = [s for s in sources if s in ENDPOINTS]
        source_query_pairs = [(s, query) for s in valid_sources]
        return self.search_multi_queries(source_query_pairs, max_results_per_source)

    def search_multi_queries(
        self,
        source_query_pairs: list[tuple[str, str]],
        max_results_per_source: int = 10,
    ) -> list[Evidence]:
        """
        并行调用多个端点（每个源可用不同的优化 query），去重后返回。

        与 search_multi 的区别：允许「每源不同 query」（explain/search 里按源取不同
        语言的优化 query 的场景）。内部用 ThreadPoolExecutor 并发发起 self.search，
        httpx.Client 线程安全可共享连接池；单源异常不影响其他源（记录 warning 继续）。
        总耗时 ≈ 最慢的单源，而非所有源之和。

        Args:
            source_query_pairs: (source, query) 列表，按调用方期望的优先级顺序排列
            max_results_per_source: 每个源最多返回条数

        Returns:
            去重后的 Evidence 列表（结果按入参顺序稳定合并，去重保留首次出现）
        """
        # 过滤未知源，保留入参顺序
        pairs = [(s, q) for (s, q) in source_query_pairs if s in ENDPOINTS]
        if not pairs:
            return []

        # 并行执行：每个源在独立线程内调用 self.search（含 tenacity 重试）
        results_by_index: list[Optional[list[Evidence]]] = [None] * len(pairs)
        max_workers = min(len(pairs), 6)

        def _do_search(index: int, source: str, q: str):
            try:
                return index, self.search(source, q, max_results_per_source)
            except Exception as e:
                print(f"[WARN] KnowS search failed for {source}: {e}")
                return index, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(_do_search, i, source, q)
                for i, (source, q) in enumerate(pairs)
            ]
            for future in futures:
                index, results = future.result()
                results_by_index[index] = results

        # 按入参顺序合并 + 去重（顺序稳定，避免并行后结果抖动）
        all_evidence: list[Evidence] = []
        seen_ids: set[str] = set()
        for results in results_by_index:
            if not results:
                continue
            for ev in results:
                dedup_key = self._dedup_key(ev)
                if dedup_key and dedup_key not in seen_ids:
                    seen_ids.add(dedup_key)
                    all_evidence.append(ev)

        return all_evidence

    def _normalize(self, raw: dict, source: str) -> list[Evidence]:
        """将 KnowS AI 返回的原始 JSON 标准化为 Evidence 对象"""
        evidences = []

        # KnowS AI 可能返回 {"evidences": [...]} 或直接 [...]
        items = raw.get("evidences", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return evidences

        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            # 生成唯一 ID
            eid = (
                item.get("pmid")
                or item.get("doi")
                or item.get("nct_id")
                or f"{source}_{i}"
            )

            # 映射来源类型
            src_type = SOURCE_TYPE_MAP.get(source, "unknown")

            # 提取日期
            pub_date = None
            if item.get("publish_date"):
                try:
                    pub_date = item["publish_date"]
                    if isinstance(pub_date, str):
                        pub_date = date.fromisoformat(pub_date)
                except (ValueError, TypeError):
                    pub_date = None

            # authors 可能是 list[str] 或 str，统一转为逗号分隔字符串
            authors_raw = item.get("authors")
            if isinstance(authors_raw, list):
                authors_str = ", ".join(str(a) for a in authors_raw)
            else:
                authors_str = authors_raw

            evidence = Evidence(
                id=str(eid),
                title=item.get("title", ""),
                authors=authors_str,
                source_type=src_type,
                pmid=item.get("pmid"),
                doi=item.get("doi"),
                nct_id=item.get("nct_id"),
                abstract=item.get("abstract"),
                publish_date=pub_date,
                journal=item.get("journal"),
                evidence_level=item.get("evidence_level"),
                url=item.get("url") or item.get("link"),
                raw=item,
            )
            evidences.append(evidence)

        return evidences

    def _dedup_key(self, ev: Evidence) -> str | None:
        """生成去重键：优先 PMID，其次 DOI，再次 NCT ID"""
        return ev.pmid or ev.doi or ev.nct_id or ev.id

    def close(self):
        self._client.close()


# ─── 全局单例 ───────────────────────────────────────────────────────────────

knows_client = KnowsClient()
