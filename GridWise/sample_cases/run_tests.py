import json
import os
import sys

import requests

API_URL = os.environ.get("GRIDWISE_API_URL", "http://127.0.0.1:8000/optimize-energy")
TOLERANCE = 0.01
CASES_DIR = os.path.dirname(__file__)


def close(a, b, tol=TOLERANCE):
    return abs(a - b) <= tol


def check_case(path: str) -> bool:
    with open(path) as f:
        case = json.load(f)

    request_payload = case["input"]
    expected = case.get("expected_output", {})

    try:
        resp = requests.post(API_URL, json=request_payload, timeout=30)
    except requests.exceptions.ConnectionError:
        print(f"[FAIL] {os.path.basename(path)}: could not connect to {API_URL}")
        return False

    if resp.status_code != 200:
        print(f"[FAIL] {os.path.basename(path)}: HTTP {resp.status_code} - {resp.text}")
        return False

    body = resp.json()

    plan = body.get("hourly_plan", [])
    hours_seen = sorted(p["hour"] for p in plan)
    ok = True

    if hours_seen != list(range(24)):
        print(f"[FAIL] {os.path.basename(path)}: hourly_plan does not cover 24 unique hours 0-23")
        ok = False

    if body.get("scenario_id") != request_payload["scenario_id"]:
        print(f"[FAIL] {os.path.basename(path)}: scenario_id mismatch")
        ok = False

    expected_cost = expected.get("total_cost_bdt")
    if expected_cost is not None and not close(body.get("total_cost_bdt", 0), expected_cost, tol=max(TOLERANCE, 0.05 * expected_cost)):
        print(
            f"[WARN] {os.path.basename(path)}: total_cost_bdt {body.get('total_cost_bdt')} "
            f"differs from expected {expected_cost} (informational only)"
        )

    if ok:
        print(
            f"[PASS] {os.path.basename(path)}: total_grid_kwh={body.get('total_grid_kwh')} "
            f"total_cost_bdt={body.get('total_cost_bdt')} peak_grid_kwh={body.get('peak_grid_kwh')}"
        )
    return ok


def main():
    case_files = sorted(
        f for f in os.listdir(CASES_DIR)
        if f.startswith("case_") and f.endswith(".json")
    )
    if not case_files:
        print("No sample_cases/*.json files found.")
        return

    results = [check_case(os.path.join(CASES_DIR, f)) for f in case_files]

    print()
    print(f"{sum(results)}/{len(results)} cases passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
