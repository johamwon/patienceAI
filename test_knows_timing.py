"""Quick timing test for individual KnowS endpoints"""
import os, sys, time
sys.path.insert(0, '.')

from backend.app.services.knows_client import knows_client

sources = ['paper_en', 'paper_cn', 'guide', 'trial', 'meeting', 'package_insert']
query = 'Lung Adenocarcinoma Immunotherapy'

print(f"Testing KnowS endpoints with query: {query}")
print("-" * 60)

for s in sources:
    t = time.time()
    try:
        r = knows_client.search(s, query, 5)
        elapsed = time.time() - t
        print(f"  {s:20s}: OK ({len(r)} results, {elapsed:.1f}s)")
    except Exception as e:
        elapsed = time.time() - t
        print(f"  {s:20s}: FAIL ({elapsed:.1f}s) - {e}")

print("\nDone.")
