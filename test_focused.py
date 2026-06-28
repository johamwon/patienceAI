"""Focused re-test of previously failing tests"""
import httpx
import sys
import time

BASE_URL = "http://localhost:8001"

print("=" * 60)
print("Focused re-test of previously failing tests")
print("=" * 60)

# Test 3: Drug comparison intent
print("\n--- Test 3: Drug comparison → drug_info intent ---")
print("  Query: 奥希替尼和吉非替尼哪个好")
t = time.time()
resp = httpx.post(f"{BASE_URL}/api/v1/search", json={"query": "奥希替尼和吉非替尼哪个好", "max_results": 20}, timeout=60.0)
elapsed = time.time() - t
print(f"  Response time: {elapsed:.1f}s")
if resp.status_code == 200:
    data = resp.json()
    intent = data.get("intent")
    total = data.get("total", 0)
    sources = set(ev.get("source_type") for ev in data.get("evidences", []))
    print(f"  Intent: {intent} | Total: {total} | Sources: {sources}")
    if intent == "drug_info":
        print("  [PASS] Intent is drug_info")
    else:
        print(f"  [FAIL] Intent is '{intent}', expected 'drug_info'")
    if "package_insert" in sources:
        print("  [PASS] package_insert source found")
    else:
        print(f"  [WARN] package_insert not in sources: {sources}")
else:
    print(f"  [FAIL] HTTP {resp.status_code}")

# Test 7: Basic explain
print("\n--- Test 7: Basic explain → 3-layer structure ---")
print("  Query: 肺腺癌免疫治疗最新进展")
print("  (timeout: 180s - this may take a while due to multiple LLM calls)")
t = time.time()
try:
    resp = httpx.post(f"{BASE_URL}/api/v1/explain", json={"query": "肺腺癌免疫治疗最新进展"}, timeout=180.0)
    elapsed = time.time() - t
    print(f"  Response time: {elapsed:.1f}s")
    if resp.status_code == 200:
        data = resp.json()
        layer1 = data.get("layer1_conclusion", {})
        layer2 = data.get("layer2_evidence_cards", [])
        layer3 = data.get("layer3_patient_explanation", {})
        print(f"  Layer1: {layer1.get('text', '')[:60]}...")
        print(f"  Layer2: {len(layer2)} cards")
        print(f"  Layer3 keys: {list(layer3.keys())}")
        if layer1 and layer2 and layer3:
            print("  [PASS] All 3 layers present")
        else:
            issues = []
            if not layer1: issues.append("missing layer1")
            if not layer2: issues.append("empty layer2")
            if not layer3: issues.append("missing layer3")
            print(f"  [FAIL] {', '.join(issues)}")
    else:
        print(f"  [FAIL] HTTP {resp.status_code}: {resp.text[:200]}")
except httpx.TimeoutException:
    elapsed = time.time() - t
    print(f"  [FAIL] Timed out after {elapsed:.1f}s")
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}")

# Test 8: Drug explain
print("\n--- Test 8: Drug query explain → valid structure ---")
print("  Query: 奥希替尼的副作用有哪些")
print("  (timeout: 180s)")
t = time.time()
try:
    resp = httpx.post(f"{BASE_URL}/api/v1/explain", json={"query": "奥希替尼的副作用有哪些"}, timeout=180.0)
    elapsed = time.time() - t
    print(f"  Response time: {elapsed:.1f}s")
    if resp.status_code == 200:
        data = resp.json()
        layer1 = data.get("layer1_conclusion", {})
        layer2 = data.get("layer2_evidence_cards", [])
        layer3 = data.get("layer3_patient_explanation", {})
        print(f"  Layer1: {layer1.get('text', '')[:60]}...")
        print(f"  Layer2: {len(layer2)} cards")
        print(f"  Layer3 keys: {list(layer3.keys())}")
        if layer1 and layer2 and layer3:
            print("  [PASS] All 3 layers present")
        else:
            issues = []
            if not layer1: issues.append("missing layer1")
            if not layer2: issues.append("empty layer2")
            if not layer3: issues.append("missing layer3")
            print(f"  [FAIL] {', '.join(issues)}")
    else:
        print(f"  [FAIL] HTTP {resp.status_code}: {resp.text[:200]}")
except httpx.TimeoutException:
    elapsed = time.time() - t
    print(f"  [FAIL] Timed out after {elapsed:.1f}s")
except Exception as e:
    print(f"  [FAIL] {type(e).__name__}: {e}")

print("\n" + "=" * 60)
print("Done.")
