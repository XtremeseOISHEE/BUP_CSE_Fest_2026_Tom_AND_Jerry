from unittest.mock import patch

from app.interpreter import interpret_notes


def test_full_person_a_pipeline():

    notes = [
        "Solar output will drop to 20% from 1 PM to 3 PM.",
        "Do not charge the battery between 2 PM and 4 PM.",
        "The cafeteria menu changes tomorrow.",
    ]

    fake_llm_output = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13, 14],
                "factor": 0.2,
            },
            "explanation": "Solar reduction.",
        },
        {
            "note_index": 1,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [14, 15],
            },
            "explanation": "Charging disabled.",
        },
        {
            "note_index": 2,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Unrelated.",
        },
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value=fake_llm_output,
    ):

        result = interpret_notes(notes)

    # ---------------------------------------------------------
    # Fundamental contract
    # ---------------------------------------------------------

    assert len(result) == 3

    assert [
        item["note_index"]
        for item in result
    ] == [0, 1, 2]

    # ---------------------------------------------------------
    # First directive
    # ---------------------------------------------------------

    assert result[0]["directive_type"] == (
        "solar_reduction"
    )

    assert result[0][
        "structured_adjustment"
    ]["hours"] == [13, 14]

    assert result[0][
        "structured_adjustment"
    ]["factor"] == 0.2

    # ---------------------------------------------------------
    # Second directive
    # ---------------------------------------------------------

    assert result[1]["directive_type"] == (
        "no_charge_window"
    )

    assert result[1][
        "structured_adjustment"
    ]["hours"] == [14, 15]

    # ---------------------------------------------------------
    # Third directive
    # ---------------------------------------------------------

    assert result[2]["directive_type"] == "no_op"

    assert result[2]["applies"] is False

    assert result[2][
        "structured_adjustment"
    ] is None