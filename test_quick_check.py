import httpx, time

BASE = "http://localhost:8002"

# Test search with drug intent
print("--- Search test (drug comparison) ---")
t = time.time()
r = httpx.post(f"{BASE}/api/v1/search", json={"query": "奥希替尼和吉非替尼哪个好", "max_results": 5}, timeout=60.0)
print(f"  Time: {time.time()-t:.1f}s | Status: {r.status_code} | Intent: {r.json().get('intent')}")

# Test explain
print("\n--- Explain test (quick) ---")
t = time.time()
try:
    r = httpx.post(f"{BASE}/api/v1/explain", json={"query": "奥希替尼的副作用有哪些"}, timeout=180.0)
    elapsed = time.time() - t
    print(f"  Time: {elapsed:.1f}s | Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  Layer1: {data.get('layer1_conclusion', {}).get('text', '')[:80]}")
        print(f"  Layer2 cards: {len(data.get('layer2_evidence_cards', []))}")
        print(f"  Layer3 present: {bool(data.get('layer3_patient_explanation'))}")
    else:
        print(f"  Error: {r.text[:200]}")
except httpx.TimeoutException:
    print(f"  TIMEOUT after {time.time()-t:.1f}s")
