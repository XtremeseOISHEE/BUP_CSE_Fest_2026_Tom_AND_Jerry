from unittest.mock import patch

from app.interpreter import interpret_notes


def test_three_note_contract():

    notes = [
        "Solar output will drop to about 20% from 1 PM to 3 PM.",
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
            "explanation": "Solar output is reduced.",
        },
        {
            "note_index": 1,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [14, 15],
            },
            "explanation": "Battery charging is prohibited.",
        },
        {
            "note_index": 2,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "The note is unrelated.",
        },
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value=fake_llm_output,
    ):

        result = interpret_notes(notes)

    assert len(result) == 3

    assert result[0]["note_index"] == 0
    assert result[1]["note_index"] == 1
    assert result[2]["note_index"] == 2

    assert result[0]["directive_type"] == "solar_reduction"
    assert result[1]["directive_type"] == "no_charge_window"
    assert result[2]["directive_type"] == "no_op"


def test_solar_example():

    notes = [
        "Solar output will drop to about 20% from 1 PM to 3 PM."
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
            "explanation": "Solar output is reduced.",
        }
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value=fake_llm_output,
    ):

        result = interpret_notes(notes)

    item = result[0]

    assert item["note_index"] == 0
    assert item["applies"] is True
    assert item["directive_type"] == "solar_reduction"

    assert item["structured_adjustment"]["hours"] == [
        13,
        14,
    ]

    assert item["structured_adjustment"]["factor"] == 0.2


def test_charge_window_example():

    notes = [
        "Do not charge the battery between 2 PM and 4 PM."
    ]

    fake_llm_output = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [14, 15],
            },
            "explanation": "Charging is prohibited.",
        }
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value=fake_llm_output,
    ):

        result = interpret_notes(notes)

    item = result[0]

    assert item["directive_type"] == "no_charge_window"
    assert item["structured_adjustment"]["hours"] == [
        14,
        15,
    ]


def test_irrelevant_note():

    notes = [
        "The cafeteria menu changes tomorrow."
    ]

    fake_llm_output = [
        {
            "note_index": 0,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "This does not affect energy scheduling.",
        }
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value=fake_llm_output,
    ):

        result = interpret_notes(notes)

    item = result[0]

    assert item["note_index"] == 0
    assert item["applies"] is False
    assert item["directive_type"] == "no_op"
    assert item["structured_adjustment"] is None


def test_llm_failure_never_crashes():

    notes = [
        "Solar output will drop tomorrow."
    ]

    with patch(
        "app.interpreter._call_llm",
        side_effect=RuntimeError("API failure"),
    ):

        result = interpret_notes(notes)

    assert len(result) == 1

    assert result[0]["note_index"] == 0
    assert result[0]["applies"] is False
    assert result[0]["directive_type"] == "no_op"
    assert result[0]["structured_adjustment"] is None


def test_malformed_llm_output():

    notes = [
        "Do not charge from 2 PM to 4 PM.",
        "The weather is cloudy.",
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value="INVALID JSON",
    ):

        result = interpret_notes(notes)

    assert len(result) == 2

    assert result[0]["directive_type"] == "no_op"
    assert result[1]["directive_type"] == "no_op"


def test_invalid_llm_directive_is_safely_rejected():

    notes = [
        "Do something strange with the battery."
    ]

    fake_llm_output = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "battery_magic",
            "structured_adjustment": {},
            "explanation": "Invalid directive.",
        }
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value=fake_llm_output,
    ):

        result = interpret_notes(notes)

    assert result[0]["directive_type"] == "no_op"
    assert result[0]["applies"] is False
    assert result[0]["structured_adjustment"] is None


def test_wrong_hour_order_is_rejected():

    notes = [
        "Do not charge from 2 PM to 4 PM."
    ]

    fake_llm_output = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [15, 14],
            },
            "explanation": "Bad hour order.",
        }
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value=fake_llm_output,
    ):

        result = interpret_notes(notes)

    assert result[0]["directive_type"] == "no_op"


def test_missing_note_gets_no_op():

    notes = [
        "Do not charge from 2 PM to 4 PM.",
        "Solar output drops at noon.",
        "Something unrelated.",
    ]

    fake_llm_output = [
        {
            "note_index": 0,
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

    assert len(result) == 3

    assert result[0]["note_index"] == 0
    assert result[1]["note_index"] == 1
    assert result[2]["note_index"] == 2

    assert result[1]["directive_type"] == "no_op"


def test_output_always_has_exactly_five_keys():

    notes = [
        "Do not charge the battery from 10 AM to noon."
    ]

    fake_llm_output = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [10, 11],
            },
            "explanation": "Charging disabled.",
            "unexpected": "bad field",
        }
    ]

    with patch(
        "app.interpreter._call_llm",
        return_value=fake_llm_output,
    ):

        result = interpret_notes(notes)

    assert set(result[0].keys()) == {
        "note_index",
        "applies",
        "directive_type",
        "structured_adjustment",
        "explanation",
    }


def test_more_than_three_notes_are_safe():

    notes = [
        "Note one.",
        "Note two.",
        "Note three.",
        "Note four.",
    ]

    result = interpret_notes(notes)

    assert len(result) == 4

    for index, item in enumerate(result):

        assert item["note_index"] == index
        assert item["applies"] is False
        assert item["directive_type"] == "no_op"
        assert item["structured_adjustment"] is None