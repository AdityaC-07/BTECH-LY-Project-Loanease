"""
PAN generator utility for deterministic CIBIL score targeting.

The actual CIBIL simulation formula (services/credit_score.py):
    score = 300 + (int(md5(PAN.upper())[:8], 16) % 601)

Note: The spec references SHA256 — the implementation uses MD5.
"""
from __future__ import annotations

import hashlib
from typing import Dict, Optional


def _cibil_from_pan(pan: str) -> int:
    h = hashlib.md5(pan.upper().encode()).hexdigest()
    return 300 + (int(h[:8], 16) % 601)


def generate_pan_for_cibil(target_score: int, limit: int = 200_000) -> str:
    """Return the first PAN-like string whose CIBIL score equals target_score.

    Searches the space "TSTxxxxx" where x increments from 0 to limit.
    Raises ValueError if no match is found within limit iterations.
    """
    if not (300 <= target_score <= 900):
        raise ValueError(f"target_score must be in [300, 900], got {target_score}")
    for i in range(limit):
        # Shape: TST + 5-digit number + A + 1-digit → 10 chars, PAN-like
        candidate = f"TST{i:05d}A{i % 10}"
        if _cibil_from_pan(candidate) == target_score:
            return candidate
    raise ValueError(f"No PAN found for CIBIL target {target_score} within {limit} iterations")


def build_pan_map(targets: Dict[str, int]) -> Dict[str, str]:
    """Build a {label: pan} mapping for a dict of {label: target_score}."""
    return {label: generate_pan_for_cibil(score) for label, score in targets.items()}


# ---------------------------------------------------------------------------
# Pre-computed PANs for the 16 test cases defined in the spec.
# These are computed once at import time and reused across all test modules.
# ---------------------------------------------------------------------------

_BUCKET_TARGETS: Dict[str, int] = {
    # Tier 2 – Poor
    "poor_low":     320,
    "poor_mid":     450,
    "poor_high":    549,
    # Tier 3 – Below Average (Fair)
    "fair_low":     580,
    "fair_mid":     620,
    "fair_high":    649,
    # Tier 4 – Good
    "good_low":     680,
    "good_mid":     720,
    "good_high":    749,
    # Tier 5 – Very Good
    "very_good_low":  760,
    "very_good_mid":  785,
    "very_good_high": 799,
    # Tier 6 – Excellent
    "excellent_low":  820,
    "excellent_mid":  870,
    "excellent_high": 900,
}

GENERATED_TEST_PANS: Dict[str, str] = build_pan_map(_BUCKET_TARGETS)


# ---------------------------------------------------------------------------
# Self-tests (run with pytest tests/test_pan_generator.py)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402  (below imports are fine for test files)


class TestPanGeneratorCorrectness:
    """Verify every generated PAN hashes back to its target score."""

    @pytest.mark.parametrize("label,target", list(_BUCKET_TARGETS.items()))
    def test_generated_pan_matches_target(self, label: str, target: int) -> None:
        pan = GENERATED_TEST_PANS[label]
        assert _cibil_from_pan(pan) == target, (
            f"PAN {pan!r} for label {label!r} produced "
            f"{_cibil_from_pan(pan)}, expected {target}"
        )

    def test_score_always_in_range(self) -> None:
        for label, pan in GENERATED_TEST_PANS.items():
            score = _cibil_from_pan(pan)
            assert 300 <= score <= 900, f"{label}: score {score} out of range"

    def test_each_pan_is_unique(self) -> None:
        pans = list(GENERATED_TEST_PANS.values())
        assert len(pans) == len(set(pans)), "Duplicate PANs generated"

    def test_invalid_target_raises(self) -> None:
        with pytest.raises(ValueError):
            generate_pan_for_cibil(150)

    def test_invalid_target_too_high_raises(self) -> None:
        with pytest.raises(ValueError):
            generate_pan_for_cibil(901)
