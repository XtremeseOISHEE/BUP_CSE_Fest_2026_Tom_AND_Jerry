import json
import os
import sys

import requests

API_URL = os.environ.get("GRIDWISE_API_URL", "http://127.0.0.1:8000/optimize-energy")
PACK = os.path.join(os.path.dirname(__file__), "..", "sample_cases.json")
FALLBACK_MARKERS = ("malformed", "safely mapped", "stub:")


def main():
    with open(PACK, encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    passed = 0
    for case in cases:
        cid = case["id"]
        exp = case["expected_output"]
        try:
            resp = requests.post(API_URL, json=case["input"], timeout=120)
        except requests.exceptions.RequestException as e:
            print(f"[FAIL] {cid}: request error {e}")
            continue
        if resp.status_code != 200:
            print(f"[FAIL] {cid}: HTTP {resp.status_code} {resp.text[:200]}")
            continue

        body = resp.json()
        problems = []

        got = [(d["note_index"], d["applies"], d["directive_type"]) for d in body["directive_interpretation"]]
        want = [(d["note_index"], d["applies"], d["directive_type"]) for d in exp["directive_interpretation"]]
        if got != want:
            problems.append(f"directives {got} != expected {want}")

        for g, w in zip(body["directive_interpretation"], exp["directive_interpretation"]):
            if g["structured_adjustment"] != w["structured_adjustment"]:
                problems.append(f"note {g['note_index']} adjustment {g['structured_adjustment']} != {w['structured_adjustment']}")

        fallbacks = [d["note_index"] for d in body["directive_interpretation"]
                     if any(m in d["explanation"] for m in FALLBACK_MARKERS)]
        if fallbacks:
            problems.append(f"fallback explanation on notes {fallbacks} (LLM path not used)")

        if abs(body["total_cost_bdt"] - exp["total_cost_bdt"]) > 0.01 * max(1.0, abs(exp["total_cost_bdt"])):
            problems.append(f"total_cost_bdt {body['total_cost_bdt']} vs expected {exp['total_cost_bdt']}")

        if "WARNING" in body["plan_summary"]:
            problems.append("validator flagged the plan")

        if problems:
            print(f"[FAIL] {cid}: " + "; ".join(problems))
        else:
            passed += 1
            print(f"[PASS] {cid}: cost={body['total_cost_bdt']} grid={body['total_grid_kwh']} peak={body['peak_grid_kwh']}")

    print(f"\n{passed}/{len(cases)} passed")
    sys.exit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()
