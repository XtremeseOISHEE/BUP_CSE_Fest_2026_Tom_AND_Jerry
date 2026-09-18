import json
from pathlib import Path

import pytest

from app.interpreter import interpret_notes


SAMPLE_FILE = Path(__file__).resolve().parents[1] / "sample_cases.json"


def normalize_directives(items):
    """
    Ignore explanation text because the public specification says
    explanation wording does not need to match byte-for-byte.
    """
    normalized = []

    for item in items:
        normalized.append({
            "note_index": item["note_index"],
            "applies": item["applies"],
            "directive_type": item["directive_type"],
            "structured_adjustment": item["structured_adjustment"],
        })

    return normalized


@pytest.fixture(scope="module")
def sample_cases():
    if not SAMPLE_FILE.exists():
        pytest.fail(
            f"Missing public sample file: {SAMPLE_FILE}\n"
            "Place the official sample JSON at the project root as "
            "'sample_cases.json'."
        )

    with SAMPLE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert "_meta" in data
    assert "cases" in data

    assert data["_meta"]["case_count"] == 10
    assert len(data["cases"]) == 10

    return data["cases"]


def test_public_sample_pack_has_10_cases(sample_cases):
    assert len(sample_cases) == 10


@pytest.mark.parametrize("case_number", range(10))
def test_public_sample_case_structure(sample_cases, case_number):
    case = sample_cases[case_number]

    assert "id" in case
    assert "input" in case
    assert "expected_output" in case

    assert "operator_notes" in case["input"]
    assert "directive_interpretation" in case["expected_output"]

    notes = case["input"]["operator_notes"]
    expected = case["expected_output"]["directive_interpretation"]

    assert 1 <= len(notes) <= 3
    assert len(expected) == len(notes)


@pytest.mark.parametrize("case_number", range(10))
def test_public_sample_directive_semantics(sample_cases, case_number, monkeypatch):
    """
    Tests Person A against the official public expected directive semantics.

    The LLM itself is mocked, because this test should:
      - not consume API quota
      - not depend on network
      - test the interpreter/validator contract deterministically
    """

    case = sample_cases[case_number]

    notes = case["input"]["operator_notes"]
    expected = case["expected_output"]["directive_interpretation"]

    # Feed the official expected interpretation through our validator.
    monkeypatch.setattr(
        "app.interpreter._call_llm",
        lambda operator_notes: expected
    )

    actual = interpret_notes(notes)

    assert normalize_directives(actual) == normalize_directives(expected)


@pytest.mark.parametrize("case_number", range(10))
def test_public_sample_note_indices_are_complete(sample_cases, case_number):
    case = sample_cases[case_number]

    notes = case["input"]["operator_notes"]
    expected = case["expected_output"]["directive_interpretation"]

    expected_indices = list(range(len(notes)))
    actual_indices = [item["note_index"] for item in expected]

    assert actual_indices == expected_indices


@pytest.mark.parametrize("case_number", range(10))
def test_public_sample_no_op_rules(sample_cases, case_number):
    case = sample_cases[case_number]

    expected = case["expected_output"]["directive_interpretation"]

    for item in expected:
        if item["directive_type"] == "no_op":
            assert item["applies"] is False
            assert item["structured_adjustment"] is None


@pytest.mark.parametrize("case_number", range(10))
def test_public_sample_non_no_op_rules(sample_cases, case_number):
    case = sample_cases[case_number]

    expected = case["expected_output"]["directive_interpretation"]

    for item in expected:
        if item["directive_type"] != "no_op":
            assert item["applies"] is True
            assert item["structured_adjustment"] is not None


@pytest.mark.parametrize("case_number", range(10))
def test_public_sample_hours_are_valid(sample_cases, case_number):
    case = sample_cases[case_number]

    expected = case["expected_output"]["directive_interpretation"]

    for item in expected:
        adjustment = item["structured_adjustment"]

        if adjustment is None:
            continue

        hours = adjustment["hours"]

        # Non-empty
        assert len(hours) > 0

        # Integers
        assert all(isinstance(h, int) and not isinstance(h, bool)
                   for h in hours)

        # 0–23
        assert all(0 <= h <= 23 for h in hours)

        # Unique
        assert len(hours) == len(set(hours))

        # Ascending
        assert hours == sorted(hours)


@pytest.mark.parametrize("case_number", range(10))
def test_public_sample_solar_factors_are_valid(sample_cases, case_number):
    case = sample_cases[case_number]

    expected = case["expected_output"]["directive_interpretation"]

    for item in expected:
        if item["directive_type"] != "solar_reduction":
            continue

        adjustment = item["structured_adjustment"]

        assert "factor" in adjustment
        assert 0 <= adjustment["factor"] <= 1