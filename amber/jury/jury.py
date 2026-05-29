"""The three-model legal jury — Layer-2 UNSIGNED advisory.

Given a signed Amber Layer-1 observation (a packet's ``facts.json`` — the
deterministic price/geo facts), three causally-different frontier models
(OpenAI / Google / Anthropic, via the AI/ML API gateway) **independently**
classify the Reg (EU) 2018/302 legal taxonomy and give a brief, rule-grounded
rationale. The three run concurrently.

Consensus rule (LOCK 6 — NO Fleiss' kappa / consensus-theater on any user
surface; precision/recall is the headline, see ``goldset.py``):
  * a strict MAJORITY label (>= 2 of 3 agreeing on the same token) becomes the
    advisory label;
  * otherwise (all three differ, or a model errored leaving no majority) the
    outcome is ``ROUTE_TO_HUMAN`` — the jury NEVER auto-resolves a split.

Layer separation (LOCK 4) is PHYSICAL: this module reads the signed facts and
emits a SEPARATE advisory object/file. It never writes back into the packet and
an LLM never computes a fact/number into the signed bundle. The advisory carries
an explicit disclaimer that it is AI-assisted interpretation, unsigned, and not
legal advice.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from amber.jury import taxonomy
from amber.jury.client import DEFAULT_MODELS, JuryModels, make_client

ADVISORY_SCHEMA = "amber/legal_advisory@1"

# The disclaimer stamped onto every advisory — this is the LOCK-4 / honesty
# guarantee made machine-visible: the label is interpretation, not signed fact.
ADVISORY_DISCLAIMER = (
    "AI-assisted interpretation — NOT signed, NOT legal advice. This Layer-2 "
    "advisory is produced by three independent language models reading the "
    "signed Layer-1 facts; it is physically separate from the cryptographically "
    "signed evidence packet and is never written into it. A human lawyer "
    "confirms any legal conclusion. Labels are grounded on Reg (EU) 2018/302."
)

# Bounded, deterministic generation: temperature 0 so the jury is reproducible.
_TEMPERATURE = 0.0
_MAX_TOKENS = 400
# Wall-clock cap per model call so one hung provider cannot stall the jury.
_PER_MODEL_TIMEOUT_S = 60.0


def _system_prompt() -> str:
    """The shared system prompt — identical rule text for all three jurors."""
    return (
        "You are a legal-taxonomy triage assistant for Regulation (EU) 2018/302 "
        "(the EU Geo-Blocking Regulation). You classify a deterministic, "
        "cryptographically-signed observation of an online retailer serving two "
        "EU member states. You do NOT give legal advice; you produce a labeled, "
        "rule-grounded interpretation for a human lawyer to confirm.\n\n"
        "Regulation (EU) 2018/302 in brief: it concerns ACCESS, not price "
        "parity. It PERMITS traders to set different net prices per member "
        "state, but PROHIBITS (Arts 3-5) blocking, automatically re-routing, or "
        "refusing a customer in one member state from accessing and buying at "
        "the offer available to another member state, and prohibits "
        "discriminatory payment refusal (Art 5) — unless an objective "
        "justification applies.\n\n"
        "Choose EXACTLY ONE label from this taxonomy (each line gives the "
        "criterion you must apply):\n"
        f"{taxonomy.taxonomy_prompt_block()}\n\n"
        "Rules: a net-of-tax price difference ALONE, with both markets "
        "PURCHASABLE, is PERMITTED under 2018/302 (it is not prohibited "
        "geo-blocking). Only an actual access/payment denial (one market "
        "blocked while another completes) with no objective justification is "
        "PROHIBITED_GEO_BLOCKING. If the signed facts are inconclusive, choose "
        "INSUFFICIENT_INFO rather than guess.\n\n"
        'Respond with ONLY a JSON object, no prose around it: '
        '{"label": "<one taxonomy token>", "rationale": '
        '"<at most 60 words, grounded in Reg 2018/302 criteria>"}'
    )


def summarize_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Extract the legally-relevant slice of a Layer-1 ``facts.json``.

    Supports the ``amber/facts@2`` floor schema (the rich cross-country
    comparison) and degrades gracefully for other shapes by passing through the
    whole object. We send the model the deterministic findings — never raw HTML
    — so it reasons over the signed facts, not unverified page text.
    """
    schema = facts.get("schema", "")
    if not str(schema).startswith("amber/facts@2"):
        # Unknown/older schema: hand the model the whole signed-facts object.
        return dict(facts)

    return {
        "url": facts.get("url"),
        "sku_label": facts.get("sku_label"),
        "countries": facts.get("countries"),
        "same_second_batch": facts.get("same_second_batch"),
        "sku_identity": {
            "confidence": (facts.get("sku_identity") or {}).get("confidence"),
            "canonical_gtin": (facts.get("sku_identity") or {}).get("canonical_gtin"),
        },
        "cross_country_comparison": facts.get("cross_country_comparison"),
        "within_country_control": facts.get("within_country_control"),
    }


