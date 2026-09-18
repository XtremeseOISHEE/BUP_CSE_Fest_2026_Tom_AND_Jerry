from app.schemas import DirectiveInterpretation
from app.interpreter import interpret_notes


def test_person_a_output_matches_person_b_schema():

    notes = [
        "Solar output will drop to 20% from 1 PM to 3 PM.",
        "Do not charge the battery between 2 PM and 4 PM.",
        "The cafeteria menu changes tomorrow.",
    ]

    # We don't want this contract test to call the real API.
    # Therefore this test only validates the schema using
    # representative Person-A output.

    sample_output = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13, 14],
                "factor": 0.2,
            },
            "explanation": "Solar output is reduced.",
        },
        {
            "note_index": 1,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [14, 15],
            },
            "explanation": "Charging is prohibited.",
        },
        {
            "note_index": 2,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Unrelated note.",
        },
    ]

    validated = [
        DirectiveInterpretation(**item)
        for item in sample_output
    ]

    assert len(validated) == len(notes)

    for item in validated:

        dumped = item.model_dump()

        assert set(dumped.keys()) == {
            "note_index",
            "applies",
            "directive_type",
            "structured_adjustment",
            "explanation",
        }