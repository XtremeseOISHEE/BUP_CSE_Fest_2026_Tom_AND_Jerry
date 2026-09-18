import pulp


def _effective_solar(hours_data: list[dict], directives: list[dict]) -> dict[int, float]:
    effective = {h["hour"]: h["solar_kwh"] for h in hours_data}
    for d in directives:
        if not d.get("applies"):
            continue
        if d.get("directive_type") == "solar_reduction":
            adj = d.get("structured_adjustment") or {}
            factor = adj.get("factor", 1.0)
            for h in adj.get("hours", []):
                if h in effective:
                    effective[h] = effective[h] * factor
    return effective


def _reserve_by_hour(hours_data: list[dict], battery: dict, directives: list[dict]) -> dict[int, float]:
    base = battery["minimum_energy_kwh"]
    reserve = {h["hour"]: base for h in hours_data}
    for d in directives:
        if not d.get("applies"):
            continue
        if d.get("directive_type") == "minimum_battery_reserve":
            adj = d.get("structured_adjustment") or {}
            min_energy = adj.get("minimum_energy_kwh", base)
            for h in adj.get("hours", []):
                if h in reserve:
                    reserve[h] = max(reserve[h], min_energy)
    return reserve


def _hour_flags(directives: list[dict], directive_type: str) -> set[int]:
    hours = set()
    for d in directives:
        if not d.get("applies"):
            continue
        if d.get("directive_type") == directive_type:
            adj = d.get("structured_adjustment") or {}
            hours.update(adj.get("hours", []))
    return hours


def _max_grid_by_hour(directives: list[dict]) -> dict[int, float]:
    limits: dict[int, float] = {}
    for d in directives:
        if not d.get("applies"):
            continue
        if d.get("directive_type") == "max_grid_window":
            adj = d.get("structured_adjustment") or {}
            max_grid = adj.get("max_grid_kwh")
            if max_grid is None:
                continue
            for h in adj.get("hours", []):
                limits[h] = min(limits.get(h, max_grid), max_grid)
    return limits


def solve_schedule(hours_data: list[dict], battery: dict, directives: list[dict]) -> dict:
    hours_data = sorted(hours_data, key=lambda h: h["hour"])
    hour_indices = [h["hour"] for h in hours_data]
    demand = {h["hour"]: h["demand_kwh"] for h in hours_data}
    tariff = {h["hour"]: h["tariff_bdt_per_kwh"] for h in hours_data}

    effective_solar = _effective_solar(hours_data, directives)
    reserve = _reserve_by_hour(hours_data, battery, directives)
    no_charge_hours = _hour_flags(directives, "no_charge_window")
    no_discharge_hours = _hour_flags(directives, "no_discharge_window")
    max_grid_hours = _max_grid_by_hour(directives)

    prob = pulp.LpProblem("gridwise_energy_optimization", pulp.LpMinimize)

    grid = {h: pulp.LpVariable(f"grid_{h}", lowBound=0) for h in hour_indices}
    solar_used = {h: pulp.LpVariable(f"solar_used_{h}", lowBound=0) for h in hour_indices}
    charge = {h: pulp.LpVariable(f"charge_{h}", lowBound=0) for h in hour_indices}
    discharge = {h: pulp.LpVariable(f"discharge_{h}", lowBound=0) for h in hour_indices}
    battery_energy = {h: pulp.LpVariable(f"battery_energy_{h}", lowBound=0) for h in hour_indices}

    prob += pulp.lpSum(grid[h] * tariff[h] for h in hour_indices)

    for h in hour_indices:
        prob += grid[h] + solar_used[h] + discharge[h] == demand[h] + charge[h]
        prob += solar_used[h] <= effective_solar[h]
        prob += charge[h] <= battery["max_charge_kwh_per_hour"]
        prob += discharge[h] <= battery["max_discharge_kwh_per_hour"]

        prev_energy = battery["initial_energy_kwh"] if h == 0 else battery_energy[h - 1]
        prob += battery_energy[h] == prev_energy + charge[h] - discharge[h]

        prob += battery_energy[h] >= reserve[h]
        prob += battery_energy[h] <= battery["capacity_kwh"]

        if h in no_charge_hours:
            prob += charge[h] == 0
        if h in no_discharge_hours:
            prob += discharge[h] == 0
        if h in max_grid_hours:
            prob += grid[h] <= max_grid_hours[h]

    prob += battery_energy[hour_indices[-1]] == battery["initial_energy_kwh"]

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        raise ValueError(f"optimizer failed to find optimal solution: status={pulp.LpStatus[status]}")

    hourly_plan = []
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for h in hour_indices:
        grid_val = max(0.0, pulp.value(grid[h]))
        solar_val = max(0.0, pulp.value(solar_used[h]))
        charge_val = max(0.0, pulp.value(charge[h]))
        discharge_val = max(0.0, pulp.value(discharge[h]))
        energy_after = max(0.0, pulp.value(battery_energy[h]))

        net = charge_val - discharge_val
        if net > 1e-6:
            action = "charge"
            magnitude = net
        elif net < -1e-6:
            action = "discharge"
            magnitude = -net
        else:
            action = "idle"
            magnitude = 0.0

        hourly_plan.append({
            "hour": h,
            "grid_kwh": round(grid_val, 4),
            "solar_used_kwh": round(solar_val, 4),
            "battery_action": action,
            "battery_kwh": round(magnitude, 4),
            "battery_energy_after_kwh": round(energy_after, 4),
        })

        total_grid += grid_val
        total_cost += grid_val * tariff[h]
        peak_grid = max(peak_grid, grid_val)

    return {
        "hourly_plan": hourly_plan,
        "total_grid_kwh": round(total_grid, 4),
        "total_cost_bdt": round(total_cost, 4),
        "peak_grid_kwh": round(peak_grid, 4),
    }
