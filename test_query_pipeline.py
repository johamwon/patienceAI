"""
patienceAI - Query-to-KnowS Pipeline Integration Tests
========================================================
Tests the live backend at http://localhost:8001 for:
1. Query rewriting + search endpoint (/api/v1/search)
2. Explain endpoint (/api/v1/explain)
"""

import httpx
import json
import sys
import time

BASE_URL = "http://localhost:8001"
SEARCH_TIMEOUT = 60.0
EXPLAIN_TIMEOUT = 180.0

# Track results
results = []


def record(test_name: str, passed: bool, details: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append({"name": test_name, "passed": passed, "details": details})
    print(f"  [{status}] {test_name}")
    if details:
        print(f"         {details}")
    print()


def test_search(test_id: int, query: str, expected_intent: str = None,
                expected_sources: list[str] = None, description: str = ""):
    """Test the /api/v1/search endpoint"""
    test_name = f"Test {test_id}: {description}"
    print(f"--- {test_name} ---")
    print(f"  Query: {query}")

    try:
        resp = httpx.post(
            f"{BASE_URL}/api/v1/search",
            json={"query": query, "max_results": 20},
            timeout=SEARCH_TIMEOUT,
        )

        if resp.status_code != 200:
            record(test_name, False, f"HTTP {resp.status_code}: {resp.text[:200]}")
            return

        data = resp.json()

        # Check evidences not empty
        evidences = data.get("evidences", [])
        intent = data.get("intent", "")
        total = data.get("total", 0)

        print(f"  Intent: {intent} | Total evidences: {total}")

        # Show first 2 evidence titles
        for i, ev in enumerate(evidences[:2]):
            print(f"  Evidence[{i}]: [{ev.get('source_type')}] {ev.get('title', '')[:60]}")

        # Validation
        issues = []

        if not evidences:
            issues.append("No evidences returned (empty list)")

        if expected_intent and intent != expected_intent:
            issues.append(f"Intent mismatch: got '{intent}', expected '{expected_intent}'")

        if expected_sources:
            found_sources = set(ev.get("source_type") for ev in evidences)
            for src in expected_sources:
                if src not in found_sources:
                    issues.append(f"Expected source '{src}' not found in results (found: {found_sources})")

        if issues:
            record(test_name, False, " | ".join(issues))
        else:
            record(test_name, True, f"Intent={intent}, {total} evidences from {set(ev.get('source_type') for ev in evidences)}")

    except httpx.TimeoutException:
        record(test_name, False, f"Request timed out after {SEARCH_TIMEOUT}s")
    except httpx.ConnectError:
        record(test_name, False, "Connection refused - is the backend running on port 8001?")
    except Exception as e:
        record(test_name, False, f"Exception: {type(e).__name__}: {e}")


def test_explain(test_id: int, query: str, description: str = ""):
    """Test the /api/v1/explain endpoint"""
    test_name = f"Test {test_id}: {description}"
    print(f"--- {test_name} ---")
    print(f"  Query: {query}")

    try:
        resp = httpx.post(
            f"{BASE_URL}/api/v1/explain",
            json={"query": query},
            timeout=EXPLAIN_TIMEOUT,
        )

        if resp.status_code != 200:
            record(test_name, False, f"HTTP {resp.status_code}: {resp.text[:300]}")
            return

        data = resp.json()

        # Validate 3-layer structure
        issues = []

        # Layer 1: conclusion
        layer1 = data.get("layer1_conclusion")
        if not layer1:
            issues.append("Missing layer1_conclusion")
        elif not layer1.get("text"):
            issues.append("layer1_conclusion.text is empty")

        # Layer 2: evidence cards
        layer2 = data.get("layer2_evidence_cards")
        if layer2 is None:
            issues.append("Missing layer2_evidence_cards")
        elif not isinstance(layer2, list):
            issues.append(f"layer2_evidence_cards is not a list: {type(layer2)}")
        elif len(layer2) == 0:
            issues.append("layer2_evidence_cards is empty (no cards)")
        else:
            print(f"  Layer2: {len(layer2)} evidence cards")
            # Check first card has required fields
            card = layer2[0]
            if not card.get("study_type"):
                issues.append("First evidence card missing study_type")
            if not card.get("source_id"):
                issues.append("First evidence card missing source_id")

        # Layer 3: patient explanation
        layer3 = data.get("layer3_patient_explanation")
        if not layer3:
            issues.append("Missing layer3_patient_explanation")
        else:
            required_fields = ["what_is_it", "what_evidence_says", "what_it_means_for_you", "when_to_see_doctor"]
            for field in required_fields:
                if not layer3.get(field):
                    issues.append(f"layer3 missing or empty: {field}")

        # Print summary
        if layer1:
            print(f"  Layer1 conclusion: {layer1.get('text', '')[:80]}...")
        if layer3:
            print(f"  Layer3 what_is_it: {layer3.get('what_is_it', '')[:80]}...")

        if issues:
            record(test_name, False, " | ".join(issues))
        else:
            record(test_name, True, f"All 3 layers present, {len(layer2)} evidence cards")

    except httpx.TimeoutException:
        record(test_name, False, f"Request timed out after {EXPLAIN_TIMEOUT}s")
    except httpx.ConnectError:
        record(test_name, False, "Connection refused - is the backend running on port 8001?")
    except Exception as e:
        record(test_name, False, f"Exception: {type(e).__name__}: {e}")


def main():
    print("=" * 70)
    print("patienceAI Query Pipeline Integration Tests")
    print(f"Target: {BASE_URL}")
    print("=" * 70)
    print()

    # Quick connectivity check
    try:
        r = httpx.get(f"{BASE_URL}/docs", timeout=5.0)
        print(f"[OK] Backend is reachable (status {r.status_code})")
    except Exception as e:
        print(f"[FATAL] Cannot reach backend at {BASE_URL}: {e}")
        print("Make sure the backend is running: backend\\venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --port 8001")
        sys.exit(1)

    print()
    print("=" * 70)
    print("TEST GROUP 1: Search Endpoint (/api/v1/search)")
    print("=" * 70)
    print()

    # Test 1: Conversational Chinese → treatment_progress
    test_search(
        1,
        "我爸得了肺腺癌，想了解最新的免疫治疗方案",
        expected_intent="treatment_progress",
        description="Conversational Chinese → treatment_progress intent",
    )

    # Test 2: Simple disease question → guide
    test_search(
        2,
        "胰腺癌是什么",
        expected_intent="disease_understanding",
        expected_sources=["guide"],
        description="Simple disease question → guide source",
    )

    # Test 3: Drug comparison → package_insert
    test_search(
        3,
        "奥希替尼和吉非替尼哪个好",
        expected_intent="drug_info",
        expected_sources=["package_insert"],
        description="Drug comparison → package_insert source",
    )

    # Test 4: Rumor check
    test_search(
        4,
        "听说断食能饿死癌细胞是真的吗",
        expected_intent="rumor_check",
        description="Rumor check → rumor_check intent",
    )

    # Test 5: Clinical trial query → trial source
    test_search(
        5,
        "有没有CAR-T治疗胃癌的临床试验在招募",
        expected_intent="clinical_trial",
        expected_sources=["trial"],
        description="Clinical trial query → trial source",
    )

    # Test 6: English mixed query
    test_search(
        6,
        "PD-L1表达检测TPS评分是什么意思",
        description="English mixed query → returns evidences",
    )

    print()
    print("=" * 70)
    print("TEST GROUP 2: Explain Endpoint (/api/v1/explain)")
    print("=" * 70)
    print()

    # Test 7: Basic explain
    test_explain(
        7,
        "肺腺癌免疫治疗最新进展",
        description="Basic explain → 3-layer structure",
    )

    # Test 8: Drug query explain
    test_explain(
        8,
        "奥希替尼的副作用有哪些",
        description="Drug query explain → valid structure",
    )

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    print(f"  Total: {total} | Passed: {passed} | Failed: {failed}")
    print()

    if failed > 0:
        print("FAILED TESTS:")
        for r in results:
            if not r["passed"]:
                print(f"  ✗ {r['name']}")
                print(f"    Reason: {r['details']}")
        print()

    if failed == 0:
        print("All tests passed! ✓")
    else:
        print(f"{failed} test(s) failed.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
