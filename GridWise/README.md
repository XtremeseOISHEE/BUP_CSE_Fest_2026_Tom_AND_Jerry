# GridWise — Energy Optimizer Service

Live API: https://gridwise-api-tom-and-jerry.onrender.com

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

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- `GET /health` -> `{"status": "ok"}`
- `POST /optimize-energy` -> see `app/schemas.py` for the exact request/response shape.

## Run with Docker

```bash
docker build -t gridwise .
docker run -p 8000:8000 gridwise
```

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
