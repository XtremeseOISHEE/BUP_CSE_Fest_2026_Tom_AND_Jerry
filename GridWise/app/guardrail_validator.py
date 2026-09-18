from __future__ import annotations

from typing import Any

from app.schemas import DirectiveInterpretation


ALLOWED_DIRECTIVE_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


def _no_op(
    note_index: int,
    explanation: str,
) -> dict:
    """
    Safest fallback for an invalid or uncertain interpretation.
    """

    return {
        "note_index": note_index,
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": explanation,
    }


def _is_number(value: Any) -> bool:
    """
    True for int/float, but not bool.
    """

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def _validate_hours(value: Any) -> bool:
    """
    Validate GridWise hour representation.

    Requirements:
    - list
    - integers only
    - values 0..23
    - no duplicates
    - ascending order
    """

    if not isinstance(value, list):
        return False

    if not all(
        isinstance(hour, int)
        and not isinstance(hour, bool)
        for hour in value
    ):
        return False

    if any(
        hour < 0 or hour > 23
        for hour in value
    ):
        return False

    if len(value) != len(set(value)):
        return False

    if value != sorted(value):
        return False

    return True


def _validate_adjustment(
    directive_type: str,
    adjustment: Any,
) -> bool:
    """
    Validate structured_adjustment according
    to the directive type.
    """

    # ---------------------------------------------------------
    # no_op
    # ---------------------------------------------------------

    if directive_type == "no_op":
        return adjustment is None

    if not isinstance(adjustment, dict):
        return False

    # ---------------------------------------------------------
    # solar_reduction
    # ---------------------------------------------------------

    if directive_type == "solar_reduction":

        if set(adjustment.keys()) != {
            "hours",
            "factor",
        }:
            return False

        if not _validate_hours(
            adjustment["hours"]
        ):
            return False

        factor = adjustment["factor"]

        if not _is_number(factor):
            return False

        if factor < 0 or factor > 1:
            return False

        return True

    # ---------------------------------------------------------
    # minimum_battery_reserve
    # ---------------------------------------------------------

    if directive_type == "minimum_battery_reserve":

        if set(adjustment.keys()) != {
            "hours",
            "minimum_energy_kwh",
        }:
            return False

        if not _validate_hours(
            adjustment["hours"]
        ):
            return False

        minimum_energy_kwh = adjustment[
            "minimum_energy_kwh"
        ]

        if not _is_number(
            minimum_energy_kwh
        ):
            return False

        if minimum_energy_kwh < 0:
            return False

        return True

    # ---------------------------------------------------------
    # no_charge_window
    # ---------------------------------------------------------

    if directive_type == "no_charge_window":

        if set(adjustment.keys()) != {
            "hours",
        }:
            return False

        return _validate_hours(
            adjustment["hours"]
        )

    # ---------------------------------------------------------
    # no_discharge_window
    # ---------------------------------------------------------

    if directive_type == "no_discharge_window":

        if set(adjustment.keys()) != {
            "hours",
        }:
            return False

        return _validate_hours(
            adjustment["hours"]
        )

    # ---------------------------------------------------------
    # max_grid_window
    # ---------------------------------------------------------

    if directive_type == "max_grid_window":

        if set(adjustment.keys()) != {
            "hours",
            "max_grid_kwh",
        }:
            return False

        if not _validate_hours(
            adjustment["hours"]
        ):
            return False

        max_grid_kwh = adjustment[
            "max_grid_kwh"
        ]

        if not _is_number(
            max_grid_kwh
        ):
            return False

        if max_grid_kwh < 0:
            return False

        return True

    return False