def _build_user_prompt(facts: dict[str, Any]) -> str:
    brief = summarize_facts(facts)
    return (
        "Signed Layer-1 observation (deterministic facts; net-of-tax already "
        "computed by Amber; no LLM produced any number below):\n"
        + json.dumps(brief, indent=2, sort_keys=True, ensure_ascii=False)
    )


# A fenced or bare JSON object, captured non-greedily from the first { to a }.
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_model_reply(text: str) -> tuple[str, str]:
    """Parse a model reply into ``(label, rationale)``.

    Robust to models that wrap JSON in ``` fences or add stray prose: it
    extracts the first balanced-looking ``{...}`` and parses it. An unparseable
    reply, or a label outside the taxonomy, maps to ``INSUFFICIENT_INFO`` with a
    rationale explaining the parse outcome — we never invent a label, and we
    never raise (a single bad reply must not crash the jury).
    """
    raw = (text or "").strip()
    match = _JSON_OBJ_RE.search(raw)
    if not match:
        return (
            taxonomy.INSUFFICIENT_INFO,
            f"model reply had no JSON object; raw reply: {raw[:160]!r}",
        )
    try:
        obj = json.loads(match.group(0))
    except (ValueError, TypeError):
        return (
            taxonomy.INSUFFICIENT_INFO,
            f"model JSON did not parse; raw reply: {raw[:160]!r}",
        )
    label = str(obj.get("label", "")).strip().upper()
    rationale = str(obj.get("rationale", "")).strip()
    if not taxonomy.is_valid_label(label):
        return (
            taxonomy.INSUFFICIENT_INFO,
            f"model returned non-taxonomy label {label!r}; "
            f"rationale was: {rationale[:160]!r}",
        )
    return label, (rationale or "(model returned no rationale)")


@dataclass
class JurorVerdict:
    """One model's independent classification of the signed observation."""

    family: str  # "openai" | "google" | "anthropic"
    model_id: str
    label: str
    rationale: str
    ok: bool  # False => the model call errored; label is then INSUFFICIENT_INFO
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "model_id": self.model_id,
            "label": self.label,
            "rationale": self.rationale,
            "ok": self.ok,
            "error": self.error,
        }


