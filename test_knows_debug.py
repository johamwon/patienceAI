"""Debug KnowS paper_en endpoint to see the actual error"""
import os, sys, httpx
sys.path.insert(0, '.')

KNOWS_BASE_URL = os.getenv("KNOWS_BASE_URL", "https://api.nullht.com/v1")
KNOWS_API_KEY = os.getenv("KNOWS_API_KEY", "")

url = f"{KNOWS_BASE_URL}/evidences/ai_search_paper_en"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {KNOWS_API_KEY}"}
payload = {"query": "Lung Adenocarcinoma Immunotherapy", "max_results": 5}

print(f"POST {url}")
print(f"Payload: {payload}")
print()

resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:1000]}")
