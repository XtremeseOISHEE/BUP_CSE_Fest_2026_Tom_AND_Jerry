from app.guardrail_validator import validate_interpretations


def test_valid_solar_reduction():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13, 14],
                "factor": 0.2,
            },
            "explanation": "Solar output reduced.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["note_index"] == 0
    assert result[0]["applies"] is True
    assert result[0]["directive_type"] == "solar_reduction"
    assert result[0]["structured_adjustment"] == {
        "hours": [13, 14],
        "factor": 0.2,
    }


def test_valid_minimum_battery_reserve():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "minimum_battery_reserve",
            "structured_adjustment": {
                "hours": [18, 19, 20],
                "minimum_energy_kwh": 5.0,
            },
            "explanation": "Battery reserve required.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "minimum_battery_reserve"
    assert result[0]["structured_adjustment"] == {
        "hours": [18, 19, 20],
        "minimum_energy_kwh": 5.0,
    }


def test_valid_no_charge_window():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [14, 15],
            },
            "explanation": "Charging disabled.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_charge_window"


def test_valid_no_discharge_window():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_discharge_window",
            "structured_adjustment": {
                "hours": [19, 20, 21],
            },
            "explanation": "Discharging disabled.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_discharge_window"


def test_valid_max_grid_window():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "max_grid_window",
            "structured_adjustment": {
                "hours": [17, 18],
                "max_grid_kwh": 3.0,
            },
            "explanation": "Grid consumption limited.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "max_grid_window"


def test_valid_no_op():
    raw = [
        {
            "note_index": 0,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Unrelated note.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"
    assert result[0]["applies"] is False
    assert result[0]["structured_adjustment"] is None


def test_unknown_directive_becomes_no_op():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "random_directive",
            "structured_adjustment": {},
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"
    assert result[0]["applies"] is False
    assert result[0]["structured_adjustment"] is None


def test_duplicate_hours():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [14, 15, 15],
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_unsorted_hours():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [15, 14],
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_out_of_range_hours():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [24],
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_negative_hours():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [-1],
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_invalid_factor_above_one():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13],
                "factor": 1.5,
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_invalid_factor_below_zero():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13],
                "factor": -0.2,
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_missing_factor():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13],
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_negative_battery_reserve():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "minimum_battery_reserve",
            "structured_adjustment": {
                "hours": [13],
                "minimum_energy_kwh": -5,
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_missing_battery_reserve():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "minimum_battery_reserve",
            "structured_adjustment": {
                "hours": [13],
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_negative_grid_limit():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "max_grid_window",
            "structured_adjustment": {
                "hours": [13],
                "max_grid_kwh": -2,
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_missing_grid_limit():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "max_grid_window",
            "structured_adjustment": {
                "hours": [13],
            },
            "explanation": "Bad.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["directive_type"] == "no_op"


def test_no_op_applies_true_is_fixed():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Nothing to do.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["applies"] is False
    assert result[0]["directive_type"] == "no_op"
    assert result[0]["structured_adjustment"] is None


def test_false_applies_becomes_no_op():
    raw = [
        {
            "note_index": 0,
            "applies": False,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13],
                "factor": 0.2,
            },
            "explanation": "Contradictory.",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert result[0]["applies"] is False
    assert result[0]["directive_type"] == "no_op"
    assert result[0]["structured_adjustment"] is None


def test_missing_note_mapping():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [13],
            },
            "explanation": "First note.",
        }
    ]

    result = validate_interpretations(raw, 2)

    assert len(result) == 2
    assert result[0]["note_index"] == 0
    assert result[1]["note_index"] == 1
    assert result[1]["directive_type"] == "no_op"


def test_duplicate_note_index():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [13],
            },
            "explanation": "First.",
        },
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_discharge_window",
            "structured_adjustment": {
                "hours": [14],
            },
            "explanation": "Duplicate.",
        },
    ]

    result = validate_interpretations(raw, 1)

    assert len(result) == 1
    assert result[0]["note_index"] == 0
    assert result[0]["directive_type"] == "no_op"


def test_malformed_llm_output():
    result = validate_interpretations(
        "THIS IS NOT JSON",
        3,
    )

    assert len(result) == 3

    for index, item in enumerate(result):
        assert item["note_index"] == index
        assert item["applies"] is False
        assert item["directive_type"] == "no_op"
        assert item["structured_adjustment"] is None


def test_none_llm_output():
    result = validate_interpretations(
        None,
        2,
    )

    assert len(result) == 2

    assert result[0]["directive_type"] == "no_op"
    assert result[1]["directive_type"] == "no_op"


def test_empty_llm_output():
    result = validate_interpretations(
        [],
        3,
    )

    assert len(result) == 3

    for index, item in enumerate(result):
        assert item["note_index"] == index
        assert item["directive_type"] == "no_op"


def test_exactly_five_fields():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {
                "hours": [10, 11],
            },
            "explanation": "No charging.",
            "extra_field": "should not survive",
        }
    ]

    result = validate_interpretations(raw, 1)

    assert set(result[0].keys()) == {
        "note_index",
        "applies",
        "directive_type",
        "structured_adjustment",
        "explanation",
    }