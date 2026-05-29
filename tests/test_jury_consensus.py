"""Tests for the jury: reply parsing, consensus logic, and the full run.

The AI/ML API is MOCKED here — no network, no credits. A ``FakeClient`` returns
scripted per-model content so we can drive every consensus branch
deterministically (majority, unanimous, tie -> ROUTE_TO_HUMAN, and a model
error counting as a non-vote).
"""

from __future__ import annotations

import json

from amber.jury import taxonomy
from amber.jury.client import JuryModels
from amber.jury.jury import (
    JurorVerdict,
    consensus,
    parse_model_reply,
    run_jury,
)

MODELS = JuryModels(openai="m-openai", google="m-google", anthropic="m-anthropic")


# --------------------------------------------------------------------------- #
# A mock OpenAI-SDK-shaped client.
# --------------------------------------------------------------------------- #
class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class FakeClient:
    """Mimics ``client.chat.completions.create(model=...)``.

    ``by_model`` maps a model id to either a string reply or an Exception to
    raise (to exercise the error -> non-vote path).
    """

    def __init__(self, by_model: dict):
        self._by_model = by_model
        self.calls: list[str] = []
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, *, model, messages, **kwargs):  # noqa: D401 - SDK shape
        self.calls.append(model)
        result = self._by_model[model]
        if isinstance(result, Exception):
            raise result
        return _Resp(result)


def _reply(label: str, rationale: str = "because Reg 2018/302") -> str:
    return json.dumps({"label": label, "rationale": rationale})


# --------------------------------------------------------------------------- #
# parse_model_reply
# --------------------------------------------------------------------------- #
def test_parse_plain_json():
    label, rationale = parse_model_reply(_reply(taxonomy.TAX_DUTY_ARTIFACT, "vat only"))
    assert label == taxonomy.TAX_DUTY_ARTIFACT
    assert rationale == "vat only"


def test_parse_fenced_json():
    fenced = "```json\n" + _reply(taxonomy.PROHIBITED_GEO_BLOCKING) + "\n```"
    label, _ = parse_model_reply(fenced)
    assert label == taxonomy.PROHIBITED_GEO_BLOCKING


def test_parse_json_with_surrounding_prose():
    text = "Here is my answer:\n" + _reply(taxonomy.INSUFFICIENT_INFO) + "\nThanks!"
    label, _ = parse_model_reply(text)
    assert label == taxonomy.INSUFFICIENT_INFO


def test_parse_lowercase_label_is_normalised():
    label, _ = parse_model_reply('{"label": "permitted_objective_justification", "rationale": "x"}')
    assert label == taxonomy.PERMITTED_OBJECTIVE_JUSTIFICATION


def test_parse_non_taxonomy_label_falls_back_to_insufficient():
    label, rationale = parse_model_reply('{"label": "TOTALLY_MADE_UP", "rationale": "x"}')
    assert label == taxonomy.INSUFFICIENT_INFO
    assert "non-taxonomy" in rationale


def test_parse_garbage_does_not_raise():
    label, rationale = parse_model_reply("not json at all")
    assert label == taxonomy.INSUFFICIENT_INFO
    assert "no JSON" in rationale


def test_parse_empty_does_not_raise():
    label, _ = parse_model_reply("")
    assert label == taxonomy.INSUFFICIENT_INFO


# --------------------------------------------------------------------------- #
# consensus
# --------------------------------------------------------------------------- #
def _v(family, label, ok=True):
    return JurorVerdict(family, f"m-{family}", label, "r", ok=ok)


def test_consensus_unanimous():
    vs = [_v("openai", "A"), _v("google", "A"), _v("anthropic", "A")]
    label, routed, tally = consensus(vs)
    assert label == "A"
    assert routed is False
    assert tally == {"A": 3}


def test_consensus_majority_two_of_three():
    vs = [_v("openai", "A"), _v("google", "A"), _v("anthropic", "B")]
    label, routed, tally = consensus(vs)
    assert label == "A"
    assert routed is False
    assert tally == {"A": 2, "B": 1}


def test_consensus_three_way_split_routes_to_human():
    vs = [_v("openai", "A"), _v("google", "B"), _v("anthropic", "C")]
    label, routed, tally = consensus(vs)
    assert label == taxonomy.ROUTE_TO_HUMAN
    assert routed is True
    assert tally == {"A": 1, "B": 1, "C": 1}


