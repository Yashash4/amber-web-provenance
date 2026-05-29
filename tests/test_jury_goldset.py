"""Tests for the gold-set + precision/recall metrics (mocked jury).

No network: a scripted client lets us drive the metric math deterministically
and confirm the fixture is well-formed and clearly labeled.
"""

from __future__ import annotations

import json

from amber.jury import taxonomy
from amber.jury.client import JuryModels
from amber.jury.goldset import (
    GOLD_SET,
    GoldExample,
    evaluate_goldset,
    score_predictions,
)
from tests.test_jury_consensus import _reply

MODELS = JuryModels(openai="m-openai", google="m-google", anthropic="m-anthropic")


# --------------------------------------------------------------------------- #
# score_predictions (pure metric math)
# --------------------------------------------------------------------------- #
def test_perfect_predictions():
    expected = ["A", "B", "A", "B"]
    m = score_predictions("x", expected, list(expected))
    assert m.accuracy == 1.0
    assert m.per_label["A"].precision == 1.0
    assert m.per_label["A"].recall == 1.0
    assert m.macro_f1 == 1.0


def test_precision_recall_math():
    # expected: A A B ; predicted: A B B
    # Label A: tp=1 (pos0), fp=0, fn=1 (pos1) -> P=1.0 R=0.5
    # Label B: tp=1 (pos2), fp=1 (pos1), fn=0 -> P=0.5 R=1.0
    m = score_predictions("x", ["A", "A", "B"], ["A", "B", "B"])
    assert m.accuracy == 2 / 3
    assert m.per_label["A"].precision == 1.0
    assert m.per_label["A"].recall == 0.5
    assert m.per_label["B"].precision == 0.5
    assert m.per_label["B"].recall == 1.0


def test_length_mismatch_raises():
    import pytest

    with pytest.raises(ValueError):
        score_predictions("x", ["A"], ["A", "B"])


def test_route_to_human_scored_as_a_label():
    # A clear case routed to human is a miss, reflected in the metric.
    m = score_predictions(
        "consensus",
        [taxonomy.PROHIBITED_GEO_BLOCKING],
        [taxonomy.ROUTE_TO_HUMAN],
    )
    assert m.accuracy == 0.0


# --------------------------------------------------------------------------- #
# The fixture is well-formed and clearly labeled
# --------------------------------------------------------------------------- #
def test_goldset_examples_are_well_formed():
    assert len(GOLD_SET) >= 12
    for ex in GOLD_SET:
        assert isinstance(ex, GoldExample)
        assert taxonomy.is_valid_label(ex.expected_label)
        assert ex.facts["schema"].startswith("amber/facts@2")
        # Every fixture is clearly marked as methodology data, not production.
        assert "FIXTURE" in ex.facts["sku_label"]


def test_goldset_covers_multiple_labels():
    labels = {ex.expected_label for ex in GOLD_SET}
    assert taxonomy.PROHIBITED_GEO_BLOCKING in labels
    assert taxonomy.TAX_DUTY_ARTIFACT in labels
    assert taxonomy.INSUFFICIENT_INFO in labels
    assert taxonomy.PERMITTED_OBJECTIVE_JUSTIFICATION in labels


# --------------------------------------------------------------------------- #
# evaluate_goldset end-to-end with a perfect mocked oracle
# --------------------------------------------------------------------------- #
class OracleClient:
    """A mock client that answers each example with its GROUND-TRUTH label.

    It keys off the fixture's distinguishing facts so we can prove the pipeline
    (run jury -> consensus -> score) yields 100% when the models are perfect.
    """

    def __init__(self, models):
        self._models = models
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, *, model, messages, **kwargs):
        user = messages[-1]["content"]
        label = _oracle_label(user)
        content = _reply(label)

        class _M:
            def __init__(self, c):
                self.message = type("X", (), {"content": c})

        class _R:
            def __init__(self, c):
                self.choices = [_M(c)]

        return _R(content)


def _oracle_label(user_prompt: str) -> str:
    """Infer the correct label from the fixture facts embedded in the prompt."""
    data = json.loads(user_prompt.split("\n", 1)[1])
    cc = data["cross_country_comparison"]
    primary = cc.get("primary_finding")
    states = cc.get("per_country_states", {})
    flat = {s for sts in states.values() for s in sts}
    if primary == "ACCESS_OR_PAYMENT_DENIAL":
        return taxonomy.PROHIBITED_GEO_BLOCKING
    if primary == "INCONCLUSIVE" or "INCONCLUSIVE" in flat or len(states) < 2:
        return taxonomy.INSUFFICIENT_INFO
    if primary == "NO_NET_DELTA":
        return taxonomy.TAX_DUTY_ARTIFACT
    if primary == "NET_OF_TAX_PRICE_DELTA":
        return taxonomy.PERMITTED_OBJECTIVE_JUSTIFICATION
    return taxonomy.INSUFFICIENT_INFO


def test_evaluate_goldset_perfect_oracle_scores_100():
    client = OracleClient(MODELS)
    report = evaluate_goldset(client=client, models=MODELS)
    assert report.n_examples == len(GOLD_SET)
    assert report.consensus.accuracy == 1.0
    for name in ("openai", "google", "anthropic"):
        assert report.per_model[name].accuracy == 1.0
    # The report dict carries the fixture disclaimer.
    d = report.as_dict()
    assert "NOT real" in d["fixture_disclaimer"]
    assert len(d["rows"]) == len(GOLD_SET)


def test_evaluate_goldset_with_one_dissenting_model_still_consensus_correct():
    # openai + google = oracle; anthropic always wrong. Consensus still right.
    class TwoRightOneWrong(OracleClient):
        def create(self, *, model, messages, **kwargs):
            if model == "m-anthropic":
                messages = list(messages)
                # Force a wrong-but-valid label.
                class _M:
                    def __init__(self, c):
                        self.message = type("X", (), {"content": c})

                class _R:
                    def __init__(self, c):
                        self.choices = [_M(c)]

                return _R(_reply(taxonomy.DYNAMIC_PRICING))
            return super().create(model=model, messages=messages, **kwargs)

    report = evaluate_goldset(client=TwoRightOneWrong(MODELS), models=MODELS)
    # The two-of-three majority keeps consensus perfect even with a bad juror.
    assert report.consensus.accuracy == 1.0
    assert report.per_model["anthropic"].accuracy == 0.0
