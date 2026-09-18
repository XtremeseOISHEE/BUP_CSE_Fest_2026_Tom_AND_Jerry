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
- `app/main.py` — FastAPI app. `interpret_notes(operator_notes)`
  is currently a stub that returns `no_op` for every note — swap in the LLM
  interpreter here.

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
API and the LLM stub), run:

```bash
python sample_cases/_quick_optimizer_check.py
```

## Environment variables

- `LLM_API_KEY` — placeholder for the LLM note-interpretation module
  (Person A's component). Not currently read by this service; document it
  here so it's ready when that module is wired in.

## Known limitations

- `interpret_notes` is a stub returning `no_op` for every note
  until the LLM interpreter module is integrated.
- The optimizer assumes a single battery and a single grid connection point;
  no multi-battery or multi-site support.
- `max_grid_window` directives only constrain the hours listed; if two
  `max_grid_window` directives target the same hour, the tighter limit wins.
- No authentication/rate limiting — not intended for public deployment as-is.
- The LP solver (CBC via PuLP) runs synchronously in-process; fine for a
  24-hour single-scenario horizon but not batched/concurrent-safe at scale.