def test_consensus_insufficient_info_can_be_the_majority():
    vs = [
        _v("openai", taxonomy.INSUFFICIENT_INFO),
        _v("google", taxonomy.INSUFFICIENT_INFO),
        _v("anthropic", taxonomy.PROHIBITED_GEO_BLOCKING),
    ]
    label, routed, _ = consensus(vs)
    assert label == taxonomy.INSUFFICIENT_INFO
    assert routed is False


def test_consensus_one_error_non_vote_still_allows_majority():
    # Two agree on A; the third errored (counts as INSUFFICIENT_INFO non-vote).
    vs = [
        _v("openai", "A"),
        _v("google", "A"),
        _v("anthropic", taxonomy.INSUFFICIENT_INFO, ok=False),
    ]
    label, routed, _ = consensus(vs)
    assert label == "A"
    assert routed is False


# --------------------------------------------------------------------------- #
# run_jury (mocked client)
# --------------------------------------------------------------------------- #
_FACTS = {
    "schema": "amber/facts@2",
    "url": "https://shop.example/x",
    "countries": ["BE", "DE"],
    "cross_country_comparison": {
        "primary_finding": "ACCESS_OR_PAYMENT_DENIAL",
        "net_delta": None,
        "access_denial": {"geo_blocked_countries": ["BE"], "purchasable_countries": ["DE"]},
        "per_country_states": {"BE": ["GEO_BLOCKED"], "DE": ["PURCHASABLE"]},
    },
    "within_country_control": {"all_intra_country_agree": True, "per_country": []},
}


def test_run_jury_majority_advisory():
    client = FakeClient(
        {
            "m-openai": _reply(taxonomy.PROHIBITED_GEO_BLOCKING),
            "m-google": _reply(taxonomy.PROHIBITED_GEO_BLOCKING),
            "m-anthropic": _reply(taxonomy.INSUFFICIENT_INFO),
        }
    )
    adv = run_jury(_FACTS, client=client, models=MODELS)
    assert adv.advisory_label == taxonomy.PROHIBITED_GEO_BLOCKING
    assert adv.routed_to_human is False
    assert adv.signed is False  # LOCK-4 machine-checkable flag
    assert adv.layer == "LAYER_2_INTERPRETATION"
    assert len(adv.jurors) == 3
    # family order is stable openai, google, anthropic
    assert [j.family for j in adv.jurors] == ["openai", "google", "anthropic"]
    assert sorted(client.calls) == ["m-anthropic", "m-google", "m-openai"]


def test_run_jury_split_routes_to_human():
    client = FakeClient(
        {
            "m-openai": _reply(taxonomy.PROHIBITED_GEO_BLOCKING),
            "m-google": _reply(taxonomy.PERMITTED_OBJECTIVE_JUSTIFICATION),
            "m-anthropic": _reply(taxonomy.TAX_DUTY_ARTIFACT),
        }
    )
    adv = run_jury(_FACTS, client=client, models=MODELS)
    assert adv.advisory_label == taxonomy.ROUTE_TO_HUMAN
    assert adv.routed_to_human is True


def test_run_jury_model_error_is_surfaced_not_swallowed():
    client = FakeClient(
        {
            "m-openai": _reply(taxonomy.PROHIBITED_GEO_BLOCKING),
            "m-google": _reply(taxonomy.PROHIBITED_GEO_BLOCKING),
            "m-anthropic": RuntimeError("provider 503"),
        }
    )
    adv = run_jury(_FACTS, client=client, models=MODELS)
    errored = [j for j in adv.jurors if j.family == "anthropic"][0]
    assert errored.ok is False
    assert "provider 503" in errored.error
    assert errored.label == taxonomy.INSUFFICIENT_INFO
    # The two healthy models still carry the advisory.
    assert adv.advisory_label == taxonomy.PROHIBITED_GEO_BLOCKING


def test_advisory_dict_carries_disclaimer_and_unsigned_flag():
    client = FakeClient(
        {m: _reply(taxonomy.TAX_DUTY_ARTIFACT) for m in MODELS.as_tuple()}
    )
    adv = run_jury(_FACTS, client=client, models=MODELS)
    d = adv.as_dict()
    assert d["signed"] is False
    assert "NOT legal advice" in d["disclaimer"]
    assert d["schema"] == "amber/legal_advisory@1"
