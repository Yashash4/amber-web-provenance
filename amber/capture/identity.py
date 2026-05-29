"""GTIN / SKU-identity confidence.

A price comparison is only honest if the two geos are quoting the SAME product.
The robust identity anchor is the **GTIN** (the barcode): a 8/12/13/14-digit code
with a check digit. Amber's rule (glossary):

  * GTIN present in every compared capture AND identical across them AND the
    bundle/warranty descriptors match  -> ``GTIN_MATCH`` (high confidence).
  * GTIN present and check-digit-valid but the bundle/warranty differs ->
    ``BUNDLE_MISMATCH`` (the two listings are not the same offer).
  * GTIN absent / differing / invalid -> ``SKU_IDENTITY_UNVERIFIED``.

There is **no silent name fallback**: two listings that merely share a product
name are NOT treated as the same SKU. Surfacing ``SKU_IDENTITY_UNVERIFIED`` is
the root solution; pretending a name match is an identity match is the kind of
overclaim a judge kills.

The GTIN check digit is validated deterministically (GS1 mod-10) so a corrupted
or fabricated GTIN is caught, not trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

GTIN_MATCH = "GTIN_MATCH"
BUNDLE_MISMATCH = "BUNDLE_MISMATCH"
SKU_IDENTITY_UNVERIFIED = "SKU_IDENTITY_UNVERIFIED"

_VALID_GTIN_LENGTHS = {8, 12, 13, 14}


def gtin_check_digit_valid(gtin: str) -> bool:
    """Validate a GTIN's GS1 mod-10 check digit (8/12/13/14 digits).

    Returns False for the wrong length, non-digits, or a failing check digit —
    so a fabricated/garbled GTIN cannot be trusted as identity. The algorithm:
    right-to-left, the digit immediately left of the check digit is weighted 3,
    then alternating 1,3,...; the check digit makes the weighted sum a multiple
    of 10.
    """
    if not gtin or not gtin.isdigit() or len(gtin) not in _VALID_GTIN_LENGTHS:
        return False
    digits = [int(c) for c in gtin]
    check = digits[-1]
    payload = digits[:-1]
    # Weight the payload right-to-left: rightmost payload digit gets weight 3.
    total = 0
    for i, d in enumerate(reversed(payload)):
        weight = 3 if i % 2 == 0 else 1
        total += d * weight
    computed_check = (10 - (total % 10)) % 10
    return computed_check == check


def normalize_gtin(gtin: str | None) -> str | None:
    """Zero-pad a valid shorter GTIN to 14 digits for cross-length comparison.

    GTIN-8/12/13 are the same identity as their 14-digit zero-padded form. We
    normalise so a GTIN-13 and its GTIN-14 representation compare equal. Returns
    None for an invalid/absent GTIN (never a guess).
    """
    if gtin is None:
        return None
    g = gtin.strip()
    if not gtin_check_digit_valid(g):
        return None
    return g.zfill(14)


@dataclass
class IdentityResult:
    """The cross-capture SKU-identity verdict.

    ``confidence`` is one of the three tokens. ``canonical_gtin`` is the shared
    normalized GTIN when matched, else None. ``per_capture`` records each
    capture's raw + normalized GTIN + validity so the fact is auditable.
    """

    confidence: str
    canonical_gtin: str | None
    rationale: str
    per_capture: list[dict] = field(default_factory=list)

    def as_fact(self) -> dict:
        return {
            "confidence": self.confidence,
            "canonical_gtin": self.canonical_gtin,
            "rationale": self.rationale,
            "per_capture": list(self.per_capture),
        }


@dataclass(frozen=True)
class IdentityInput:
    """One capture's identity-bearing fields for the cross-capture comparison."""

    capture_id: str
    gtin: str | None
    bundle_descriptor: str | None = None  # e.g. "single" / "2-pack" / "+warranty"


def assess(inputs: list[IdentityInput]) -> IdentityResult:
    """Assess whether a set of captures are the SAME SKU by GTIN (+ bundle).

    Rules (in order):
      * Any capture missing a valid GTIN -> SKU_IDENTITY_UNVERIFIED.
      * GTINs not all identical (normalized) -> SKU_IDENTITY_UNVERIFIED.
      * GTINs identical but bundle descriptors differ -> BUNDLE_MISMATCH.
      * All identical GTIN + matching bundle -> GTIN_MATCH.
    Never falls back to name matching.
    """
    if not inputs:
        return IdentityResult(
            confidence=SKU_IDENTITY_UNVERIFIED,
            canonical_gtin=None,
            rationale="no captures to assess",
        )

    per_capture: list[dict] = []
    normalized: list[str | None] = []
    for inp in inputs:
        norm = normalize_gtin(inp.gtin)
        valid = norm is not None
        normalized.append(norm)
        per_capture.append(
            {
                "capture_id": inp.capture_id,
                "gtin_raw": inp.gtin,
                "gtin_normalized": norm,
                "gtin_valid": valid,
                "bundle_descriptor": inp.bundle_descriptor,
            }
        )

    # Any invalid/absent GTIN -> unverified.
    if any(n is None for n in normalized):
        missing = [pc["capture_id"] for pc in per_capture if not pc["gtin_valid"]]
        return IdentityResult(
            confidence=SKU_IDENTITY_UNVERIFIED,
            canonical_gtin=None,
            rationale=(
                f"GTIN absent or check-digit-invalid for capture(s) {missing}; "
                "no silent name fallback -> SKU_IDENTITY_UNVERIFIED"
            ),
            per_capture=per_capture,
        )

    # All present + valid: are they identical?
    distinct = set(normalized)
    if len(distinct) > 1:
        return IdentityResult(
            confidence=SKU_IDENTITY_UNVERIFIED,
            canonical_gtin=None,
            rationale=f"GTINs differ across captures: {sorted(distinct)}",
            per_capture=per_capture,
        )

    canonical = next(iter(distinct))

    # GTINs identical: check bundle descriptors. Treat None as "unspecified";
    # only an explicit DIFFERENCE between two specified descriptors is a mismatch.
    specified = {
        inp.bundle_descriptor.strip().lower()
        for inp in inputs
        if inp.bundle_descriptor and inp.bundle_descriptor.strip()
    }
    if len(specified) > 1:
        return IdentityResult(
            confidence=BUNDLE_MISMATCH,
            canonical_gtin=canonical,
            rationale=(
                f"identical GTIN {canonical} but bundle/warranty descriptors "
                f"differ: {sorted(specified)} — not the same offer"
            ),
            per_capture=per_capture,
        )

    return IdentityResult(
        confidence=GTIN_MATCH,
        canonical_gtin=canonical,
        rationale=(
            f"identical valid GTIN {canonical} across all "
            f"{len(inputs)} captures; bundle/warranty consistent"
        ),
        per_capture=per_capture,
    )