def _validate_single(
    raw: Any,
    expected_note_index: int,
) -> dict:
    """
    Validate a single LLM interpretation.
    """

    # ---------------------------------------------------------
    # Must be a dictionary
    # ---------------------------------------------------------

    if not isinstance(raw, dict):

        return _no_op(
            expected_note_index,
            "Invalid LLM output; safely mapped to no_op.",
        )

    # ---------------------------------------------------------
    # directive_type
    # ---------------------------------------------------------

    directive_type = raw.get(
        "directive_type"
    )

    if directive_type not in ALLOWED_DIRECTIVE_TYPES:

        return _no_op(
            expected_note_index,
            "Unknown directive type; safely mapped to no_op.",
        )

    # ---------------------------------------------------------
    # applies
    # ---------------------------------------------------------

    applies = raw.get("applies")

    if not isinstance(applies, bool):

        return _no_op(
            expected_note_index,
            "Invalid applies value; safely mapped to no_op.",
        )

    # ---------------------------------------------------------
    # no_op must have applies=False
    # ---------------------------------------------------------

    if directive_type == "no_op":

        applies = False

    # ---------------------------------------------------------
    # applies=False must mean no_op
    # ---------------------------------------------------------

    elif applies is False:

        directive_type = "no_op"

    # ---------------------------------------------------------
    # structured_adjustment
    # ---------------------------------------------------------

    adjustment = raw.get(
        "structured_adjustment"
    )

    if directive_type == "no_op":

        adjustment = None

    else:

        if not _validate_adjustment(
            directive_type,
            adjustment,
        ):

            return _no_op(
                expected_note_index,
                "Invalid structured adjustment; safely mapped to no_op.",
            )

    # ---------------------------------------------------------
    # explanation
    # ---------------------------------------------------------

    explanation = raw.get(
        "explanation"
    )

    if not isinstance(
        explanation,
        str,
    ):

        explanation = "Validated directive."

    explanation = explanation.strip()

    # ---------------------------------------------------------
    # Construct exact output object
    # ---------------------------------------------------------

    result = {
        "note_index": expected_note_index,
        "applies": applies,
        "directive_type": directive_type,
        "structured_adjustment": adjustment,
        "explanation": explanation,
    }

    # ---------------------------------------------------------
    # Validate against Person B's schema
    # ---------------------------------------------------------

    try:

        validated = DirectiveInterpretation(
            **result
        )

        return validated.model_dump()

    except Exception:

        return _no_op(
            expected_note_index,
            "Shared schema validation failed; safely mapped to no_op.",
        )


def validate_interpretations(
    raw_output: Any,
    number_of_notes: int,
) -> list[dict]:
    """
    Deterministically validate LLM output.

    Guarantees:

    - exactly one output per input note
    - correct note ordering
    - no duplicate/missing note indices
    - invalid directives become no_op
    - malformed LLM output never crashes the request
    """

    if not isinstance(
        number_of_notes,
        int,
    ):
        return []

    if number_of_notes < 0:
        return []

    # ---------------------------------------------------------
    # Entire LLM response malformed
    # ---------------------------------------------------------

    if not isinstance(
        raw_output,
        list,
    ):

        return [
            _no_op(
                index,
                "LLM output was malformed; safely mapped to no_op.",
            )
            for index in range(
                number_of_notes
            )
        ]

    # ---------------------------------------------------------
    # Build note_index mapping
    # ---------------------------------------------------------

    candidate_by_index: dict[int, Any] = {}

    for item in raw_output:

        if not isinstance(
            item,
            dict,
        ):
            continue

        raw_index = item.get(
            "note_index"
        )

        if not isinstance(
            raw_index,
            int,
        ):
            continue

        if (
            raw_index < 0
            or raw_index >= number_of_notes
        ):
            continue

        # Duplicate index is unsafe.
        if raw_index in candidate_by_index:

            candidate_by_index[
                raw_index
            ] = None

        else:

            candidate_by_index[
                raw_index
            ] = item

    # ---------------------------------------------------------
    # Produce exact ordered output
    # ---------------------------------------------------------

    results: list[dict] = []

    for index in range(
        number_of_notes
    ):

        raw = candidate_by_index.get(
            index
        )

        # Missing/duplicate mapping.
        if raw is None:

            results.append(
                _no_op(
                    index,
                    "Missing or duplicate note mapping; safely mapped to no_op.",
                )
            )

            continue

        results.append(
            _validate_single(
                raw,
                expected_note_index=index,
            )
        )

    return results