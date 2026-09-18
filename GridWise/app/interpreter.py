from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.validator import validate_interpretations


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


def _build_prompt(
    operator_notes: list[str],
) -> str:
    """
    Build the user prompt.
    """

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
"""


def _call_llm(
    operator_notes: list[str],
) -> Any:
    """
    Call Gemini using structured JSON output.
    """

    client = _get_client()

    prompt = _build_prompt(
        operator_notes
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
) -> list[dict]:
    """
    Main Person A contract.

    Input:
        list[str]

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
            cleaned_notes
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

    return validate_interpretations(
        raw_output,
        number_of_notes,
    )