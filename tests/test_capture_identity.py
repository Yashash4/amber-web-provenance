"""GTIN / SKU-identity confidence tests — no silent name fallback."""

from __future__ import annotations

from amber.capture import identity
from amber.capture.identity import IdentityInput


def test_valid_gtin13_check_digit():
    # 4006381333931 is a check-digit-valid EAN-13.
    assert identity.gtin_check_digit_valid("4006381333931") is True


def test_invalid_gtin_check_digit():
    assert identity.gtin_check_digit_valid("4006381333930") is False  # wrong check digit
    assert identity.gtin_check_digit_valid("123") is False  # wrong length
    assert identity.gtin_check_digit_valid("400638133393X") is False  # non-digit
    assert identity.gtin_check_digit_valid("") is False


def test_normalize_pads_to_14():
    assert identity.normalize_gtin("4006381333931") == "00004006381333931"[-14:]
    assert identity.normalize_gtin("4006381333931") == "04006381333931"
    assert identity.normalize_gtin("invalid") is None


def test_gtin_match_high_confidence():
    r = identity.assess(
        [
            IdentityInput("de-01", "4006381333931"),
            IdentityInput("be-01", "4006381333931"),
        ]
    )
    assert r.confidence == identity.GTIN_MATCH
    assert r.canonical_gtin == "04006381333931"


def test_gtin_13_and_14_representation_match():
    # Same identity in 13- and zero-padded 14-digit form -> still a match.
    g13 = "4006381333931"
    g14 = "04006381333931"
    assert identity.gtin_check_digit_valid(g14) is True
    r = identity.assess([IdentityInput("a", g13), IdentityInput("b", g14)])
    assert r.confidence == identity.GTIN_MATCH


def test_missing_gtin_is_unverified_no_name_fallback():
    r = identity.assess(
        [IdentityInput("de-01", "4006381333931"), IdentityInput("be-01", None)]
    )
    assert r.confidence == identity.SKU_IDENTITY_UNVERIFIED
    assert "no silent name fallback" in r.rationale


def test_differing_gtins_unverified():
    r = identity.assess(
        [IdentityInput("de-01", "4006381333931"), IdentityInput("be-01", "5010019640161")]
    )
    assert r.confidence == identity.SKU_IDENTITY_UNVERIFIED


def test_bundle_mismatch():
    r = identity.assess(
        [
            IdentityInput("de-01", "4006381333931", bundle_descriptor="single"),
            IdentityInput("be-01", "4006381333931", bundle_descriptor="2-pack"),
        ]
    )
    assert r.confidence == identity.BUNDLE_MISMATCH
    assert r.canonical_gtin == "04006381333931"


def test_invalid_gtin_treated_as_unverified():
    r = identity.assess(
        [IdentityInput("de-01", "4006381333930"), IdentityInput("be-01", "4006381333930")]
    )
    # Both share the SAME string but it's check-digit-invalid -> unverified.
    assert r.confidence == identity.SKU_IDENTITY_UNVERIFIED
