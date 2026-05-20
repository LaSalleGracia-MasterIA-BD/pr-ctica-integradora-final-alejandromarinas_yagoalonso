"""Unit tests for the COVID-threshold decision rule.

These tests don't load a Keras model — they test the pure decision rule
`Predictor._apply_decision_rule` in isolation. The rule is:

    if P(COVID-19) >= COVID_THRESHOLD -> COVID-19
    else                               -> argmax(Normal, Pneumonia)

The rule is post-hoc thresholding on the model's raw softmax outputs and is
the operative decision rule for the API since Feature 16. See ADR-010 and
docs/model-evaluation/threshold-analysis.md.
"""
from __future__ import annotations

import pytest

from src.ml.predictor import (
    COVID_CLASS,
    COVID_THRESHOLD,
    DECISION_RULE,
    Predictor,
)


@pytest.fixture
def predictor_for_rule():
    """A Predictor whose _apply_decision_rule we can call.

    We bypass __init__ on purpose: we do NOT want to load the Keras model
    just to test a pure function. The rule depends on nothing on `self`.
    """
    p = Predictor.__new__(Predictor)
    return p


def test_threshold_constants_are_what_we_advertise():
    assert COVID_CLASS == "COVID-19"
    assert COVID_THRESHOLD == 0.35
    assert DECISION_RULE == "covid_threshold_0.35"


def test_p_covid_just_above_threshold_forces_covid(predictor_for_rule):
    """P(COVID)=0.36, P(Normal)=0.50: argmax says Normal, threshold says COVID."""
    probs = {"Normal": 0.50, "Pneumonia": 0.14, "COVID-19": 0.36}
    assert predictor_for_rule._apply_decision_rule(probs) == "COVID-19"


def test_p_covid_just_below_threshold_does_not_force_covid(predictor_for_rule):
    """P(COVID)=0.34, P(Normal)=0.50: threshold not met, argmax wins."""
    probs = {"Normal": 0.50, "Pneumonia": 0.16, "COVID-19": 0.34}
    assert predictor_for_rule._apply_decision_rule(probs) == "Normal"


def test_p_covid_exactly_at_threshold_forces_covid(predictor_for_rule):
    """Boundary condition: >= 0.35 (NOT strictly greater)."""
    probs = {"Normal": 0.40, "Pneumonia": 0.25, "COVID-19": 0.35}
    assert predictor_for_rule._apply_decision_rule(probs) == "COVID-19"


def test_p_covid_dominant_returns_covid(predictor_for_rule):
    """Trivial case: COVID is the argmax anyway."""
    probs = {"Normal": 0.10, "Pneumonia": 0.10, "COVID-19": 0.80}
    assert predictor_for_rule._apply_decision_rule(probs) == "COVID-19"


def test_below_threshold_argmax_normal(predictor_for_rule):
    probs = {"Normal": 0.60, "Pneumonia": 0.30, "COVID-19": 0.10}
    assert predictor_for_rule._apply_decision_rule(probs) == "Normal"


def test_below_threshold_argmax_pneumonia(predictor_for_rule):
    probs = {"Normal": 0.20, "Pneumonia": 0.55, "COVID-19": 0.25}
    assert predictor_for_rule._apply_decision_rule(probs) == "Pneumonia"


def test_zero_covid_probability_picks_argmax_of_others(predictor_for_rule):
    probs = {"Normal": 0.45, "Pneumonia": 0.55, "COVID-19": 0.0}
    assert predictor_for_rule._apply_decision_rule(probs) == "Pneumonia"


def test_threshold_rule_handles_tie_between_normal_and_pneumonia(predictor_for_rule):
    """If Normal and Pneumonia tie below threshold, max() picks first; deterministic."""
    probs = {"Normal": 0.34, "Pneumonia": 0.34, "COVID-19": 0.32}
    result = predictor_for_rule._apply_decision_rule(probs)
    assert result in {"Normal", "Pneumonia"}
