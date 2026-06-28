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
        并行调用多个端点，去重后返回

        Args:
            query: 检索查询
            sources: 证据类型列表
            max_results_per_source: 每个源最多返回条数

        Returns:
            去重后的 Evidence 列表
        """
        all_evidence: list[Evidence] = []
        seen_ids: set[str] = set()

        for source in sources:
            if source not in ENDPOINTS:
                continue
            try:
                results = self.search(source, query, max_results_per_source)
                for ev in results:
                    dedup_key = self._dedup_key(ev)
                    if dedup_key and dedup_key not in seen_ids:
                        seen_ids.add(dedup_key)
                        all_evidence.append(ev)
            except Exception as e:
                print(f"[WARN] KnowS search failed for {source}: {e}")
                continue

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