def _classify_one(client, family: str, model_id: str, system: str, user: str) -> JurorVerdict:
    """Call one model and parse its verdict. Errors become a labeled non-vote.

    A provider error (rate limit, 5xx, timeout) is captured as ``ok=False`` with
    label INSUFFICIENT_INFO so it counts as a non-vote in the majority — it never
    crashes the jury and never silently becomes a substantive label.
    """
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
            timeout=_PER_MODEL_TIMEOUT_S,
        )
        content = resp.choices[0].message.content or ""
        label, rationale = parse_model_reply(content)
        return JurorVerdict(family, model_id, label, rationale, ok=True)
    except Exception as exc:  # provider/network/SDK error => non-vote, surfaced
        return JurorVerdict(
            family,
            model_id,
            taxonomy.INSUFFICIENT_INFO,
            f"model call failed: {type(exc).__name__}: {exc}",
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def consensus(verdicts: list[JurorVerdict]) -> tuple[str, bool, dict[str, int]]:
    """Reduce juror verdicts to a consensus label.

    Returns ``(label, routed_to_human, tally)``. A strict majority (>= 2 of 3 on
    the SAME token) wins. Otherwise the outcome is ``ROUTE_TO_HUMAN`` and
    ``routed_to_human`` is True — the jury never auto-resolves a split. ``tally``
    is the per-label vote count for the report. INSUFFICIENT_INFO is a real
    label and can itself form a majority (the jury collectively declining).
    """
    tally: dict[str, int] = {}
    for v in verdicts:
        tally[v.label] = tally.get(v.label, 0) + 1

    threshold = (len(verdicts) // 2) + 1  # strict majority of the panel size
    for label, count in tally.items():
        if count >= threshold:
            return label, False, tally
    return taxonomy.ROUTE_TO_HUMAN, True, tally


@dataclass
class Advisory:
    """The Layer-2 UNSIGNED advisory — the jury's full result.

    This object (and its JSON form) is PHYSICALLY SEPARATE from the signed
    Layer-1 packet: it is written next to the packet as ``legal_advisory.json``,
    never inside it.
    """

    schema: str
    advisory_label: str
    routed_to_human: bool
    tally: dict[str, int]
    jurors: list[JurorVerdict]
    facts_summary: dict[str, Any]
    generated_at: str
    disclaimer: str = ADVISORY_DISCLAIMER
    signed: bool = False  # ALWAYS False — this is the machine-checkable LOCK-4 flag
    layer: str = "LAYER_2_INTERPRETATION"
    criterion: str = field(default="")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "layer": self.layer,
            "signed": self.signed,
            "disclaimer": self.disclaimer,
            "advisory_label": self.advisory_label,
            "advisory_criterion": self.criterion,
            "routed_to_human": self.routed_to_human,
            "tally": self.tally,
            "jurors": [j.as_dict() for j in self.jurors],
            "facts_summary": self.facts_summary,
            "generated_at": self.generated_at,
        }


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_jury(
    facts: dict[str, Any],
    *,
    client=None,
    models: JuryModels = DEFAULT_MODELS,
) -> Advisory:
    """Run the three-model jury on a Layer-1 ``facts`` dict and return an Advisory.

    The three model calls run CONCURRENTLY (a thread per model; the OpenAI SDK
    is blocking I/O, so threads give true wall-clock parallelism). ``client`` is
    injected by tests (mocked) and built from the AI/ML API key otherwise.
    """
    if client is None:
        client = make_client()

    system = _system_prompt()
    user = _build_user_prompt(facts)
    jobs = (
        ("openai", models.openai),
        ("google", models.google),
        ("anthropic", models.anthropic),
    )

    verdicts: list[JurorVerdict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {
            pool.submit(_classify_one, client, family, model_id, system, user): family
            for family, model_id in jobs
        }
        results: dict[str, JurorVerdict] = {}
        for fut in concurrent.futures.as_completed(futures):
            v = fut.result()
            results[v.family] = v
    # Preserve a stable family order in the report (openai, google, anthropic).
    verdicts = [results[family] for family, _ in jobs]

    label, routed, tally = consensus(verdicts)
    criterion = (
        taxonomy.LABELS_BY_TOKEN[label].criterion
        if label in taxonomy.LABELS_BY_TOKEN
        else "No majority label — disagreement routed to a human reviewer."
    )

    return Advisory(
        schema=ADVISORY_SCHEMA,
        advisory_label=label,
        routed_to_human=routed,
        tally=tally,
        jurors=verdicts,
        facts_summary=summarize_facts(facts),
        generated_at=_now_iso(),
        criterion=criterion,
    )
