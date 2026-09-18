# GridWise — Energy Optimizer Service

Live API: https://gridwise-api-tom-and-jerry.onrender.com

Docker image: `docker pull oishee494jellyfish/gridwise-api:v1`

> Note: free-tier hosting may take 30-50s to wake up on the first request after inactivity.

LLM-assisted 24-hour household/microgrid energy scheduling. An operator writes
free-text notes ("don't discharge the battery 6-9pm"); an LLM interprets them
into structured directives; a linear-programming optimizer produces a
cost-minimal hourly grid/solar/battery schedule; a validator independently
replays the schedule to confirm every constraint holds before the response
goes out.

## Architecture

- `app/schemas.py` — Pydantic request/response contract (shared with the LLM
  interpretation module).
- `app/optimizer.py` — builds and solves the LP with PuLP (CBC solver),
  minimizing total grid cost subject to energy balance, solar availability,
  battery rate/capacity/reserve limits, and any applicable directives.
- `app/validator.py` — replays the optimizer's output hour-by-hour and
  independently verifies every constraint and the reported totals. Runs as a
  safety net before every response; logs a warning (never crashes) if it
  finds a violation.
- `app/interpreter.py` — `interpret_notes(operator_notes, battery=None)`
  converts each note to a structured directive with Gemini. `battery` lets
  the LLM resolve relative quantities ("50% of battery capacity") into
  absolute kWh.
- `app/guardrail_validator.py` — deterministic guardrail on the LLM output:
  one directive per note, only allowed directive types, malformed output
  falls back to `no_op`.
- `app/main.py` — FastAPI app; calls `interpret_notes`, then the optimizer,
  then the final-schedule validator.

## Setup (local)

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
```

## Run locally

Create a `.env` file in the project root containing your key (never commit it):

```
LLM_API_KEY=your_gemini_api_key_here
```

Then, from the project root:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- `GET /health` -> `{"status": "ok"}`
- `POST /optimize-energy` -> see `app/schemas.py` for the exact request/response shape.

## Run with Docker

Pull the published image and run it, passing the key at runtime (it is not
baked into the image):

```bash
docker pull oishee494jellyfish/gridwise-api:v1
docker run -p 8000:8000 -e LLM_API_KEY=your_gemini_api_key_here oishee494jellyfish/gridwise-api:v1
```

Or build from source:

```bash
docker build -t gridwise .
docker run -p 8000:8000 -e LLM_API_KEY=your_gemini_api_key_here gridwise
```

Either way the API is then at `http://localhost:8000`.

## Sample request / response

Send the request in `sample_cases/example_request.json` (24 hourly entries;
abbreviated below):

```bash
curl -X POST https://gridwise-api-tom-and-jerry.onrender.com/optimize-energy \
  -H "Content-Type: application/json" \
  -d @sample_cases/example_request.json
```

Request (abbreviated):

```json
{
  "scenario_id": "SAMPLE-03",
  "operator_notes": [
    "Keep at least 50% of the battery capacity stored in the battery from 6 PM until 9 PM for emergency operations."
  ],
  "hours": [
    {"hour": 0, "demand_kwh": 90, "solar_kwh": 0, "tariff_bdt_per_kwh": 6},
    "... hours 1-22 ...",
    {"hour": 23, "demand_kwh": "...", "solar_kwh": "...", "tariff_bdt_per_kwh": "..."}
  ],
  "battery": {
    "capacity_kwh": 200,
    "initial_energy_kwh": 120,
    "minimum_energy_kwh": 40,
    "max_charge_kwh_per_hour": 50,
    "max_discharge_kwh_per_hour": 50
  }
}
```

Response (abbreviated; `hourly_plan` has all 24 hours):

```json
{
  "scenario_id": "SAMPLE-03",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "minimum_battery_reserve",
      "structured_adjustment": {"hours": [18, 19, 20], "minimum_energy_kwh": 100.0},
      "explanation": "50% of the 200 kWh capacity is 100 kWh, which is reserved from 6 PM to 9 PM."
    }
  ],
  "hourly_plan": [
    {"hour": 0, "grid_kwh": 40.0, "solar_used_kwh": 0.0, "battery_action": "discharge", "battery_kwh": 50.0, "battery_energy_after_kwh": 70.0},
    "... hours 1-17 ...",
    {"hour": 18, "grid_kwh": 155.0, "solar_used_kwh": 0.0, "battery_action": "discharge", "battery_kwh": 50.0, "battery_energy_after_kwh": 150.0},
    "... hours 19-23 ..."
  ],
  "total_grid_kwh": 2430.0,
  "total_cost_bdt": 35480.0,
  "peak_grid_kwh": 205.0,
  "plan_summary": "Optimized 24h schedule for 'SAMPLE-03': total grid draw 2430.00 kWh, cost 35480.00 BDT, peak grid 205.00 kWh."
}
```

Note how the LLM turned "50% of the battery capacity" into an absolute
`minimum_energy_kwh` of 100, which the optimizer then enforced for hours 18-20.

## Testing against sample cases

With the server running locally on port 8000:

```bash
python sample_cases/run_tests.py
```

This POSTs every `sample_cases/case_*.json` `input` to the running API and
checks the response for structural validity (24 unique hours, matching
`scenario_id`) and reports `total_cost_bdt` alongside any `expected_output`
value for comparison. An exact schedule match is not required — the LP can
find multiple optimal solutions with the same cost — only constraint
validity and a comparable total cost matter.

To run the 10-case public pack (`sample_cases.json`, includes the expected
directives and costs) against the running API and the real LLM:

```bash
python sample_cases/run_sample_pack.py
```

Set `GRIDWISE_API_URL` to test a different host, e.g. the live API.

To exercise the optimizer directly with a hardcoded directive (bypassing the
API and the LLM), run:

```bash
python sample_cases/_quick_optimizer_check.py
```

## Environment variables

- `LLM_API_KEY` — Gemini API key used by `app/interpreter.py`. Set it in a
  local `.env` file (git-ignored) or in the host's environment settings.
  Without it, every note safely falls back to `no_op`.

## Known limitations

- If the LLM call fails (bad key, quota, timeout), notes silently fall back
  to `no_op` and the plan is optimized without them.
- Relative quantities are resolved only from the battery config; notes
  relative to anything else (e.g. peak demand) become `no_op`.
- The optimizer assumes a single battery and a single grid connection point;
  no multi-battery or multi-site support.
- `max_grid_window` directives only constrain the hours listed; if two
  `max_grid_window` directives target the same hour, the tighter limit wins.
- No authentication/rate limiting — not intended for public deployment as-is.
- The LP solver (CBC via PuLP) runs synchronously in-process; fine for a
  24-hour single-scenario horizon but not batched/concurrent-safe at scale.
