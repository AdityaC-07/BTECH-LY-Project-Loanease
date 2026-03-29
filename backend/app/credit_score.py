"""
Credit score simulation and banding for LoanEase underwriting.
Deterministic bureau score tied to PAN number as simulation of CIBIL.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal


# Demo PAN scores: hardcoded for predictable demo behavior
DEMO_PAN_SCORES = {
    "ABCDE1234F": 820,  # High score — easy approval
    "XYZPQ5678K": 680,  # Medium score — conditional
    "LMNOP9012R": 420,  # Low score — likely rejection
    "QRSTU3456S": 285,  # Below cutoff — hard reject
    "DEMO00000D": 750,  # Safe demo score
}


# Credit score bands: determine eligibility, rate ranges, and negotiation rounds
CREDIT_SCORE_BANDS = {
    "HARD_REJECT": {
        "min": 0,
        "max": 299,
        "label": "Ineligible",
        "color": "red",
        "eligible": False,
        "xgboost_runs": False,
        "message_en": "Your credit score of {score} is below the minimum threshold of 300. "
        "You are currently ineligible for a loan. "
        "We recommend improving your credit score before reapplying.",
        "message_hi": "आपका credit score {score} है जो न्यूनतम सीमा 300 से कम है। "
        "आप वर्तमान में loan के लिए पात्र नहीं हैं। "
        "हम अनुशंसा करते हैं कि पुनः आवेदन करने से पहले अपना credit score सुधारें।",
    },
    "HIGH_RISK": {
        "min": 300,
        "max": 549,
        "label": "High Risk",
        "color": "orange",
        "eligible": True,
        "rate_min": 13.5,
        "rate_max": 14.0,
        "xgboost_runs": True,
        "negotiation_allowed": False,
        "max_negotiation_rounds": 0,
    },
    "MEDIUM_RISK": {
        "min": 550,
        "max": 699,
        "label": "Medium Risk",
        "color": "yellow",
        "eligible": True,
        "rate_min": 12.0,
        "rate_max": 13.0,
        "xgboost_runs": True,
        "negotiation_allowed": True,
        "max_negotiation_rounds": 1,
    },
    "LOW_MEDIUM_RISK": {
        "min": 700,
        "max": 749,
        "label": "Low-Medium Risk",
        "color": "yellow",
        "eligible": True,
        "rate_min": 11.5,
        "rate_max": 12.0,
        "xgboost_runs": True,
        "negotiation_allowed": True,
        "max_negotiation_rounds": 2,
    },
    "LOW_RISK": {
        "min": 750,
        "max": 900,
        "label": "Low Risk",
        "color": "green",
        "eligible": True,
        "rate_min": 10.5,
        "rate_max": 11.5,
        "xgboost_runs": True,
        "negotiation_allowed": True,
        "max_negotiation_rounds": 3,
    },
}


def validate_pan(pan: str) -> bool:
    """Validate PAN format: 5 letters, 4 digits, 1 letter."""
    return bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan))


def simulate_credit_score(pan: str) -> int:
    """
    Generate deterministic credit score from PAN via SHA256 hashing.
    Same PAN always produces same score (mimics real CIBIL behavior for demo).

    Args:
        pan: Valid PAN number (format: ABCDE1234F)

    Returns:
        Credit score in range 300-900 (realistic CIBIL range)

    Raises:
        ValueError: If PAN format is invalid
    """
    if not validate_pan(pan):
        raise ValueError(f"Invalid PAN format: {pan}. Expected format: ABCDE1234F")

    # Generate deterministic score from PAN hash
    hash_val = int(hashlib.sha256(pan.encode()).hexdigest(), 16)

    # Map to 300-900 range (realistic CIBIL range)
    # Scores below 300 don't exist in CIBIL system
    raw_score = 300 + (hash_val % 601)

    return raw_score


def get_credit_score(pan: str) -> int:
    """
    Get credit score for PAN number.
    Check demo PANs first, then simulate deterministically.

    Args:
        pan: PAN number to score

    Returns:
        Credit score 300-900
    """
    pan = pan.strip().upper()

    # Check demo PANs first for predictable demo behavior
    if pan in DEMO_PAN_SCORES:
        return DEMO_PAN_SCORES[pan]

    # Otherwise simulate deterministically
    return simulate_credit_score(pan)


def get_credit_band(score: int) -> dict:
    """
    Get credit score band details for a given score.

    Args:
        score: Credit score (300-900)

    Returns:
        Band dict with label, color, eligibility, rates, negotiation info
    """
    for band_name, band in CREDIT_SCORE_BANDS.items():
        if band["min"] <= score <= band["max"]:
            return {**band, "band_name": band_name}

    # Default to hardest reject if score out of range
    return {**CREDIT_SCORE_BANDS["HARD_REJECT"], "band_name": "HARD_REJECT"}


def mask_pan(pan: str) -> str:
    """
    Mask PAN for display: show first 5 + last 1 character.
    ABCDE1234F → ABCDE****F
    """
    pan = pan.strip().upper()
    if len(pan) < 6:
        return pan
    return f"{pan[:5]}****{pan[-1]}"
