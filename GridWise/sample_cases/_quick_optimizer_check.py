import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.optimizer import solve_schedule
from app.validator import validate_final_schedule, validate_totals

with open(os.path.join(os.path.dirname(__file__), "case_01_basic.json")) as f:
    case = json.load(f)

req = case["input"]
hours_data = req["hours"]
battery = req["battery"]

directives = [
    {
        "note_index": 0,
        "applies": True,
        "directive_type": "no_discharge_window",
        "structured_adjustment": {"hours": [18, 19, 20]},
        "explanation": "hardcoded test directive",
    },
    {
        "note_index": 1,
        "applies": True,
        "directive_type": "minimum_battery_reserve",
        "structured_adjustment": {"hours": [22, 23, 0, 1, 2, 3, 4, 5], "minimum_energy_kwh": 5.0},
        "explanation": "hardcoded test directive",
    },
]

result = solve_schedule(hours_data, battery, directives)

print(f"total_grid_kwh: {result['total_grid_kwh']}")
print(f"total_cost_bdt: {result['total_cost_bdt']}")
print(f"peak_grid_kwh: {result['peak_grid_kwh']}")
print()
for p in result["hourly_plan"]:
    print(p)

is_valid, violations = validate_final_schedule(result["hourly_plan"], hours_data, battery, directives)
totals_violations = validate_totals(
    result["total_grid_kwh"], result["total_cost_bdt"], result["peak_grid_kwh"],
    result["hourly_plan"], hours_data,
)

print()
print(f"validator is_valid: {is_valid}")
if violations:
    print("violations:")
    for v in violations:
        print(f"  - {v}")
if totals_violations:
    print("totals violations:")
    for v in totals_violations:
        print(f"  - {v}")
