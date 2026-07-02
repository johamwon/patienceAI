"""Debug KnowS paper_en normalization to find what validation error occurs"""
import os, sys, httpx, json
sys.path.insert(0, '.')

KNOWS_BASE_URL = os.getenv("KNOWS_BASE_URL", "https://api.nullht.com/v1")
KNOWS_API_KEY = os.getenv("KNOWS_API_KEY", "")

url = f"{KNOWS_BASE_URL}/evidences/ai_search_paper_en"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {KNOWS_API_KEY}"}
payload = {"query": "Lung Adenocarcinoma Immunotherapy", "max_results": 5}

resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
raw_data = resp.json()

print(f"Status: {resp.status_code}")
print(f"Keys in response: {list(raw_data.keys())}")

evidences_raw = raw_data.get("evidences", [])
print(f"Number of raw evidences: {len(evidences_raw)}")

# Try to normalize manually
from backend.app.models.schemas import Evidence
from datetime import date

for i, item in enumerate(evidences_raw[:2]):
    print(f"\n--- Item {i} ---")
    print(f"  Keys: {list(item.keys())}")
    print(f"  title: {item.get('title', '')[:60]}")
    print(f"  pmid: {item.get('pmid')}")
    print(f"  doi: {item.get('doi')}")
    print(f"  publish_date: {item.get('publish_date')} (type={type(item.get('publish_date'))})")
    print(f"  authors: {str(item.get('authors'))[:80]} (type={type(item.get('authors'))})")
    
    # Try to create Evidence object
    try:
        eid = item.get("pmid") or item.get("doi") or item.get("nct_id") or f"paper_en_{i}"
        pub_date = None
        if item.get("publish_date"):
            try:
                pd = item["publish_date"]
                if isinstance(pd, str):
                    pub_date = date.fromisoformat(pd)
            except (ValueError, TypeError) as e:
                print(f"  Date parse error: {e}")

        ev = Evidence(
            id=str(eid),
            title=item.get("title", ""),
            authors=item.get("authors"),
            source_type="paper_en",
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
        print(f"  ✓ Evidence created OK")
    except Exception as e:
        print(f"  ✗ Evidence creation FAILED: {type(e).__name__}: {e}")
