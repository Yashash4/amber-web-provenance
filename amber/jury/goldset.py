"""The methodology gold-set + precision/recall metrics (the AI/ML-prize evidence).

Per LOCK 6 we win the AI/ML prize with REPRODUCIBLE gold-set precision/recall in
the README — NOT with on-screen consensus theater (no Fleiss' kappa anywhere
user-facing). This module holds a small, hand-labeled gold set of synthetic
Layer-1 observations, each with a ground-truth Reg 2018/302 label, and computes
per-model + consensus precision / recall / accuracy on it.

EVERY example here is a clearly-labeled METHODOLOGY FIXTURE — a constructed test
case for measuring the classifier, NEVER presented as real production capture
data. The cases are derived from the structure of the Reg 2018/302 taxonomy
(net-of-tax artifacts, permitted price differentials, access/payment denials,
inconclusive soft-blocks, etc.), so the metric measures whether the jury applies
the *rule* correctly. Synthetic fixtures for measuring a classifier are a
standard, honest evaluation method; the honesty rule we must not break is never
fabricating real price HISTORY or implying a fixture is a live capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from amber.jury import taxonomy
from amber.jury.client import DEFAULT_MODELS, JuryModels, make_client
from amber.jury.jury import JurorVerdict, consensus, run_jury

GOLDSET_VERSION = "amber/jury-goldset@1 (methodology fixture — NOT production data)"


@dataclass(frozen=True)
class GoldExample:
    """One hand-labeled gold-set example: a fixture observation + true label."""

    example_id: str
    description: str
    expected_label: str
    facts: dict[str, Any]


def _facts(
    *,
    countries: list[str],
    primary: str,
    net_delta: dict | None = None,
    access_denial: dict | None = None,
    per_country_states: dict[str, list[str]],
    within_agree: bool = True,
    url: str = "https://shop.amber-demo.example/product/gold-fixture",
) -> dict[str, Any]:
    """Build a minimal ``amber/facts@2``-shaped fixture for the gold set.

    Only the legally-relevant slice :func:`amber.jury.jury.summarize_facts`
    reads is populated; the schema tag marks it as a fixture, not a real packet.
    """
    return {
        "schema": "amber/facts@2",
        "url": url,
        "sku_label": "GOLD-FIXTURE (METHODOLOGY — NOT PRODUCTION DATA)",
        "countries": countries,
        "same_second_batch": True,
        "sku_identity": {"confidence": "GTIN_MATCH", "canonical_gtin": "04006381333931"},
        "cross_country_comparison": {
            "primary_finding": primary,
            "net_delta": net_delta,
            "access_denial": access_denial,
            "per_country_states": per_country_states,
        },
        "within_country_control": {
            "all_intra_country_agree": within_agree,
            "per_country": [
                {"country": c, "agreement": "AGREE" if within_agree else "DISAGREE"}
                for c in countries
            ],
        },
    }


def _net(cheap_c: str, exp_c: str, cheap: str, exp: str, delta: str, gross_delta: str) -> dict:
    return {
        "cheaper_country": cheap_c,
        "more_expensive_country": exp_c,
        "cheaper_net": cheap,
        "more_expensive_net": exp,
        "net_of_tax_delta": delta,
        "gross_delta": gross_delta,
        "delta_is_nonzero": delta not in ("0", "0.00", "0.0"),
    }


# --------------------------------------------------------------------------- #
# The hand-labeled gold set (16 examples across the taxonomy). Ground-truth
# labels are the legally-correct classification under Reg 2018/302 given ONLY
# the deterministic signed facts shown. These are the test cases the
# precision/recall numbers are computed against.
# --------------------------------------------------------------------------- #
GOLD_SET: tuple[GoldExample, ...] = (
    # --- TAX_DUTY_ARTIFACT: gross differs, net agrees (~0) ---
    GoldExample(
        "tax-01",
        "Gross prices differ but net-of-tax prices are equal (pure VAT artifact).",
        taxonomy.TAX_DUTY_ARTIFACT,
        _facts(
            countries=["BE", "DE"],
            primary="NO_NET_DELTA",
            net_delta=_net("BE", "DE", "100.00", "100.00", "0.00", "2.00"),
            per_country_states={"BE": ["PURCHASABLE"], "DE": ["PURCHASABLE"]},
        ),
    ),
    GoldExample(
        "tax-02",
        "VAT-only difference: identical net, both PURCHASABLE.",
        taxonomy.TAX_DUTY_ARTIFACT,
        _facts(
            countries=["FR", "DE"],
            primary="NO_NET_DELTA",
            net_delta=_net("DE", "FR", "82.50", "82.50", "0.00", "1.65"),
            per_country_states={"DE": ["PURCHASABLE"], "FR": ["PURCHASABLE"]},
        ),
    ),
    # --- PERMITTED_OBJECTIVE_JUSTIFICATION: lawful net price differential, ---
    # both markets fully PURCHASABLE (2018/302 permits different net prices).
    GoldExample(
        "perm-01",
        "Net-of-tax price differs but both markets are PURCHASABLE — a permitted "
        "price differential, not an access denial.",
        taxonomy.PERMITTED_OBJECTIVE_JUSTIFICATION,
        _facts(
            countries=["BE", "DE"],
            primary="NET_OF_TAX_PRICE_DELTA",
            net_delta=_net("BE", "DE", "107.43", "115.24", "7.81", "5.00"),
            per_country_states={"BE": ["PURCHASABLE"], "DE": ["PURCHASABLE"]},
        ),
    ),
    GoldExample(
        "perm-02",
        "Larger net differential, both PURCHASABLE — still permitted (price "
        "parity is not required by 2018/302).",
        taxonomy.PERMITTED_OBJECTIVE_JUSTIFICATION,
        _facts(
            countries=["IE", "DE"],
            primary="NET_OF_TAX_PRICE_DELTA",
            net_delta=_net("DE", "IE", "90.00", "118.00", "28.00", "30.00"),
            per_country_states={"DE": ["PURCHASABLE"], "IE": ["PURCHASABLE"]},
        ),
    ),
    # --- PROHIBITED_GEO_BLOCKING: one market blocked, the other completes ---
    GoldExample(
        "block-01",
        "Belgium GEO_BLOCKED while Germany PURCHASABLE — access denial, no "
        "objective justification.",
        taxonomy.PROHIBITED_GEO_BLOCKING,
        _facts(
            countries=["BE", "DE"],
            primary="ACCESS_OR_PAYMENT_DENIAL",
            access_denial={
                "geo_blocked_countries": ["BE"],
                "purchasable_countries": ["DE"],
            },
            per_country_states={"BE": ["GEO_BLOCKED"], "DE": ["PURCHASABLE"]},
        ),
    ),
    GoldExample(
        "block-02",
        "Checkout refused for the Belgian session (payment-step denial) while "
        "Germany completes — Art 5 discriminatory refusal.",
        taxonomy.PROHIBITED_GEO_BLOCKING,
        _facts(
            countries=["BE", "DE"],
            primary="ACCESS_OR_PAYMENT_DENIAL",
            access_denial={
                "geo_blocked_countries": ["BE"],
                "purchasable_countries": ["DE"],
            },
            per_country_states={"BE": ["GEO_BLOCKED"], "DE": ["PURCHASABLE"]},
        ),
    ),
    GoldExample(
        "block-03",
        "Italy blocked while Germany completes — same-SKU access denial.",
        taxonomy.PROHIBITED_GEO_BLOCKING,
        _facts(
            countries=["IT", "DE"],
            primary="ACCESS_OR_PAYMENT_DENIAL",
            access_denial={
                "geo_blocked_countries": ["IT"],
                "purchasable_countries": ["DE"],
            },
            per_country_states={"IT": ["GEO_BLOCKED"], "DE": ["PURCHASABLE"]},
        ),
    ),
    # --- INSUFFICIENT_INFO: soft-block / single country / inconclusive ---
    GoldExample(
        "insuf-01",
        "Belgian session INCONCLUSIVE (anti-bot soft-block forced it); no "
        "causally-independent denial signal.",
        taxonomy.INSUFFICIENT_INFO,
        _facts(
            countries=["BE", "DE"],
            primary="INCONCLUSIVE",
            net_delta=None,
            per_country_states={"BE": ["INCONCLUSIVE"], "DE": ["PURCHASABLE"]},
        ),
    ),
    GoldExample(
        "insuf-02",
        "Only one country resolved (the other failed to capture) — cannot "
        "compare.",
        taxonomy.INSUFFICIENT_INFO,
        _facts(
            countries=["DE"],
            primary="INCONCLUSIVE",
            net_delta=None,
            per_country_states={"DE": ["PURCHASABLE"]},
        ),
    ),
    GoldExample(
        "insuf-03",
        "Both countries INCONCLUSIVE (soft-blocked) — nothing to classify.",
        taxonomy.INSUFFICIENT_INFO,
        _facts(
            countries=["BE", "DE"],
            primary="INCONCLUSIVE",
            net_delta=None,
            per_country_states={"BE": ["INCONCLUSIVE"], "DE": ["INCONCLUSIVE"]},
        ),
    ),
    # --- TAX_DUTY_ARTIFACT: another VAT-only control (negative control) ---
    GoldExample(
        "tax-03",
        "Net agrees to the cent across three countries — tax artifact only.",
        taxonomy.TAX_DUTY_ARTIFACT,
        _facts(
            countries=["BE", "DE"],
            primary="NO_NET_DELTA",
            net_delta=_net("DE", "BE", "59.99", "59.99", "0.00", "1.20"),
            per_country_states={"BE": ["PURCHASABLE"], "DE": ["PURCHASABLE"]},
        ),
    ),
    # --- PERMITTED: small but real net delta, both purchasable ---
    GoldExample(
        "perm-03",
        "Small real net delta, both PURCHASABLE — permitted differential.",
        taxonomy.PERMITTED_OBJECTIVE_JUSTIFICATION,
        _facts(
            countries=["NL", "DE"],
            primary="NET_OF_TAX_PRICE_DELTA",
            net_delta=_net("DE", "NL", "44.00", "47.50", "3.50", "3.50"),
            per_country_states={"DE": ["PURCHASABLE"], "NL": ["PURCHASABLE"]},
        ),
    ),
    GoldExample(
        "perm-04",
        "Net differential between Spain and Germany, both PURCHASABLE.",
        taxonomy.PERMITTED_OBJECTIVE_JUSTIFICATION,
        _facts(
            countries=["ES", "DE"],
            primary="NET_OF_TAX_PRICE_DELTA",
            net_delta=_net("ES", "DE", "200.00", "215.00", "15.00", "12.00"),
            per_country_states={"ES": ["PURCHASABLE"], "DE": ["PURCHASABLE"]},
        ),
    ),
    # --- PROHIBITED: redirect-style block ---
    GoldExample(
        "block-04",
        "Belgian session auto-redirected to a national gate (GEO_BLOCKED) while "
        "Germany completes the same SKU.",
        taxonomy.PROHIBITED_GEO_BLOCKING,
        _facts(
            countries=["BE", "DE"],
            primary="ACCESS_OR_PAYMENT_DENIAL",
            access_denial={
                "geo_blocked_countries": ["BE"],
                "purchasable_countries": ["DE"],
            },
            per_country_states={"BE": ["GEO_BLOCKED"], "DE": ["PURCHASABLE"]},
        ),
    ),
    # --- INSUFFICIENT: denial present but the comparator is also inconclusive ---
    GoldExample(
        "insuf-04",
        "One country GEO_BLOCKED but the comparator is INCONCLUSIVE (not "
        "confirmed PURCHASABLE) — no clean access-denial contrast.",
        taxonomy.INSUFFICIENT_INFO,
        _facts(
            countries=["BE", "DE"],
            primary="INCONCLUSIVE",
            net_delta=None,
            per_country_states={"BE": ["GEO_BLOCKED"], "DE": ["INCONCLUSIVE"]},
        ),
    ),
    # --- TAX vs PERMITTED boundary: net zero -> tax artifact, not permitted-diff
    GoldExample(
        "tax-04",
        "Gross delta large, net delta exactly zero — the difference is entirely "
        "tax, so TAX_DUTY_ARTIFACT (not a permitted price differential).",
        taxonomy.TAX_DUTY_ARTIFACT,
        _facts(
            countries=["BE", "DE"],
            primary="NO_NET_DELTA",
            net_delta=_net("BE", "DE", "300.00", "300.00", "0.00", "9.00"),
            per_country_states={"BE": ["PURCHASABLE"], "DE": ["PURCHASABLE"]},
        ),
    ),
)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


@dataclass
class LabelMetrics:
    """Per-label precision/recall/F1 with the raw tp/fp/fn for transparency."""

    label: str
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class ClassifierMetrics:
    """Accuracy + per-label and macro precision/recall for one classifier."""

    name: str
    n: int
    correct: int
    per_label: dict[str, LabelMetrics] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def macro_precision(self) -> float:
        if not self.per_label:
            return 0.0
        return sum(m.precision for m in self.per_label.values()) / len(self.per_label)

    @property
    def macro_recall(self) -> float:
        if not self.per_label:
            return 0.0
        return sum(m.recall for m in self.per_label.values()) / len(self.per_label)

    @property
    def macro_f1(self) -> float:
        if not self.per_label:
            return 0.0
        return sum(m.f1 for m in self.per_label.values()) / len(self.per_label)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "n": self.n,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "macro_precision": round(self.macro_precision, 4),
            "macro_recall": round(self.macro_recall, 4),
            "macro_f1": round(self.macro_f1, 4),
            "per_label": {k: v.as_dict() for k, v in sorted(self.per_label.items())},
        }


def score_predictions(
    name: str, expected: list[str], predicted: list[str]
) -> ClassifierMetrics:
    """Compute accuracy + per-label precision/recall from aligned label lists.

    ``ROUTE_TO_HUMAN`` is a legitimate predicted value for the consensus
    classifier; it is scored like any other label (it can be a false positive
    against a gold label, and it has no gold instances so its recall slot stays
    empty). This is honest: routing a clear case to a human is a miss, and the
    metric reflects that.
    """
    if len(expected) != len(predicted):
        raise ValueError("score_predictions: expected/predicted length mismatch")

    pairs = list(zip(expected, predicted, strict=True))
    labels = sorted(set(expected) | set(predicted))
    per_label: dict[str, LabelMetrics] = {}
    for label in labels:
        tp = sum(1 for e, p in pairs if e == label and p == label)
        fp = sum(1 for e, p in pairs if e != label and p == label)
        fn = sum(1 for e, p in pairs if e == label and p != label)
        per_label[label] = LabelMetrics(label, tp, fp, fn)

    correct = sum(1 for e, p in pairs if e == p)
    return ClassifierMetrics(name, len(expected), correct, per_label)


@dataclass
class GoldRunRow:
    """The full per-example result row (for the detailed report / debugging)."""

    example_id: str
    expected: str
    jurors: list[JurorVerdict]
    consensus_label: str
    routed_to_human: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "expected": self.expected,
            "jurors": [j.as_dict() for j in self.jurors],
            "consensus_label": self.consensus_label,
            "routed_to_human": self.routed_to_human,
        }


@dataclass
class GoldReport:
    """The complete gold-set evaluation: per-model + consensus metrics + rows."""

    version: str
    n_examples: int
    per_model: dict[str, ClassifierMetrics]
    consensus: ClassifierMetrics
    rows: list[GoldRunRow]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "fixture_disclaimer": (
                "Methodology gold-set fixture: synthetic Layer-1 observations "
                "constructed to measure the legal classifier. NOT real "
                "production capture data; no real price history is fabricated."
            ),
            "n_examples": self.n_examples,
            "per_model": {k: v.as_dict() for k, v in sorted(self.per_model.items())},
            "consensus": self.consensus.as_dict(),
            "rows": [r.as_dict() for r in self.rows],
        }


def evaluate_goldset(
    *,
    client=None,
    models: JuryModels = DEFAULT_MODELS,
    gold_set: tuple[GoldExample, ...] = GOLD_SET,
) -> GoldReport:
    """Run the jury over the gold set and compute per-model + consensus metrics.

    For each example, runs the three-model jury once (reusing the same client),
    records each model's label and the consensus label, then computes
    accuracy + per-label precision/recall/F1 for each model and for the
    consensus. ``client`` is injected by tests; built from the API key otherwise.
    """
    if client is None:
        client = make_client()

    expected = [ex.expected_label for ex in gold_set]
    model_preds: dict[str, list[str]] = {"openai": [], "google": [], "anthropic": []}
    consensus_preds: list[str] = []
    rows: list[GoldRunRow] = []

    for ex in gold_set:
        advisory = run_jury(ex.facts, client=client, models=models)
        by_family = {j.family: j for j in advisory.jurors}
        for family in model_preds:
            model_preds[family].append(by_family[family].label)
        consensus_preds.append(advisory.advisory_label)
        rows.append(
            GoldRunRow(
                example_id=ex.example_id,
                expected=ex.expected_label,
                jurors=advisory.jurors,
                consensus_label=advisory.advisory_label,
                routed_to_human=advisory.routed_to_human,
            )
        )

    per_model = {
        family: score_predictions(family, expected, preds)
        for family, preds in model_preds.items()
    }
    consensus_metrics = score_predictions("consensus", expected, consensus_preds)

    return GoldReport(
        version=GOLDSET_VERSION,
        n_examples=len(gold_set),
        per_model=per_model,
        consensus=consensus_metrics,
        rows=rows,
    )


# Re-export consensus so callers/tests can reach it via goldset if convenient.
__all__ = [
    "GOLD_SET",
    "GOLDSET_VERSION",
    "ClassifierMetrics",
    "GoldExample",
    "GoldReport",
    "GoldRunRow",
    "LabelMetrics",
    "consensus",
    "evaluate_goldset",
    "score_predictions",
]
