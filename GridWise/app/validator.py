TOLERANCE = 0.01


def validate_final_schedule(
    hourly_plan: list[dict],
    hours_data: list[dict],
    battery: dict,
    directives: list[dict],
) -> tuple[bool, list[str]]:
    violations: list[str] = []

    hours_by_index = {h["hour"]: h for h in hours_data}
    plan_hours = [p["hour"] for p in hourly_plan]

    if sorted(set(plan_hours)) != list(range(24)) or len(plan_hours) != 24:
        violations.append(f"plan does not contain exactly 24 unique hours 0-23: got {sorted(plan_hours)}")
        return False, violations

    plan_by_hour = {p["hour"]: p for p in hourly_plan}

    effective_solar = {h["hour"]: h["solar_kwh"] for h in hours_data}
    reserve = {h["hour"]: battery["minimum_energy_kwh"] for h in hours_data}
    no_charge_hours = set()
    no_discharge_hours = set()
    max_grid_hours: dict[int, float] = {}

    for d in directives:
        if not d.get("applies"):
            continue
        dtype = d.get("directive_type")
        adj = d.get("structured_adjustment") or {}
        if dtype == "solar_reduction":
            factor = adj.get("factor", 1.0)
            for h in adj.get("hours", []):
                if h in effective_solar:
                    effective_solar[h] = hours_by_index[h]["solar_kwh"] * factor
        elif dtype == "minimum_battery_reserve":
            min_energy = adj.get("minimum_energy_kwh", battery["minimum_energy_kwh"])
            for h in adj.get("hours", []):
                if h in reserve:
                    reserve[h] = max(reserve[h], min_energy)
        elif dtype == "no_charge_window":
            no_charge_hours.update(adj.get("hours", []))
        elif dtype == "no_discharge_window":
            no_discharge_hours.update(adj.get("hours", []))
        elif dtype == "max_grid_window":
            max_grid = adj.get("max_grid_kwh")
            if max_grid is not None:
                for h in adj.get("hours", []):
                    max_grid_hours[h] = min(max_grid_hours.get(h, max_grid), max_grid)

    prev_energy = battery["initial_energy_kwh"]
    recalculated_total_grid = 0.0
    recalculated_total_cost = 0.0
    recalculated_peak_grid = 0.0

    for h in range(24):
        entry = plan_by_hour[h]
        src = hours_by_index[h]

        grid_kwh = entry["grid_kwh"]
        solar_used_kwh = entry["solar_used_kwh"]
        action = entry["battery_action"]
        battery_kwh = entry["battery_kwh"]
        energy_after = entry["battery_energy_after_kwh"]

        charge_val = battery_kwh if action == "charge" else 0.0
        discharge_val = battery_kwh if action == "discharge" else 0.0

        balance = grid_kwh + solar_used_kwh + discharge_val - src["demand_kwh"] - charge_val
        if abs(balance) > TOLERANCE:
            violations.append(f"hour {h}: energy balance violated (residual={balance:.4f})")

        if solar_used_kwh > effective_solar[h] + TOLERANCE:
            violations.append(
                f"hour {h}: solar_used_kwh {solar_used_kwh} exceeds effective solar {effective_solar[h]}"
            )

        if energy_after < reserve[h] - TOLERANCE:
            violations.append(f"hour {h}: battery_energy_after_kwh {energy_after} below reserve {reserve[h]}")
        if energy_after > battery["capacity_kwh"] + TOLERANCE:
            violations.append(f"hour {h}: battery_energy_after_kwh {energy_after} exceeds capacity {battery['capacity_kwh']}")

        if charge_val > battery["max_charge_kwh_per_hour"] + TOLERANCE:
            violations.append(f"hour {h}: charge {charge_val} exceeds max_charge_kwh_per_hour")
        if discharge_val > battery["max_discharge_kwh_per_hour"] + TOLERANCE:
            violations.append(f"hour {h}: discharge {discharge_val} exceeds max_discharge_kwh_per_hour")

        if action == "idle" and abs(battery_kwh) > TOLERANCE:
            violations.append(f"hour {h}: battery_action is idle but battery_kwh={battery_kwh}")

        expected_energy = prev_energy + charge_val - discharge_val
        if abs(expected_energy - energy_after) > TOLERANCE:
            violations.append(
                f"hour {h}: battery_energy_after_kwh {energy_after} does not match "
                f"prev {prev_energy} + charge {charge_val} - discharge {discharge_val}"
            )

        if h in no_charge_hours and charge_val > TOLERANCE:
            violations.append(f"hour {h}: no_charge_window directive violated (charge={charge_val})")
        if h in no_discharge_hours and discharge_val > TOLERANCE:
            violations.append(f"hour {h}: no_discharge_window directive violated (discharge={discharge_val})")
        if h in max_grid_hours and grid_kwh > max_grid_hours[h] + TOLERANCE:
            violations.append(f"hour {h}: max_grid_window directive violated (grid={grid_kwh} > {max_grid_hours[h]})")

        recalculated_total_grid += grid_kwh
        recalculated_total_cost += grid_kwh * src["tariff_bdt_per_kwh"]
        recalculated_peak_grid = max(recalculated_peak_grid, grid_kwh)

        prev_energy = energy_after

    if abs(prev_energy - battery["initial_energy_kwh"]) > TOLERANCE:
        violations.append(
            f"final battery_energy_after_kwh {prev_energy} != initial_energy_kwh {battery['initial_energy_kwh']}"
        )

    return len(violations) == 0, violations


def validate_totals(
    total_grid_kwh: float,
    total_cost_bdt: float,
    peak_grid_kwh: float,
    hourly_plan: list[dict],
    hours_data: list[dict],
) -> list[str]:
    violations: list[str] = []
    hours_by_index = {h["hour"]: h for h in hours_data}

    recalculated_total_grid = sum(p["grid_kwh"] for p in hourly_plan)
    recalculated_total_cost = sum(p["grid_kwh"] * hours_by_index[p["hour"]]["tariff_bdt_per_kwh"] for p in hourly_plan)
    recalculated_peak_grid = max((p["grid_kwh"] for p in hourly_plan), default=0.0)

    if abs(recalculated_total_grid - total_grid_kwh) > TOLERANCE:
        violations.append(f"total_grid_kwh mismatch: reported {total_grid_kwh}, recalculated {recalculated_total_grid}")
    if abs(recalculated_total_cost - total_cost_bdt) > TOLERANCE:
        violations.append(f"total_cost_bdt mismatch: reported {total_cost_bdt}, recalculated {recalculated_total_cost}")
    if abs(recalculated_peak_grid - peak_grid_kwh) > TOLERANCE:
        violations.append(f"peak_grid_kwh mismatch: reported {peak_grid_kwh}, recalculated {recalculated_peak_grid}")

    return violations
