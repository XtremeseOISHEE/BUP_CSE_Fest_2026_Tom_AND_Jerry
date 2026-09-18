from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.guardrail_validator import _no_op, validate_interpretations


load_dotenv()


MODEL_NAME = "gemini-3.1-flash-lite"


SYSTEM_PROMPT = """
You are the GridWise operator-note interpreter.

Your ONLY job is to convert each operator note into one
structured directive.

You are NOT an optimizer.

You must NOT calculate battery schedules.

You must NOT calculate electricity costs.

You must NOT modify demand.

You must NOT modify solar production.

You must NOT invent information.

============================================================
ALLOWED DIRECTIVE TYPES
============================================================

You may ONLY use:

solar_reduction
minimum_battery_reserve
no_charge_window
no_discharge_window
max_grid_window
no_op

Never invent another directive type.


============================================================
ONE OUTPUT PER NOTE
============================================================

Every input note must receive exactly one output object.

Never skip a note.

note_index must equal the zero-based index of the input note.

Irrelevant or unrelated notes MUST become no_op.

If information necessary to create a directive is missing,
use no_op.

Do not guess.


============================================================
TIME CONVENTION
============================================================

Hours are whole-hour,
start-inclusive and end-exclusive.

Example:

"1 PM to 3 PM"

means:

[13, 14]

NOT:

[13, 14, 15]


Example:

"2 PM to 4 PM"

means:

[14, 15]


Hours must:

- be integers
- be between 0 and 23
- be unique
- be ascending


============================================================
SOLAR FACTOR CONVENTION
============================================================

factor means the usable fraction remaining.

"Solar output will drop to 20%"

means:

factor = 0.2


"Solar output will be reduced by 80%"

means:

factor = 0.2


Do NOT use factor = 0.8.


============================================================
RELATIVE QUANTITIES AND BATTERY CONTEXT
============================================================

The user prompt may contain a BATTERY CONTEXT block with:

capacity_kwh
initial_energy_kwh
minimum_energy_kwh   (the battery's normal base reserve)
max_charge_kwh_per_hour
max_discharge_kwh_per_hour

Use it ONLY to convert a quantity phrased relative to the
battery into an absolute kWh number. Output must always be
absolute kWh, never a percentage or a phrase.

Conversions for minimum_battery_reserve:

- "X% of battery capacity"        -> capacity_kwh * X / 100
- "half full" / "half charged"    -> capacity_kwh * 0.5
- "fully charged" / "full"        -> capacity_kwh
- "at its starting/initial level" -> initial_energy_kwh
- "N kWh above the normal reserve"-> minimum_energy_kwh + N

Round to at most 2 decimals. Never output a value above
capacity_kwh.

If the note uses an absolute kWh value, use it as written.

If a note is phrased relative to the battery but the BATTERY
CONTEXT block is missing, or is phrased relative to something
that is not in the BATTERY CONTEXT (for example peak demand or
yesterday's usage), use no_op. Do not guess.

solar_reduction already uses a fraction (factor), and
no_charge_window / no_discharge_window carry no quantity, so
the battery context does not change them.


============================================================
DIRECTIVE SHAPES
============================================================

solar_reduction:

{
    "hours": [int, ...],
    "factor": float
}


minimum_battery_reserve:

{
    "hours": [int, ...],
    "minimum_energy_kwh": float
}


no_charge_window:

{
    "hours": [int, ...]
}


no_discharge_window:

{
    "hours": [int, ...]
}


max_grid_window:

{
    "hours": [int, ...],
    "max_grid_kwh": float
}


no_op:

null


============================================================
WORKED EXAMPLES
============================================================

Example 1:

Input:

"Solar output will drop to about 20% from 1 PM to 3 PM."

Interpretation:

{
    "note_index": 0,
    "applies": true,
    "directive_type": "solar_reduction",
    "structured_adjustment": {
        "hours": [13, 14],
        "factor": 0.2
    },
    "explanation": "Solar availability is reduced during the specified period."
}


Example 2:

Input:

"Do not charge the battery between 2 PM and 4 PM."

Interpretation:

{
    "note_index": 0,
    "applies": true,
    "directive_type": "no_charge_window",
    "structured_adjustment": {
        "hours": [14, 15]
    },
    "explanation": "Battery charging is prohibited during the specified period."
}


Example 3:

Input (BATTERY CONTEXT capacity_kwh = 200):

"Keep at least 50% of the battery capacity stored from 6 PM until 9 PM."

Interpretation:

{
    "note_index": 0,
    "applies": true,
    "directive_type": "minimum_battery_reserve",
    "structured_adjustment": {
        "hours": [18, 19, 20],
        "minimum_energy_kwh": 100.0
    },
    "explanation": "50% of the 200 kWh capacity is 100 kWh, reserved during the period."
}


Example 4:

Input:

"The cafeteria menu changes tomorrow."

Interpretation:

{
    "note_index": 0,
    "applies": false,
    "directive_type": "no_op",
    "structured_adjustment": null,
    "explanation": "The note does not affect the energy schedule."
}


============================================================
SAFETY RULE
============================================================

If a note is ambiguous, unrelated, malformed, or lacks
necessary information, prefer no_op.

Never invent an energy directive.

A safe no_op is preferable to an unsupported directive.
"""


RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {

            "note_index": {
                "type": "INTEGER",
            },

            "applies": {
                "type": "BOOLEAN",
            },

            "directive_type": {
                "type": "STRING",
                "enum": [
                    "solar_reduction",
                    "minimum_battery_reserve",
                    "no_charge_window",
                    "no_discharge_window",
                    "max_grid_window",
                    "no_op",
                ],
            },

            "structured_adjustment": {
                "type": "OBJECT",
                "properties": {

                    "hours": {
                        "type": "ARRAY",
                        "items": {
                            "type": "INTEGER",
                        },
                    },

                    "factor": {
                        "type": "NUMBER",
                    },

                    "minimum_energy_kwh": {
                        "type": "NUMBER",
                    },

                    "max_grid_kwh": {
                        "type": "NUMBER",
                    },
                },
                "nullable": True,
            },

            "explanation": {
                "type": "STRING",
            },
        },

        "required": [
            "note_index",
            "applies",
            "directive_type",
            "structured_adjustment",
            "explanation",
        ],
    },
}


def _get_client() -> genai.Client:
    """
    Create Gemini client from environment variable.
    """

    api_key = os.getenv(
        "LLM_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "LLM_API_KEY environment variable is not set."
        )

    return genai.Client(
        api_key=api_key
    )


BATTERY_CONTEXT_FIELDS = (
    "capacity_kwh",
    "initial_energy_kwh",
    "minimum_energy_kwh",
    "max_charge_kwh_per_hour",
    "max_discharge_kwh_per_hour",
)


def _battery_context(
    battery: Any,
) -> dict[str, float]:
    """
    Reduce a battery dict/model to its known numeric fields.
    """

    if battery is None:
        return {}

    if hasattr(battery, "model_dump"):
        battery = battery.model_dump()

    if not isinstance(battery, dict):
        return {}

    return {
        field: float(battery[field])
        for field in BATTERY_CONTEXT_FIELDS
        if isinstance(battery.get(field), (int, float))
        and not isinstance(battery.get(field), bool)
    }


def _build_prompt(
    operator_notes: list[str],
    battery: Any = None,
) -> str:
    """
    Build the user prompt.
    """

    context = _battery_context(
        battery
    )

    if context:

        battery_block = (
            "BATTERY CONTEXT (use only to resolve "
            "relative quantities):\n"
            + "\n".join(
                f"{field}: {value:g}"
                for field, value in context.items()
            )
        )

    else:

        battery_block = (
            "BATTERY CONTEXT: not provided."
        )

    numbered_notes = "\n".join(
        f"{index}: {note}"
        for index, note in enumerate(
            operator_notes
        )
    )

    return f"""
Interpret the following GridWise operator notes.

There are exactly {len(operator_notes)} notes.

You MUST return exactly one interpretation
for every note.

{battery_block}

INPUT NOTES:

{numbered_notes}

Remember:

- Preserve note_index.
- Do not skip notes.
- Irrelevant notes become no_op.
- Do not invent missing values.
- Use only the six allowed directive types.
- Use exact structured_adjustment field names.
- Follow start-inclusive/end-exclusive hours.
- factor means usable fraction remaining.
- Convert battery-relative quantities to absolute kWh
  using the BATTERY CONTEXT; no_op if it is missing.
"""


def _call_llm(
    operator_notes: list[str],
    battery: Any = None,
) -> Any:
    """
    Call Gemini using structured JSON output.
    """

    client = _get_client()

    prompt = _build_prompt(
        operator_notes,
        battery,
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )

    if not response.text:

        raise ValueError(
            "Gemini returned an empty response."
        )

    return json.loads(
        response.text
    )


def interpret_notes(
    operator_notes: list[str],
    battery: dict | None = None,
) -> list[dict]:
    """
    Main Person A contract.

    Input:
        list[str]
        battery (optional): request battery dict, used only to
        resolve relative quantities such as "50% of capacity".

    Output:
        list[dict]

    There is exactly one validated output
    per input note.

    Raw LLM output is NEVER returned directly.
    """

    # ---------------------------------------------------------
    # Top-level input validation
    # ---------------------------------------------------------

    if not isinstance(
        operator_notes,
        list,
    ):
        return []

    if len(operator_notes) == 0:
        return []

    # Person B's OptimizeRequest guarantees 1-3 notes.
    #
    # If called directly with more than 3 notes, do not
    # silently throw notes away.
    if len(operator_notes) > 3:

        return [
            {
                "note_index": index,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": (
                    "Invalid number of operator notes; "
                    "safely mapped to no_op."
                ),
            }
            for index in range(
                len(operator_notes)
            )
        ]

    # ---------------------------------------------------------
    # Clean input
    # ---------------------------------------------------------

    cleaned_notes: list[str] = []

    for note in operator_notes:

        if not isinstance(
            note,
            str,
        ):

            cleaned_notes.append("")

        else:

            cleaned_notes.append(
                note.strip()
            )

    number_of_notes = len(
        cleaned_notes
    )

    # ---------------------------------------------------------
    # Call Gemini safely
    # ---------------------------------------------------------

    try:

        raw_output = _call_llm(
            cleaned_notes,
            battery,
        )

    except Exception:

        # API failure, timeout, malformed JSON,
        # quota error, etc.
        #
        # Never crash Person B's request.
        raw_output = None

    # ---------------------------------------------------------
    # Deterministic validation
    # ---------------------------------------------------------

    results = validate_interpretations(
        raw_output,
        number_of_notes,
    )

    # A reserve above capacity is infeasible for the optimizer
    # (e.g. an LLM arithmetic slip or a "150%" note): degrade to no_op.
    capacity = _battery_context(
        battery
    ).get(
        "capacity_kwh"
    )

    if capacity is not None:

        for index, item in enumerate(
            results
        ):

            adjustment = item.get(
                "structured_adjustment"
            )

            if (
                item.get("directive_type")
                == "minimum_battery_reserve"
                and adjustment
                and adjustment["minimum_energy_kwh"] > capacity
            ):

                results[index] = _no_op(
                    item["note_index"],
                    "Requested reserve exceeds battery capacity; "
                    "safely mapped to no_op.",
                )

    return results